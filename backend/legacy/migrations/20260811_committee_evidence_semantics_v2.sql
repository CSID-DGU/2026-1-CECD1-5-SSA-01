-- Committee evidence semantics v2 (proposal; additive and not runtime-wired)
--
-- v1 attaches every atom to the proposed committee profile.  A cost estimate
-- may, however, discuss an existing comparator's operating actual or a generic
-- budget guideline.  The v2 layer separates the evidence subject, observation
-- scope, and target-to-evidence relationship so equal numbers are not mistaken
-- for transferable evidence.

create table if not exists public.committee_cost_events (
  event_key                text primary key,
  bill_id                  text not null references public.assembly_bills(bill_id) on delete cascade,
  article_ref              text,
  committee_name           text not null,
  normalized_name          text not null,
  change_kind              text not null default 'unknown',
  formula_family           text,
  normalized_components    jsonb not null default '[]'::jsonb,
  cited_laws               jsonb not null default '[]'::jsonb,
  cited_articles           jsonb not null default '[]'::jsonb,
  named_institutions       jsonb not null default '[]'::jsonb,
  event_fingerprint        text,
  extraction_version       text not null,
  review_status            text not null default 'candidate'
    check (review_status in ('candidate', 'verified', 'rejected')),
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create table if not exists public.committee_evidence_subjects (
  subject_key              text primary key,
  subject_kind             text not null
    check (subject_kind in ('committee', 'institution', 'generic_guideline', 'unknown')),
  subject_name             text not null,
  normalized_name          text not null,
  parent_authority         text,
  function_class           text,
  lifecycle                text,
  identity_status          text not null default 'candidate'
    check (identity_status in ('candidate', 'verified', 'rejected')),
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create table if not exists public.committee_metric_observations (
  observation_key          text primary key,
  subject_key              text references public.committee_evidence_subjects(subject_key) on delete set null,
  source_profile_key       text references public.committee_profiles(profile_key) on delete set null,
  bill_id                  text references public.assembly_bills(bill_id) on delete cascade,
  source_item_key          text,
  metric_role              text not null,
  measurement_scope        text not null default 'unknown'
    check (measurement_scope in (
      'member_count', 'meetings_per_year', 'per_person_per_meeting',
      'whole_meeting', 'annual_operating_total', 'committee_instances', 'unknown'
    )),
  normalized_value         numeric,
  normalized_unit          text,
  evidence_kind            text not null
    check (evidence_kind in (
      'legal_fact', 'reported_actual', 'official_guideline',
      'analyst_assumption', 'analogy', 'derived', 'unknown'
    )),
  transfer_policy          text not null default 'do_not_transfer'
    check (transfer_policy in (
      'same_subject_only', 'direct_guideline', 'cross_subject_prior', 'do_not_transfer'
    )),
  observed_on              date,
  basis_year               integer,
  valid_from               date,
  valid_to                 date,
  source_ref               text,
  source_text              text not null,
  review_status            text not null default 'candidate'
    check (review_status in ('candidate', 'verified', 'rejected')),
  quality_flags            jsonb not null default '[]'::jsonb,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create table if not exists public.committee_precedent_links (
  link_key                 text primary key,
  target_event_key         text references public.committee_cost_events(event_key) on delete cascade,
  target_profile_key       text references public.committee_profiles(profile_key) on delete cascade,
  evidence_subject_key     text references public.committee_evidence_subjects(subject_key) on delete set null,
  source_bill_id           text references public.assembly_bills(bill_id) on delete cascade,
  source_item_key          text,
  link_type                text not null
    check (link_type in (
      'same_bill_history', 'same_subject_history', 'explicit_citation',
      'statutory_successor', 'template_lineage', 'named_institution',
      'functional_peer', 'generic_guideline', 'ministry_submission', 'external_actuals'
    )),
  evidence_role            text not null,
  source_quote             text,
  confidence               numeric,
  label_status             text not null default 'candidate'
    check (label_status in ('candidate', 'verified', 'rejected')),
  reviewer_notes           text,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  check (target_event_key is not null or target_profile_key is not null)
);

create index if not exists committee_cost_events_bill_idx
  on public.committee_cost_events (bill_id);
create index if not exists committee_evidence_subjects_name_idx
  on public.committee_evidence_subjects (subject_kind, normalized_name);
create index if not exists committee_metric_observations_lookup_idx
  on public.committee_metric_observations
  (metric_role, measurement_scope, evidence_kind, review_status);
create index if not exists committee_metric_observations_subject_idx
  on public.committee_metric_observations (subject_key, basis_year);
create index if not exists committee_precedent_links_target_idx
  on public.committee_precedent_links (target_event_key, evidence_role, label_status);
create index if not exists committee_precedent_links_profile_idx
  on public.committee_precedent_links (target_profile_key, evidence_role, label_status);
