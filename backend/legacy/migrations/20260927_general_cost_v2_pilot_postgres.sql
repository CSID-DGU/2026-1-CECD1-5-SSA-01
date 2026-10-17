-- PostgreSQL/Supabase projection of the isolated SQLite v2 pilot.
-- Core IDs and column names intentionally match the migration JSONL bundle.

create extension if not exists vector with schema extensions;

create table if not exists public.general_cost_v2_schema_meta (
  schema_version text primary key,
  cost_domain text not null,
  created_at timestamptz not null,
  notes text not null default ''
);

create table if not exists public.general_cost_v2_ingestion_runs (
  run_id text primary key,
  pipeline_version text not null,
  cost_nature text not null,
  source_mode text not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  status text not null check (status in ('running', 'completed', 'failed')),
  documents_requested integer not null default 0,
  metrics_json jsonb not null default '{}'::jsonb
);

create table if not exists public.general_cost_v2_ingestion_stages (
  run_id text not null references public.general_cost_v2_ingestion_runs(run_id) on delete cascade,
  stage_name text not null,
  duration_ms integer not null,
  record_count integer not null default 0,
  failure_count integer not null default 0,
  details_json jsonb not null default '{}'::jsonb,
  primary key (run_id, stage_name)
);

create table if not exists public.general_cost_v2_dataset_splits (
  bill_id text primary key,
  bill_no text not null unique,
  split text not null check (split in ('development', 'validation_holdout')),
  split_version text not null,
  assigned_at timestamptz not null
);

create table if not exists public.general_cost_v2_documents (
  document_id text primary key,
  bill_id text not null,
  bill_no text not null,
  bill_name text not null,
  age integer not null,
  proposer text,
  propose_date date,
  committee text,
  document_type text not null check (document_type in ('cost_estimate', 'bill_text')),
  source_path text not null,
  source_url text,
  original_name text,
  sha256 text not null,
  page_count integer not null,
  dataset_split text not null check (dataset_split = 'development'),
  extraction_status text not null check (extraction_status in ('parsed', 'failed')),
  extraction_version text not null,
  run_id text not null references public.general_cost_v2_ingestion_runs(run_id),
  unique (bill_id, document_type),
  unique (sha256, document_type)
);

create table if not exists public.general_cost_v2_document_chunks (
  chunk_id text primary key,
  document_id text not null references public.general_cost_v2_documents(document_id) on delete cascade,
  page_no integer not null,
  chunk_index integer not null,
  content text not null,
  content_sha256 text not null,
  parser_version text not null,
  search_tsv tsvector generated always as (to_tsvector('simple', coalesce(content, ''))) stored,
  unique (document_id, page_no, chunk_index)
);

create table if not exists public.general_cost_v2_chunk_embeddings (
  chunk_id text primary key references public.general_cost_v2_document_chunks(chunk_id) on delete cascade,
  embedding_model text not null,
  dimensions integer not null check (dimensions = 1536),
  embedding extensions.vector(1536) not null
);

create table if not exists public.general_cost_v2_formula_templates (
  formula_key text primary key,
  cost_natures_json jsonb not null,
  label text not null,
  expression_text text not null,
  required_variables_json jsonb not null,
  optional_variables_json jsonb not null,
  recurrence text not null,
  applicability_json jsonb not null,
  template_version text not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'deprecated'))
);

create table if not exists public.general_cost_v2_cost_items (
  item_id text primary key,
  source_item_key text not null unique,
  document_id text not null references public.general_cost_v2_documents(document_id) on delete cascade,
  bill_id text not null,
  bill_no text not null,
  bill_name text not null,
  item_name text not null,
  trigger_ref text,
  cost_nature text not null,
  component text not null,
  mechanism text not null,
  priced_scopes_json jsonb not null default '[]'::jsonb,
  implementing_agencies_json jsonb not null default '[]'::jsonb,
  policy_domains_json jsonb not null default '[]'::jsonb,
  recurrence text,
  classification_confidence text not null,
  classification_reason text not null,
  extraction_origin text not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected')),
  quality_flags_json jsonb not null default '[]'::jsonb,
  search_tsv tsvector generated always as (
    to_tsvector(
      'simple',
      coalesce(item_name, '') || ' ' || coalesce(bill_name, '') || ' ' ||
      coalesce(mechanism, '') || ' ' || coalesce(component, '')
    )
  ) stored
);

