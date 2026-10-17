-- Organization/administration formula and variable evidence sidecar v1.
--
-- Additive only: the existing assembly/TAG tables remain the immutable raw
-- layer.  This schema separates (1) canonical variable meaning, (2) reusable
-- formula structure, (3) extracted precedent evidence, and (4) a target-time
-- resolution audit trail.  Applying this migration does not backfill data and
-- does not make any candidate value automatically transferable.

create table if not exists public.org_admin_variable_definitions (
  canonical_key          text primary key,
  label                  text not null,
  description            text not null,
  value_kind             text not null
    check (value_kind in (
      'count', 'unit_price', 'rate', 'amount', 'duration', 'area',
      'timing', 'boolean', 'profile', 'workload'
    )),
  canonical_unit         text,
  allowed_components     text[] not null default '{}',
  search_strategy        jsonb not null default '{}'::jsonb,
  definition_version     text not null,
  active                 boolean not null default true,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create table if not exists public.org_admin_formula_templates (
  formula_key            text primary key,
  route                  text not null
    check (route in ('organization', 'committee')),
  component              text not null,
  label                  text not null,
  expression_text        text not null,
  expression_ast         jsonb not null,
  required_variables     text[] not null,
  optional_variables     text[] not null default '{}',
  recurrence             text not null
    check (recurrence in ('annual', 'one_time', 'scheduled', 'mixed')),
  applicability          jsonb not null default '{}'::jsonb,
  source_refs            jsonb not null default '[]'::jsonb,
  template_version       text not null,
  review_status          text not null default 'draft'
    check (review_status in ('draft', 'verified', 'deprecated')),
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create table if not exists public.org_admin_item_profiles (
  profile_key            text primary key,
  source_item_key        text not null unique,
  raw_structure_key      text,
  structure_id           bigint references public.cost_estimate_structures(id) on delete set null,
  bill_id                text references public.assembly_bills(bill_id) on delete cascade,
  item_name              text not null,
  item_category          text,
  route                  text not null
    check (route in ('organization', 'committee')),
  component              text not null
    check (component in (
      'personnel', 'employer_contribution', 'basic_expense', 'space',
      'asset', 'operating_expense', 'committee_meeting',
      'committee_operation', 'other'
    )),
  classification_confidence text not null
    check (classification_confidence in ('high', 'medium', 'low')),
  classification_reason  text not null,
  subject_name           text,
  subject_type           text,
  jurisdiction           text not null default 'unknown'
    check (jurisdiction in ('central', 'local', 'judicial', 'legislative', 'unknown')),
  organization_form      text,
  parent_authority       text,
  function_class         text,
  location_scope         text,
  classifier_version     text not null,
  review_status          text not null default 'candidate'
    check (review_status in ('candidate', 'verified', 'rejected')),
  raw_attributes         jsonb not null default '{}'::jsonb,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create table if not exists public.org_admin_variable_evidence (
  evidence_key           text primary key,
  profile_key            text not null references public.org_admin_item_profiles(profile_key) on delete cascade,
  raw_variable_fingerprint text not null,
  canonical_key          text references public.org_admin_variable_definitions(canonical_key) on delete set null,
  raw_variable_type      text,
  raw_variable_name      text not null,
  raw_value              numeric,
  raw_unit               text,
  normalized_value       numeric,
  normalized_unit        text,
  source_class           text not null
    check (source_class in (
      'bill_or_target_document', 'official_standard', 'official_forecast',
      'official_statistics', 'budget_or_settlement', 'similar_case',
      'analyst_assumption', 'unclassified_source', 'missing'
    )),
  transfer_policy        text not null
    check (transfer_policy in (
      'target_specific', 'versioned_official', 'scope_check_required',
      'comparable_only', 'review_required', 'do_not_transfer'
    )),
  source_document_id     bigint references public.assembly_documents(id) on delete set null,
  source_ref             text,
  source_text            text not null default '',
  basis_year_candidates  integer[] not null default '{}',
  basis_year             integer,
  valid_from             date,
  valid_to               date,
  mapping_confidence     text not null
    check (mapping_confidence in ('high', 'medium', 'low')),
  normalization_status   text not null
    check (normalization_status in (
      'mapped', 'mapped_missing_value', 'mapped_missing_unit', 'unmapped'
    )),
  unit_status            text not null default 'not_normalized'
    check (unit_status in ('normalized', 'ambiguous', 'missing', 'not_normalized')),
  review_status          text not null default 'candidate'
    check (review_status in ('candidate', 'verified', 'rejected')),
  quality_flags          jsonb not null default '[]'::jsonb,
  transform_version      text not null,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  unique (profile_key, raw_variable_fingerprint)
);

create table if not exists public.org_admin_resolution_runs (
  run_key                text primary key,
  target_bill_id         text references public.assembly_bills(bill_id) on delete set null,
  target_event_key       text,
  formula_key            text references public.org_admin_formula_templates(formula_key) on delete set null,
  as_of_date             date not null,
  target_context         jsonb not null,
  resolver_version       text not null,
  status                 text not null default 'candidate_search'
    check (status in ('candidate_search', 'resolved', 'review_required', 'failed')),
  created_at             timestamptz not null default now(),
  completed_at           timestamptz
);

create table if not exists public.org_admin_resolution_candidates (
  run_key                text not null references public.org_admin_resolution_runs(run_key) on delete cascade,
  canonical_key          text not null references public.org_admin_variable_definitions(canonical_key),
  evidence_key           text not null references public.org_admin_variable_evidence(evidence_key) on delete cascade,
  hard_gate_pass         boolean not null default false,
  gate_results           jsonb not null default '{}'::jsonb,
  rank_features          jsonb not null default '{}'::jsonb,
  rank_score             numeric,
  selected               boolean not null default false,
  selection_reason       text,
  created_at             timestamptz not null default now(),
  primary key (run_key, canonical_key, evidence_key)
);

create table if not exists public.org_admin_variable_resolutions (
  run_key                text not null references public.org_admin_resolution_runs(run_key) on delete cascade,
  canonical_key          text not null references public.org_admin_variable_definitions(canonical_key),
  selected_evidence_key  text references public.org_admin_variable_evidence(evidence_key) on delete set null,
  resolved_value         numeric,
  resolved_unit          text,
  resolution_status      text not null
    check (resolution_status in ('confirmed', 'derived', 'borrowed', 'missing')),
  resolution_reason      text not null,
  assumption_text        text,
  requires_review        boolean not null default true,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  primary key (run_key, canonical_key)
);

create index if not exists org_admin_profiles_lookup_idx
  on public.org_admin_item_profiles (route, component, review_status);
create index if not exists org_admin_profiles_bill_idx
  on public.org_admin_item_profiles (bill_id);
create index if not exists org_admin_profiles_context_idx
  on public.org_admin_item_profiles
  (jurisdiction, organization_form, function_class);
create index if not exists org_admin_evidence_lookup_idx
  on public.org_admin_variable_evidence
  (canonical_key, transfer_policy, review_status, basis_year);
create index if not exists org_admin_evidence_profile_idx
  on public.org_admin_variable_evidence (profile_key);
create index if not exists org_admin_evidence_quality_idx
  on public.org_admin_variable_evidence
  (normalization_status, unit_status, mapping_confidence);
create index if not exists org_admin_candidates_selected_idx
  on public.org_admin_resolution_candidates (run_key, selected)
  where selected = true;

-- Canonical definitions.  Search order is policy, not a learned score:
-- target bill -> current official standard -> same subject actual -> comparable
-- official case -> unresolved/HITL.
insert into public.org_admin_variable_definitions (
  canonical_key, label, description, value_kind, canonical_unit,
  allowed_components, search_strategy, definition_version
)
values
  ('headcount', '순증 인원', '신설·증원되는 직원의 수', 'count', 'person',
   array['personnel','asset','basic_expense'],
   '{"priority":["bill","official_plan","same_subject","similar_case"],"hard_gates":["staff_scope"]}'::jsonb, 'org-admin-vars-v1'),
  ('headcount_by_grade', '직급별 순증 인원', '직급별 신설·증원 인원', 'profile', 'person_by_grade',
   array['personnel'],
   '{"priority":["bill","official_plan","same_subject","similar_case"],"hard_gates":["pay_system","grade_system"]}'::jsonb, 'org-admin-vars-v1'),
  ('salary_by_grade', '직급별 1인당 보수', '직급별 연간 1인당 보수', 'unit_price', 'KRW/person/year',
   array['personnel'],
   '{"priority":["official_standard","same_subject_budget","similar_case"],"hard_gates":["pay_system","grade","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('salary_per_person', '1인당 보수', '평균 또는 특정 직급의 1인당 보수', 'unit_price', 'KRW/person/year',
   array['personnel'],
   '{"priority":["official_standard","same_subject_budget","similar_case"],"hard_gates":["pay_system","time_basis","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('total_salary', '보수 총액', '기간별 전체 보수 총액', 'amount', 'KRW/year',
   array['personnel','basic_expense','employer_contribution'],
   '{"priority":["derived","same_subject_budget","similar_case"],"hard_gates":["scope","time_basis"]}'::jsonb, 'org-admin-vars-v1'),
  ('employer_contribution_rate', '기관부담률', '보수에 대한 연금·보험 등 기관부담 비율', 'rate', 'ratio',
   array['employer_contribution','personnel'],
   '{"priority":["official_standard"],"hard_gates":["pay_system","validity_date"]}'::jsonb, 'org-admin-vars-v1'),
  ('wage_growth_rate', '보수상승률', '연도별 공무원 보수·임금 상승률', 'rate', 'ratio/year',
   array['personnel'],
   '{"priority":["official_forecast"],"hard_gates":["forecast_vintage","year"]}'::jsonb, 'org-admin-vars-v1'),
  ('basic_expense_ratio', '기본경비 비율', '인건비 대비 기본경비 비율', 'rate', 'ratio',
   array['basic_expense','personnel'],
   '{"priority":["same_subject_actual","similar_case"],"hard_gates":["organization_form","expense_scope","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('basic_expense_per_person', '1인당 기본경비', '연간 1인당 기본경비', 'unit_price', 'KRW/person/year',
   array['basic_expense'],
   '{"priority":["same_subject_actual","similar_case"],"hard_gates":["organization_form","expense_scope","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('basic_expense_amount', '기본경비 총액', '기관 단위 기본경비 총액', 'amount', 'KRW/year',
   array['basic_expense'],
   '{"priority":["same_subject_actual","similar_case"],"hard_gates":["same_subject_or_scale","expense_scope","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('asset_unit_price_per_person', '1인당 자산취득비', '신규 인력 1인당 초기 자산취득 단가', 'unit_price', 'KRW/person',
   array['asset','personnel'],
   '{"priority":["official_standard","official_forecast","similar_case"],"hard_gates":["organization_type","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('asset_amount', '자산취득비 총액', '자산취득비 총액', 'amount', 'KRW',
   array['asset'],
   '{"priority":["bill","same_subject_plan","similar_case"],"hard_gates":["asset_scope","scale"]}'::jsonb, 'org-admin-vars-v1'),
  ('required_area', '필요 면적', '사무공간의 필요 전용·임차 면적', 'area', 'm2',
   array['space'],
   '{"priority":["bill","official_standard","same_subject","similar_case"],"hard_gates":["area_scope","headcount"]}'::jsonb, 'org-admin-vars-v1'),
  ('rent_unit_price', '면적당 임차료', '지역·용도별 면적당 월 임차료', 'unit_price', 'KRW/m2/month',
   array['space'],
   '{"priority":["official_statistics","same_subject_contract","similar_case"],"hard_gates":["region","building_use","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('rent_duration_months', '임차 개월', '임차료가 발생하는 개월 수', 'duration', 'month',
   array['space'],
   '{"priority":["bill","effective_date","analyst_schedule"],"hard_gates":["estimate_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('management_fee_ratio', '임차료 대비 관리비 비율', '임차료를 기준으로 산정한 관리비 비율', 'rate', 'ratio',
   array['space'],
   '{"priority":["same_subject_actual","similar_case"],"hard_gates":["building_use","expense_scope"]}'::jsonb, 'org-admin-vars-v1'),
  ('paid_member_count', '수당 지급대상 위원 수', '총원 중 회의수당 지급 대상 위원 수', 'count', 'person',
   array['committee_meeting','committee_operation'],
   '{"priority":["bill","same_committee_actual","verified_precedent"],"hard_gates":["public_official_exclusion","committee_structure"]}'::jsonb, 'org-admin-vars-v1'),
  ('committee_member_count', '위원회 총원', '위원장을 포함한 법정 총원', 'count', 'person',
   array['committee_meeting','committee_operation'],
   '{"priority":["bill","current_law"],"hard_gates":["cap_vs_exact"]}'::jsonb, 'org-admin-vars-v1'),
  ('committee_instance_count', '위원회 설치 개수', '중앙·지역·기관별로 반복 설치되는 위원회의 수', 'count', 'instance',
   array['committee_meeting','committee_operation'],
   '{"priority":["bill","official_statistics","current_law"],"hard_gates":["jurisdiction_scope","mandatory_installation","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('annual_meetings', '연간 회의 횟수', '위원회의 연간 개최 횟수', 'count', 'meeting/year',
   array['committee_meeting','committee_operation'],
   '{"priority":["bill","same_committee_actual","same_function_actual","verified_precedent"],"hard_gates":["lifecycle","function_class","workload"]}'::jsonb, 'org-admin-vars-v1'),
  ('meeting_unit_price', '1인 1회당 회의수당', '회의참석·안건검토비를 포함한 1인 1회당 단가', 'unit_price', 'KRW/person/meeting',
   array['committee_meeting','committee_operation'],
   '{"priority":["official_standard","same_authority_guideline","verified_precedent"],"hard_gates":["authority","payment_scope","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('committee_operating_amount', '위원회 운영비', '위원회 단위 연간 또는 회당 운영비', 'amount', 'KRW',
   array['committee_operation'],
   '{"priority":["same_committee_actual","verified_precedent"],"hard_gates":["measurement_scope","committee_structure"]}'::jsonb, 'org-admin-vars-v1'),
  ('annual_operating_amount', '연간 운영비', '조직 단위 연간 운영비 총액', 'amount', 'KRW/year',
   array['operating_expense','committee_operation'],
   '{"priority":["same_subject_actual","similar_case"],"hard_gates":["scope","scale","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('price_growth_rate', '물가상승률', '비인건비 항목에 적용하는 물가상승률', 'rate', 'ratio/year',
   array['basic_expense','space','asset','operating_expense'],
   '{"priority":["official_forecast"],"hard_gates":["forecast_vintage","year"]}'::jsonb, 'org-admin-vars-v1'),
  ('duration', '적용 기간', '존속·활동·운영 기간', 'duration', null,
   array['personnel','space','asset','committee_operation'],
   '{"priority":["bill","effective_date","analyst_schedule"],"hard_gates":["unit"]}'::jsonb, 'org-admin-vars-v1'),
  ('start_timing', '발생 시점', '비용이 최초 발생하는 연도·월', 'timing', null,
   array['personnel','space','asset','committee_operation'],
   '{"priority":["bill","effective_date"],"hard_gates":["date_precision"]}'::jsonb, 'org-admin-vars-v1'),
  ('annual_case_volume', '연간 안건량', '심사·조정·처리할 연간 안건 수', 'workload', 'case/year',
   array['committee_meeting','committee_operation'],
   '{"priority":["official_statistics","same_function_actual"],"hard_gates":["case_definition","basis_year"]}'::jsonb, 'org-admin-vars-v1'),
  ('cases_per_meeting', '회당 처리안건', '회의 1회당 처리하는 평균 안건 수', 'workload', 'case/meeting',
   array['committee_meeting','committee_operation'],
   '{"priority":["same_committee_actual","same_function_actual"],"hard_gates":["function_class","process"]}'::jsonb, 'org-admin-vars-v1')
on conflict (canonical_key) do update set
  label = excluded.label,
  description = excluded.description,
  value_kind = excluded.value_kind,
  canonical_unit = excluded.canonical_unit,
  allowed_components = excluded.allowed_components,
  search_strategy = excluded.search_strategy,
  definition_version = excluded.definition_version,
  updated_at = now();

-- These are executable structures but remain draft until domain review.
insert into public.org_admin_formula_templates (
  formula_key, route, component, label, expression_text, expression_ast,
  required_variables, optional_variables, recurrence, applicability,
  source_refs, template_version, review_status
)
values
  ('ORG_PERSONNEL_GRADE_V1', 'organization', 'personnel', '직급별 인건비',
   'Σ(직급별 순증인원 × 직급별 1인당 보수)',
   '{"op":"sum_product","left":"headcount_by_grade","right":"salary_by_grade"}'::jsonb,
   array['headcount_by_grade','salary_by_grade'], array['wage_growth_rate'],
   'annual', '{"requires":"compatible grade and pay systems"}'::jsonb,
   '["NABO bill cost-estimation practice guide"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('ORG_PERSONNEL_AVERAGE_V1', 'organization', 'personnel', '평균단가 인건비',
   '순증인원 × 1인당 보수',
   '{"op":"multiply","args":["headcount","salary_per_person"]}'::jsonb,
   array['headcount','salary_per_person'], array['wage_growth_rate'],
   'annual', '{"fallback_for":"grade mix unavailable","requires":"compatible pay and time basis"}'::jsonb,
   '["NABO bill cost-estimation practice guide"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('ORG_EMPLOYER_CONTRIBUTION_V1', 'organization', 'employer_contribution', '기관부담금',
   '보수 총액 × 기관부담률',
   '{"op":"multiply","args":["total_salary","employer_contribution_rate"]}'::jsonb,
   array['total_salary','employer_contribution_rate'], array[]::text[], 'annual',
   '{"requires":"same pay system and contribution scope"}'::jsonb,
   '["NABO organization-establishment examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('ORG_BASIC_EXPENSE_RATIO_V1', 'organization', 'basic_expense', '인건비 비율형 기본경비',
   '보수 총액 × 인건비 대비 기본경비 비율',
   '{"op":"multiply","args":["total_salary","basic_expense_ratio"]}'::jsonb,
   array['total_salary','basic_expense_ratio'], array['price_growth_rate'], 'annual',
   '{"requires":"same expense scope and comparable organization form"}'::jsonb,
   '["NABO organization-establishment examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('ORG_BASIC_EXPENSE_PER_PERSON_V1', 'organization', 'basic_expense', '1인당 기본경비',
   '순증인원 × 1인당 기본경비',
   '{"op":"multiply","args":["headcount","basic_expense_per_person"]}'::jsonb,
   array['headcount','basic_expense_per_person'], array['price_growth_rate'], 'annual',
   '{"requires":"same expense scope and comparable organization form"}'::jsonb,
   '["NABO organization-establishment examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('ORG_ASSET_PER_PERSON_V1', 'organization', 'asset', '1인당 자산취득비',
   '순증인원 × 1인당 자산취득비',
   '{"op":"multiply","args":["headcount","asset_unit_price_per_person"]}'::jsonb,
   array['headcount','asset_unit_price_per_person'], array['price_growth_rate'], 'one_time',
   '{"requires":"newly equipped staff only"}'::jsonb,
   '["NABO organization-establishment examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('ORG_SPACE_RENT_V1', 'organization', 'space', '사무공간 임차료',
   '필요면적 × 면적당 월 임차료 × 임차개월',
   '{"op":"multiply","args":["required_area","rent_unit_price","rent_duration_months"]}'::jsonb,
   array['required_area','rent_unit_price','rent_duration_months'], array['price_growth_rate'], 'scheduled',
   '{"requires":"same region, building use and area scope"}'::jsonb,
   '["NABO organization-establishment examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('ORG_SPACE_MANAGEMENT_RATIO_V1', 'organization', 'space', '임차공간 관리비',
   '임차료 × 임차료 대비 관리비 비율',
   '{"op":"multiply","args":["derived.rent_amount","management_fee_ratio"]}'::jsonb,
   array['management_fee_ratio'], array['price_growth_rate'], 'annual',
   '{"requires":"rent amount from ORG_SPACE_RENT_V1 and compatible building use"}'::jsonb,
   '["NABO organization-establishment examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('COMMITTEE_MEETING_V1', 'committee', 'committee_meeting', '위원회 회의수당',
   '수당지급 위원 수 × 연간 회의횟수 × 1인 1회당 수당',
   '{"op":"multiply","args":["paid_member_count","annual_meetings","meeting_unit_price"]}'::jsonb,
   array['paid_member_count','annual_meetings','meeting_unit_price'], array[]::text[], 'annual',
   '{"requires":"paid-member scope and committee lifecycle verified"}'::jsonb,
   '["NABO committee cost-estimation examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('COMMITTEE_MULTI_INSTANCE_V1', 'committee', 'committee_meeting', '복수 위원회 회의수당',
   '위원회 설치 개수 × 수당지급 위원 수 × 연간 회의횟수 × 1인 1회당 수당',
   '{"op":"multiply","args":["committee_instance_count","paid_member_count","annual_meetings","meeting_unit_price"]}'::jsonb,
   array['committee_instance_count','paid_member_count','annual_meetings','meeting_unit_price'], array[]::text[], 'annual',
   '{"requires":"mandatory instance scope, paid-member scope and lifecycle verified"}'::jsonb,
   '["NABO multi-instance committee cost-estimation examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('ORG_OPERATING_DIRECT_V1', 'organization', 'operating_expense', '조직 연간 운영비',
   '대상 조직의 연간 운영비',
   '{"op":"identity","arg":"annual_operating_amount"}'::jsonb,
   array['annual_operating_amount'], array['price_growth_rate'], 'annual',
   '{"requires":"same organization scope or target-specific budget"}'::jsonb,
   '["NABO organization-establishment examples"]'::jsonb, 'org-admin-formulas-v1', 'draft'),
  ('COMMITTEE_OPERATING_DIRECT_V1', 'committee', 'committee_operation', '위원회 연간 운영비',
   '대상 위원회의 연간 운영비',
   '{"op":"identity","arg":"committee_operating_amount"}'::jsonb,
   array['committee_operating_amount'], array['price_growth_rate'], 'annual',
   '{"requires":"same committee and measurement scope"}'::jsonb,
   '["NABO committee cost-estimation examples"]'::jsonb, 'org-admin-formulas-v1', 'draft')
on conflict (formula_key) do update set
  label = excluded.label,
  expression_text = excluded.expression_text,
  expression_ast = excluded.expression_ast,
  required_variables = excluded.required_variables,
  optional_variables = excluded.optional_variables,
  applicability = excluded.applicability,
  source_refs = excluded.source_refs,
  template_version = excluded.template_version,
  updated_at = now();
