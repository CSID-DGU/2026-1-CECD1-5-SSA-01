-- General cost evidence DB v2 pilot (SQLite).
--
-- This pilot is deliberately isolated from the existing Supabase/TAG tables.
-- Every reusable assertion must point back to a source page, and every row
-- records its extraction/review state.  The schema can later be translated to
-- PostgreSQL + pgvector after the small-domain experiment is accepted.

pragma foreign_keys = on;

create table schema_meta (
  schema_version text primary key,
  cost_domain text not null,
  created_at text not null,
  notes text not null default ''
);

create table ingestion_runs (
  run_id text primary key,
  pipeline_version text not null,
  cost_nature text not null,
  source_mode text not null,
  started_at text not null,
  finished_at text,
  status text not null check (status in ('running', 'completed', 'failed')),
  documents_requested integer not null default 0,
  metrics_json text not null default '{}'
);

create table ingestion_stages (
  run_id text not null references ingestion_runs(run_id) on delete cascade,
  stage_name text not null,
  duration_ms integer not null,
  record_count integer not null default 0,
  failure_count integer not null default 0,
  details_json text not null default '{}',
  primary key (run_id, stage_name)
);

create table dataset_splits (
  bill_id text primary key,
  bill_no text not null unique,
  split text not null check (split in ('development', 'validation_holdout')),
  split_version text not null,
  assigned_at text not null
);

create table documents (
  document_id text primary key,
  bill_id text not null,
  bill_no text not null,
  bill_name text not null,
  age integer not null,
  proposer text,
  propose_date text,
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
  run_id text not null references ingestion_runs(run_id),
  unique (bill_id, document_type),
  unique (sha256, document_type)
);

create index documents_bill_idx on documents (bill_id, bill_no);
create index documents_type_idx on documents (document_type, propose_date);

create table document_chunks (
  chunk_id text primary key,
  document_id text not null references documents(document_id) on delete cascade,
  page_no integer not null,
  chunk_index integer not null,
  content text not null,
  content_sha256 text not null,
  parser_version text not null,
  unique (document_id, page_no, chunk_index)
);

create index document_chunks_document_idx on document_chunks (document_id, page_no);

create virtual table document_chunks_fts using fts5(
  chunk_id unindexed,
  content,
  tokenize = 'unicode61'
);

create table chunk_embeddings (
  chunk_id text primary key references document_chunks(chunk_id) on delete cascade,
  embedding_model text not null,
  dimensions integer not null,
  vector_json text not null
);

create table formula_templates (
  formula_key text primary key,
  cost_natures_json text not null,
  label text not null,
  expression_text text not null,
  required_variables_json text not null,
  optional_variables_json text not null,
  recurrence text not null,
  applicability_json text not null,
  template_version text not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'deprecated'))
);

create table cost_items (
  item_id text primary key,
  source_item_key text not null unique,
  document_id text not null references documents(document_id) on delete cascade,
  bill_id text not null,
  bill_no text not null,
  bill_name text not null,
  item_name text not null,
  trigger_ref text,
  cost_nature text not null check (cost_nature = 'goods_services'),
  component text not null,
  mechanism text not null,
  priced_scopes_json text not null default '[]',
  implementing_agencies_json text not null default '[]',
  policy_domains_json text not null default '[]',
  recurrence text,
  classification_confidence text not null,
  classification_reason text not null,
  extraction_origin text not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected')),
  quality_flags_json text not null default '[]'
);

create index cost_items_route_idx
  on cost_items (cost_nature, mechanism, component, review_status);
create index cost_items_bill_idx on cost_items (bill_id, bill_no);

create virtual table cost_items_fts using fts5(
  item_id unindexed,
  item_name,
  mechanism,
  component,
  bill_name,
  evidence_text,
  tokenize = 'unicode61'
);

create table item_formula_links (
  item_id text not null references cost_items(item_id) on delete cascade,
  formula_key text not null,
  selection_status text not null check (selection_status in ('ready', 'partial', 'unresolved')),
  missing_variables_json text not null default '[]',
  selection_reason text not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected')),
  primary key (item_id, formula_key)
);

create table variables (
  variable_id text primary key,
  item_id text not null references cost_items(item_id) on delete cascade,
  canonical_key text,
  raw_name text not null,
  raw_type text,
  raw_value real,
  raw_unit text,
  normalized_value real,
  normalized_unit text,
  basis_year integer,
  source_class text not null,
  transfer_policy text not null,
  mapping_confidence text not null,
  normalization_status text not null,
  unit_status text not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected')),
  quality_flags_json text not null default '[]'
);

create index variables_lookup_idx
  on variables (canonical_key, transfer_policy, basis_year, review_status);
create index variables_item_idx on variables (item_id);

create table amount_observations (
  observation_id text primary key,
  item_id text not null references cost_items(item_id) on delete cascade,
  year_label text,
  year_offset integer,
  amount_thousand integer,
  formula_text text,
  is_total integer not null check (is_total in (0, 1)),
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected'))
);

create index amount_observations_item_idx
  on amount_observations (item_id, year_offset, is_total);

create table evidence_links (
  evidence_link_id text primary key,
  entity_type text not null check (entity_type in ('item', 'formula', 'variable', 'amount')),
  entity_id text not null,
  chunk_id text references document_chunks(chunk_id) on delete set null,
  page_no integer,
  locator_query text not null,
  quote_text text not null,
  locator_method text not null check (locator_method in ('exact', 'fuzzy', 'unresolved')),
  locator_score real not null,
  review_status text not null check (review_status in ('candidate', 'verified', 'rejected')),
  unique (entity_type, entity_id, quote_text)
);

create index evidence_links_entity_idx on evidence_links (entity_type, entity_id);
create index evidence_links_chunk_idx on evidence_links (chunk_id, page_no);

create table item_embeddings (
  item_id text primary key references cost_items(item_id) on delete cascade,
  embedding_model text not null,
  dimensions integer not null,
  vector_json text not null,
  embedding_text text not null
);