create table if not exists public.general_cost_v2_item_formula_links (
  item_id text not null references public.general_cost_v2_cost_items(item_id) on delete cascade,
  formula_key text not null,
  selection_status text not null check (selection_status in ('ready', 'partial', 'unresolved')),
  missing_variables_json jsonb not null default '[]'::jsonb,
  selection_reason text not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected')),
  primary key (item_id, formula_key)
);

create table if not exists public.general_cost_v2_variables (
  variable_id text primary key,
  item_id text not null references public.general_cost_v2_cost_items(item_id) on delete cascade,
  canonical_key text,
  raw_name text not null,
  raw_type text,
  raw_value numeric,
  raw_unit text,
  normalized_value numeric,
  normalized_unit text,
  basis_year integer,
  source_class text not null,
  transfer_policy text not null,
  mapping_confidence text not null,
  normalization_status text not null,
  unit_status text not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected')),
  quality_flags_json jsonb not null default '[]'::jsonb
);

create table if not exists public.general_cost_v2_amount_observations (
  observation_id text primary key,
  item_id text not null references public.general_cost_v2_cost_items(item_id) on delete cascade,
  year_label text,
  year_offset integer,
  amount_thousand bigint,
  formula_text text,
  is_total boolean not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected'))
);

create table if not exists public.general_cost_v2_evidence_links (
  evidence_link_id text primary key,
  entity_type text not null check (entity_type in ('item', 'formula', 'variable', 'amount')),
  entity_id text not null,
  chunk_id text references public.general_cost_v2_document_chunks(chunk_id) on delete set null,
  page_no integer,
  locator_query text not null,
  quote_text text not null,
  locator_method text not null check (locator_method in ('exact', 'fuzzy', 'unresolved')),
  locator_score double precision not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected')),
  unique (entity_type, entity_id, quote_text)
);

create table if not exists public.general_cost_v2_item_embeddings (
  item_id text primary key references public.general_cost_v2_cost_items(item_id) on delete cascade,
  embedding_model text not null,
  dimensions integer not null check (dimensions = 1536),
  embedding extensions.vector(1536) not null,
  embedding_text text not null
);

create index if not exists general_cost_v2_documents_bill_idx
  on public.general_cost_v2_documents (bill_id, bill_no);
create index if not exists general_cost_v2_document_chunks_fts_idx
  on public.general_cost_v2_document_chunks using gin (search_tsv);
create index if not exists general_cost_v2_cost_items_route_idx
  on public.general_cost_v2_cost_items (cost_nature, mechanism, component, review_status);
create index if not exists general_cost_v2_cost_items_fts_idx
  on public.general_cost_v2_cost_items using gin (search_tsv);
create index if not exists general_cost_v2_variables_lookup_idx
  on public.general_cost_v2_variables (canonical_key, transfer_policy, basis_year, review_status);
create index if not exists general_cost_v2_amounts_item_idx
  on public.general_cost_v2_amount_observations (item_id, year_offset, is_total);
create index if not exists general_cost_v2_evidence_entity_idx
  on public.general_cost_v2_evidence_links (entity_type, entity_id);
create index if not exists general_cost_v2_item_embedding_hnsw_idx
  on public.general_cost_v2_item_embeddings
  using hnsw (embedding extensions.vector_cosine_ops);
create index if not exists general_cost_v2_chunk_embedding_hnsw_idx
  on public.general_cost_v2_chunk_embeddings
  using hnsw (embedding extensions.vector_cosine_ops);

