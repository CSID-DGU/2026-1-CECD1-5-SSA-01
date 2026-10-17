-- Committee evidence layer (additive, non-destructive)
--
-- Existing TAG tables remain the source of cost-estimate items.  These two
-- tables add the missing legal/operational profile and operand-level
-- provenance needed for evidence-first committee estimation.

create table if not exists public.committee_profiles (
  profile_key             text primary key,
  bill_id                 text not null references public.assembly_bills(bill_id) on delete cascade,
  bill_no                 text,
  bill_name               text,
  propose_date            date,
  committee_name          text not null,
  normalized_name         text not null,
  source_article_ref      text,
  source_text             text,
  profile_provenance      text not null default 'cost_estimate_restatement'
    check (profile_provenance in ('bill_text', 'cost_estimate_restatement', 'mixed')),
  lifecycle               text not null default 'unknown'
    check (lifecycle in ('standing', 'event_driven', 'temporary', 'unknown')),
  function_class          text not null default 'general',
  parent_authority        text,
  total_member_count      numeric,
  member_count_is_cap     boolean,
  paid_member_count       numeric,
  public_official_count   numeric,
  has_subcommittee        boolean not null default false,
  has_secretariat         boolean not null default false,
  plan_period_years       numeric,
  formula_signature       text,
  profile_status          text not null default 'partial'
    check (profile_status in ('complete', 'partial', 'needs_review', 'reviewed')),
  requires_review         boolean not null default true,
  extraction_method       text not null default 'deterministic_backfill',
  extraction_version      text not null,
  raw_attributes          jsonb not null default '{}'::jsonb,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  unique (bill_id, normalized_name)
);

-- Keep the migration forward-compatible with an earlier local draft of the
-- tables that did not yet expose field provenance/review state.
alter table public.committee_profiles
  add column if not exists profile_provenance text not null default 'cost_estimate_restatement',
  add column if not exists requires_review boolean not null default true;

create index if not exists committee_profiles_name_idx
  on public.committee_profiles (normalized_name);

create index if not exists committee_profiles_lifecycle_function_idx
  on public.committee_profiles (lifecycle, function_class);

create index if not exists committee_profiles_bill_id_idx
  on public.committee_profiles (bill_id);

create index if not exists committee_profiles_name_trgm_idx
  on public.committee_profiles using gin (committee_name gin_trgm_ops);

create table if not exists public.committee_evidence_atoms (
  atom_key                text primary key,
  profile_key             text not null references public.committee_profiles(profile_key) on delete cascade,
  bill_id                 text not null references public.assembly_bills(bill_id) on delete cascade,
  source_item_key         text,
  evidence_role           text not null,
  raw_value               numeric,
  text_value              text,
  raw_unit                text,
  normalized_value        numeric,
  normalized_unit         text,
  formula_text            text,
  formula_scope           text not null default 'unknown'
    check (formula_scope in ('main_committee', 'subcommittee', 'combined', 'unknown')),
  provenance_type         text not null,
  derivation_type         text not null default 'unknown',
  transferability         text not null default 'review'
    check (transferability in ('direct', 'review', 'do_not_transfer')),
  source_ref              text,
  source_text             text,
  basis_year              integer,
  valid_from              date,
  valid_to                date,
  review_status           text not null default 'candidate'
    check (review_status in ('candidate', 'verified', 'rejected')),
  quality_flags           jsonb not null default '[]'::jsonb,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

alter table public.committee_evidence_atoms
  add column if not exists text_value text;

create index if not exists committee_evidence_atoms_profile_idx
  on public.committee_evidence_atoms (profile_key);

create index if not exists committee_evidence_atoms_role_idx
  on public.committee_evidence_atoms (evidence_role);

create index if not exists committee_evidence_atoms_source_item_idx
  on public.committee_evidence_atoms (source_item_key);

create index if not exists committee_evidence_atoms_transferability_idx
  on public.committee_evidence_atoms (transferability, review_status);
