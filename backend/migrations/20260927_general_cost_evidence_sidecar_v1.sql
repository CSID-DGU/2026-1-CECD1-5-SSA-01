-- General cost-estimation profile/evidence sidecar v1.
--
-- Additive only. Existing assembly/TAG and org_admin tables stay immutable.
-- The shape intentionally mirrors org_admin_item_profiles and
-- org_admin_variable_evidence while generalizing the route to seven fiscal
-- natures. Candidate rows are never treated as verified automatically.

create table if not exists public.general_cost_formula_templates (
  formula_key            text primary key,
  cost_natures           text[] not null,
  label                  text not null,
  expression_text        text not null,
  required_variables     text[] not null,
  optional_variables     text[] not null default '{}',
  recurrence             text not null
    check (recurrence in ('annual', 'one_time', 'scheduled', 'mixed')),
  applicability          jsonb not null default '{}'::jsonb,
  template_version       text not null,
  review_status          text not null default 'draft'
    check (review_status in ('draft', 'verified', 'deprecated')),
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create table if not exists public.general_cost_document_profiles (
  document_profile_key   text primary key,
  bill_id                text,
  bill_no                text,
  bill_name              text,
  age                     integer,
  proposer                text,
  propose_date            date,
  committee               text,
  cost_natures            text[] not null default '{}',
  cost_nature_labels      text[] not null default '{}',
  primary_cost_nature     text not null,
  classification_source   text,
  classification_status   text not null default 'candidate',
  item_extraction_status  text not null default 'pending'
    check (item_extraction_status in ('pending', 'structured_candidate', 'verified', 'failed')),
  schema_version          text not null,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

create table if not exists public.general_cost_item_profiles (
  profile_key             text primary key,
  source_item_key         text not null unique,
  raw_structure_key       text,
  bill_id                 text,
  bill_no                 text,
  bill_name               text,
  propose_date            date,
  committee               text,
  item_name               text not null,
  raw_item_category       text,
  trigger_ref             text,
  cost_nature             text not null
    check (cost_nature in (
      'personnel', 'goods_services', 'transfers', 'capital',
      'tax_expenditure', 'non_tax_revenue_loss',
      'equity_contribution', 'review_required'
    )),
  component               text not null,
  formula_family          text,
  formula_readiness       text not null default 'unresolved'
    check (formula_readiness in ('ready', 'partial', 'unresolved')),
  missing_formula_variables text[] not null default '{}',
  classification_confidence text not null
    check (classification_confidence in ('high', 'medium', 'low')),
  classification_reason   text not null,
  classifier_version      text not null,
  review_status           text not null default 'candidate'
    check (review_status in ('candidate', 'verified', 'rejected')),
  raw_attributes          jsonb not null default '{}'::jsonb,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

create table if not exists public.general_cost_variable_evidence (
  evidence_key            text primary key,
  profile_key             text not null
    references public.general_cost_item_profiles(profile_key) on delete cascade,
  raw_variable_fingerprint text not null,
  canonical_key           text,
  raw_variable_type       text,
  raw_variable_name       text not null,
  raw_value               numeric,
  raw_unit                text,
  normalized_value        numeric,
  normalized_unit         text,
  source_class            text not null
    check (source_class in (
      'bill_or_target_document', 'official_standard', 'official_forecast',
      'official_statistics', 'budget_or_settlement', 'similar_case',
      'analyst_assumption', 'unclassified_source', 'missing'
    )),
  transfer_policy         text not null
    check (transfer_policy in (
      'target_specific', 'versioned_official', 'scope_check_required',
      'comparable_only', 'review_required', 'do_not_transfer'
    )),
  source_text             text not null default '',
  basis_year_candidates   integer[] not null default '{}',
  basis_year              integer,
  mapping_confidence      text not null
    check (mapping_confidence in ('high', 'medium', 'low')),
  normalization_status    text not null
    check (normalization_status in ('mapped', 'unmapped')),
  unit_status             text not null
    check (unit_status in ('normalized', 'ambiguous', 'missing', 'not_normalized')),
  review_status           text not null default 'candidate'
    check (review_status in ('candidate', 'verified', 'rejected')),
  quality_flags           jsonb not null default '[]'::jsonb,
  transform_version       text not null,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  unique (profile_key, raw_variable_fingerprint)
);

create table if not exists public.general_cost_amount_observations (
  observation_key        text primary key,
  profile_key            text not null
    references public.general_cost_item_profiles(profile_key) on delete cascade,
  year_label             text,
  year_offset            integer,
  amount_thousand        bigint,
  formula_text           text,
  is_total               boolean not null default false,
  review_status          text not null default 'candidate'
    check (review_status in ('candidate', 'verified', 'rejected')),
  transform_version      text not null,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create index if not exists general_cost_documents_bill_idx
  on public.general_cost_document_profiles (bill_id, bill_no);
create index if not exists general_cost_documents_pending_idx
  on public.general_cost_document_profiles (item_extraction_status, primary_cost_nature);
create index if not exists general_cost_profiles_lookup_idx
  on public.general_cost_item_profiles
  (cost_nature, component, formula_readiness, review_status);
create index if not exists general_cost_profiles_bill_idx
  on public.general_cost_item_profiles (bill_id, propose_date);
create index if not exists general_cost_evidence_lookup_idx
  on public.general_cost_variable_evidence
  (canonical_key, transfer_policy, review_status, basis_year);
create index if not exists general_cost_evidence_profile_idx
  on public.general_cost_variable_evidence (profile_key);
create index if not exists general_cost_amounts_profile_idx
  on public.general_cost_amount_observations (profile_key, year_offset);

