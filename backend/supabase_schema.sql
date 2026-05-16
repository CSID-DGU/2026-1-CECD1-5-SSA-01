-- ============================================================
-- 비용추계자동화시스템 Supabase Schema
-- ============================================================

-- 0. Extensions
create extension if not exists vector with schema extensions;
-- pg_trgm: 한국어 키워드 보조 검색 (PGroonga 불가 시 fallback)
create extension if not exists pg_trgm;

-- ============================================================
-- Storage Bucket
-- ============================================================
insert into storage.buckets (id, name, public)
values ('assembly-documents', 'assembly-documents', false)
on conflict (id) do nothing;

-- ============================================================
-- 1. 의안 메타데이터
-- ============================================================
create table if not exists public.assembly_bills (
  bill_id            text primary key,
  source             text not null default 'national_assembly',
  age                integer,
  bill_no            text,
  bill_name          text,
  proposer           text,
  propose_date       date,
  committee          text,
  process_result     text,
  detail_link        text,
  memo               text,
  all_document_count      integer default 0,
  selected_document_count integer default 0,
  -- 결과 라벨 (판례 학습용)
  has_cost_estimate       boolean default false,
  has_non_attachment      boolean default false,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create index if not exists assembly_bills_has_cost_estimate_idx
  on public.assembly_bills (has_cost_estimate);
create index if not exists assembly_bills_has_non_attachment_idx
  on public.assembly_bills (has_non_attachment);

-- ============================================================
-- 2. 문서 메타데이터
--    text_extract_status: success | empty_text | failed | unsupported_hwp | ocr_required
-- ============================================================
create table if not exists public.assembly_documents (
  id                   bigserial primary key,
  bill_id              text not null references public.assembly_bills(bill_id) on delete cascade,
  bill_no              text,
  bill_name            text,
  source               text not null default 'national_assembly',
  document_name        text,
  document_type        text not null,   -- bill_text | cost_estimate | non_attachment_reason
  file_type            text,            -- pdf | hwp | hwpx
  source_url           text,
  local_path           text,
  storage_bucket       text,
  storage_path         text,            -- national_assembly/{age}/{bill_no}/{document_type}/{filename}
  -- 텍스트 추출 상태
  text_extract_status  text default 'pending',
  -- success | empty_text | failed | unsupported_hwp | ocr_required
  ocr_required         boolean default false,
  -- 파일 가용성
  pdf_available        boolean default false,
  hwp_available        boolean default false,
  fallback_required    boolean default false,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique (bill_id, document_type, document_name, file_type, source_url)
);

create index if not exists assembly_documents_bill_id_idx
  on public.assembly_documents (bill_id);

create index if not exists assembly_documents_doc_type_idx
  on public.assembly_documents (document_type);

create index if not exists assembly_documents_extract_status_idx
  on public.assembly_documents (text_extract_status);

-- ============================================================
-- 3. 수집/처리 상태 관리
--    job_type: download | text_extract | embedding | upload
--    status:   pending | running | done | failed
-- ============================================================
create table if not exists public.assembly_ingestion_jobs (
  id            bigserial primary key,
  bill_id       text references public.assembly_bills(bill_id) on delete cascade,
  document_id   bigint references public.assembly_documents(id) on delete cascade,
  job_type      text not null,
  status        text not null default 'pending',
  error_message text,
  metadata      jsonb,
  started_at    timestamptz,
  completed_at  timestamptz,
  created_at    timestamptz not null default now()
);

create index if not exists ingestion_jobs_bill_id_idx
  on public.assembly_ingestion_jobs (bill_id);

create index if not exists ingestion_jobs_status_idx
  on public.assembly_ingestion_jobs (status);

create index if not exists ingestion_jobs_type_status_idx
  on public.assembly_ingestion_jobs (job_type, status);

-- ============================================================
-- 4. 벡터 검색용 Chunk
--    hash_vector 제거 (실서비스 불필요)
--    age/committee/propose_date/storage_path 추가 (필터링용)
-- ============================================================
create table if not exists public.assembly_chunks (
  chunk_id      text primary key,
  bill_id       text not null references public.assembly_bills(bill_id) on delete cascade,
  document_id   bigint references public.assembly_documents(id) on delete set null,
  bill_no       text,
  bill_name     text,
  age           integer,              -- 대수 필터링
  committee     text,                 -- 위원회 필터링
  propose_date  date,                 -- 날짜 필터링
  source        text not null default 'national_assembly',
  document_name text,
  document_type text not null,
  storage_path  text,                 -- 원본 파일 역추적
  chunk_index   integer not null,
  content       text not null,
  embedding     extensions.vector(1536),  -- OpenAI text-embedding-3-small
  created_at    timestamptz not null default now()
);

-- HNSW 인덱스 (IVFFlat 대체 - 소규모 데이터에 적합)
create index if not exists assembly_chunks_embedding_idx
  on public.assembly_chunks
  using hnsw (embedding vector_cosine_ops);

create index if not exists assembly_chunks_bill_id_idx
  on public.assembly_chunks (bill_id);

create index if not exists assembly_chunks_age_idx
  on public.assembly_chunks (age);

create index if not exists assembly_chunks_doc_type_idx
  on public.assembly_chunks (document_type);

-- pg_trgm 기반 한국어 키워드 보조 검색
create index if not exists assembly_chunks_content_trgm_idx
  on public.assembly_chunks using gin (content gin_trgm_ops);

-- ============================================================
-- 5. 비용 유발 조문 분석 결과
--    의안원문에서 추출한 조문별 비용 유발 판단 결과
--    assembly_chunks와 분리 (분석 결과 vs 검색용 chunk)
--    trigger_type: 직접지원 | 사업수행 | 조직설치 | 위탁대행 | 시설구축 | 대상확대 | 의무부과
--    obligation_strength: mandatory | semi_mandatory | discretionary | aspirational
--    status: candidate | confirmed | rejected
-- ============================================================
create table if not exists public.bill_cost_triggers (
  id                    bigserial primary key,
  bill_id               text not null references public.assembly_bills(bill_id) on delete cascade,
  document_id           bigint references public.assembly_documents(id) on delete set null,
  bill_no               text,
  article_no            text,          -- "제7조"
  article_title         text,          -- "위탁 및 대행"
  article_text          text not null,
  cost_trigger          boolean not null default false,
  trigger_type          text,          -- 직접지원 | 사업수행 | 조직설치 | 위탁대행 | 시설구축 | 대상확대 | 의무부과
  obligation_strength   text,          -- mandatory | semi_mandatory | discretionary | aspirational
  budget_clause         boolean default false,   -- "예산의 범위에서" 단서 여부
  existing_program_check text,         -- 기존 사업 흡수 가능 여부 메모
  overlap_type          text,          -- 대상자 중복 유형
  committee_change_type text,          -- 신설 | 위원추가 | 명칭변경 | 통합폐지
  cost_items            jsonb,         -- ["위탁운영비", "인건비", "사업관리비"]
  confidence            numeric(4,3),  -- 0.000 ~ 1.000
  status                text not null default 'candidate',
  reason                text,
  -- 유사 조문 의미 검색용 embedding
  article_embedding     extensions.vector(1536),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

create index if not exists bill_cost_triggers_bill_id_idx
  on public.bill_cost_triggers (bill_id);

create index if not exists bill_cost_triggers_trigger_type_idx
  on public.bill_cost_triggers (trigger_type);

create index if not exists bill_cost_triggers_cost_trigger_idx
  on public.bill_cost_triggers (cost_trigger);

-- 유사 비용유발 조문 의미 검색
create index if not exists bill_cost_triggers_embedding_idx
  on public.bill_cost_triggers
  using hnsw (article_embedding vector_cosine_ops);

-- ============================================================
-- 6. 비용추계서 TAG 구조화 결과
-- ============================================================

-- ============================================================
-- 8. KOSIS 통계 후보 변수 (cost_estimate_variables FK 참조 때문에 먼저 생성)
-- ============================================================
create table if not exists public.kosis_stat_candidates (
  variable_key          text primary key,
  candidate_source      text,
  matched_keywords      jsonb,
  used_in_documents     integer default 0,
  example_bills         jsonb,
  kosis_mapping_status  text default 'needs_mapping',
  -- needs_mapping | mapped | verified
  kosis_table_id        text,
  kosis_item_id         text,
  notes                 text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

-- 6-1. 비용추계서 1건의 구조화 상태
--    status: structured_candidate | needs_review | reviewed | rejected
create table if not exists public.cost_estimate_structures (
  id             bigserial primary key,
  bill_id        text not null references public.assembly_bills(bill_id) on delete cascade,
  document_id    bigint references public.assembly_documents(id) on delete set null,
  bill_no        text,
  bill_name      text,
  age            integer,
  committee      text,
  propose_date   date,
  total_years    integer default 5,   -- 추계 연수 (보통 5개년)
  status         text not null default 'structured_candidate',
  reviewer_notes text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists cost_estimate_structures_bill_id_idx
  on public.cost_estimate_structures (bill_id);

create index if not exists cost_estimate_structures_status_idx
  on public.cost_estimate_structures (status);

-- 6-2. 비용항목 (인건비, 운영비, 지원금 등)
create table if not exists public.cost_estimate_items (
  id              bigserial primary key,
  structure_id    bigint not null references public.cost_estimate_structures(id) on delete cascade,
  bill_id         text not null references public.assembly_bills(bill_id) on delete cascade,
  item_category   text,               -- 인건비 | 운영비 | 사업비 | 지원금 | 위탁비
  item_name       text not null,      -- "에너지 모니터링 시스템 구축"
  item_order      integer,
  trigger_ref     text,               -- 근거 조문 ("제7조 제1항")
  notes           text,
  created_at      timestamptz not null default now()
);

create index if not exists cost_estimate_items_structure_id_idx
  on public.cost_estimate_items (structure_id);

-- 6-3. 산출 변수 (대상자, 단가, 횟수 등)
--    variable_type: target_count | unit_cost | frequency | rate | period | other
create table if not exists public.cost_estimate_variables (
  id                   bigserial primary key,
  item_id              bigint not null references public.cost_estimate_items(id) on delete cascade,
  structure_id         bigint not null references public.cost_estimate_structures(id) on delete cascade,
  variable_type        text not null,  -- target_count | unit_cost | frequency | rate | period | other
  variable_name        text not null,  -- "등록장애인 수"
  variable_value       numeric,        -- 추출된 수치
  variable_unit        text,           -- "명", "원/시간", "%"
  kosis_variable_key   text references public.kosis_stat_candidates(variable_key),
  -- KOSIS 후보와 연결
  source_text          text,           -- 원문에서 추출한 근거 텍스트
  needs_kosis_lookup   boolean default false,
  notes                text,
  created_at           timestamptz not null default now()
);

create index if not exists cost_estimate_variables_item_id_idx
  on public.cost_estimate_variables (item_id);

create index if not exists cost_estimate_variables_kosis_key_idx
  on public.cost_estimate_variables (kosis_variable_key);

-- 6-4. 연도별 금액
create table if not exists public.cost_estimate_amounts (
  id              bigserial primary key,
  item_id         bigint not null references public.cost_estimate_items(id) on delete cascade,
  structure_id    bigint not null references public.cost_estimate_structures(id) on delete cascade,
  year_label      text not null,      -- "1차년도" | "2차년도" | ... | "합계"
  year_offset     integer,            -- 0=1차년도, 1=2차년도, ...
  amount_thousand integer,            -- 천원 단위
  formula_text    text,               -- "대상자 × 단가 × 12개월"
  is_total        boolean default false,
  notes           text,
  created_at      timestamptz not null default now()
);

create index if not exists cost_estimate_amounts_item_id_idx
  on public.cost_estimate_amounts (item_id);

create index if not exists cost_estimate_amounts_structure_id_idx
  on public.cost_estimate_amounts (structure_id);

-- ============================================================
-- 7. 미첨부 사유서 유형 분류
--    reason_type: A(비용없음) | B(추계곤란) | C(기존예산흡수)
--    status: candidate | confirmed | rejected
-- ============================================================
create table if not exists public.non_attachment_reason_classifications (
  id             bigserial primary key,
  bill_id        text not null references public.assembly_bills(bill_id) on delete cascade,
  document_id    bigint references public.assembly_documents(id) on delete set null,
  bill_no        text,
  reason_type    text not null,       -- A | B | C
  -- A: 비용을 수반하지 않음
  -- B: 추계가 기술적으로 곤란함
  -- C: 기존 예산 범위 내 집행 가능
  reason_text    text,                -- 원문 사유 텍스트
  evidence_text  text,                -- 근거 문구
  confidence     numeric(4,3),
  status         text not null default 'candidate',
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists non_attachment_bill_id_idx
  on public.non_attachment_reason_classifications (bill_id);

create index if not exists non_attachment_reason_type_idx
  on public.non_attachment_reason_classifications (reason_type);

