# Committee estimator v4: additional ten-bill audit

## Evaluation boundary

The engine was frozen before this run.  Ten additional bills with both an
original bill PDF and an official NABO cost-estimate PDF were selected from
the local corpus.  Five v4 development cases and the repeatedly used v3 test
cases were excluded.  The engine was run first; official calculation sections
were inspected only for evaluation.

This is an **audit set**, not a clean external holdout.  The documents already
existed in the local corpus, although runtime retrieval excluded each target
bill.  Its purpose is to expose failure modes and build the next frozen
regression set.

Bills:

- 2125736
- 2126635
- 2126636
- 2126661
- 2212433
- 2213320
- 2213937
- 2214559
- 2216417
- 2216503

## Baseline result

The ten bills contain 11 official committee formula units.

| Metric | Result |
|---|---:|
| Official formula units detected | 10 / 11 |
| Correct broad formula family | 7 / 11 |
| Strictly complete formula structure | 6 / 11 |
| Automatic numeric drafts | 0 / 11 |
| Incorrect numeric drafts exposed | 0 |
| False independent cost events | 3 |
| Target-answer leakage | 0 |

The engine was safe but too conservative: it emitted no invented amount, but
numeric coverage was zero.  This set therefore does not support a claim that
the current engine estimates unseen committee bills within 20%.  It supports
only the narrower claim that the evidence gate prevented unsupported amounts.

## v4.1 structural regression result

The baseline failures were converted into target-independent structural
rules.  No bill number, official amount, or committee proper name was added to
runtime code.

| Metric | Before | v4.1 regression |
|---|---:|---:|
| Official formula units detected | 10 / 11 | 11 / 11 |
| Correct broad formula family | 7 / 11 | 11 / 11 |
| Strictly complete formula structure | 6 / 11 | 11 / 11 |
| Automatic numeric drafts | 0 / 11 | 0 / 11 |
| False independent cost events | 3 | 0 |
| Target-answer leakage | 0 | 0 |

The structural fixes were:

- subordinate bodies are represented as relations and are not independently
  emitted from a generic subordinate article or a parent body's article;
- an optional subordinate body affects the formula only when its own local
  clause contains a composition/quantity basis;
- distributed installation is recognized only when the installation subject,
  scope quantifier, body name, and establishment predicate occur in the same
  installation clause;
- deliberative bodies ending in `participation assembly` are extracted;
- parliamentary special committees are routed by institutional archetype to
  the staffed formula even when the bill does not restate ordinary support
  staffing;
- internal employee disciplinary bodies are not promoted to bill-level cost
  events;
- a support unit embedded in an existing administrative institution is routed
  to committee meeting cost plus staffed support-operation cost, while an
  otherwise unspecified support structure uses a whole-institution analog.

This 11/11 is now a **regression result**, not evidence of external
generalization.  Numeric coverage also remains zero, so the system still does
not meet the intended end-to-end accuracy target.

## Bill-by-bill comparison

| Bill | Official formula | v4 result | Verdict |
|---|---|---|---|
| 2125736 | `(18-10) paid members × 350k × 4/year` | Main body routed to incremental meeting allowance; a subordinate clause was also promoted to a separate committee | Main formula correct, extraction over-detects |
| 2126635 | Advisory committee `30 × 250k × 4`; citizen assembly `500 × 250k × 1` plus its staffed support unit | Optional subcommittee forced compound routing; citizen assembly was missed | Wrong + missed |
| 2126636 | 15-person staffed parliamentary committee: payroll, burden, basic cost, assets, and program cost | Analogous flat operating budget | Wrong formula family |
| 2126661 | Permanent/non-permanent commissioners, 60-person office, advisory body, final report | Staffed committee family, but formula omits program/report components | Broad family right, formula incomplete |
| 2212433 | Event count × 10 members × 2 meetings × 400k | Event-driven committee | Formula correct, HITL |
| 2213320 | 6 private members × 200k × 3/year | Meeting allowance; selected precedent would imply 7 × 250k × 11 | Formula correct; value precedent wrong, safely blocked |
| 2213937 | Average annual operating budget of four special-autonomy support committees + inflation | Multi-instance local-government formula | Wrong; `지방자치단체` mention caused a false route |
| 2214559 | 20 private members × 300k × 4/year | Meeting allowance; selected evidence was 20 × 250k × 4 | Formula correct; blocked draft would have been -16.7% |
| 2216417 | Annual event count × 7 members × 3 meetings × 400k | Event-driven committee | Formula correct, HITL |
| 2216503 | Appointer-specific event count × incremental members × 3 meetings × 400k | Event-driven committee | Formula correct, HITL; extracted name has a prefix-boundary defect |

## Confirmed structural failure modes

1. **Entity boundary failure**
   - A long subordinate-clause phrase became an independent committee.
   - A subordinate professional committee became both a relation and an
     independent event.
   - An internal disciplinary committee was treated as a bill-level cost
     event.

2. **Optional subordinate body does not imply compound cost**
   - `may establish a subcommittee` was treated as if the subcommittee must be
     added to the main formula.  The official estimate priced only the main
     advisory committee.

3. **Distributed-scope detection is context-wide and too broad**
   - Any occurrence of `local government` in the definition can trigger the
     multi-instance formula even when exactly one national council is created.
     The installation subject and quantifier must be parsed together.

4. **Institutional archetype is missing from formula routing**
   - A parliamentary special committee was routed as a flat analog because
     its own article did not explicitly restate the supporting staff.  The
     official method used the normal staffed parliamentary-committee
     structure.

5. **Evidence executors are incomplete**
   - Event-driven committees have the right formula family, but v4 does not
     retrieve and fill their event-count operands even though same-institution
     precedents exist in the corpus.
   - Meeting retrieval can find a useful approximation (2214559) or a badly
     mismatched precedent (2213320); the current hard gate safely treats both
     as HITL instead of distinguishing them with stronger structural evidence.

## Remaining architectural work

The next change should not be another amount-specific prompt.  Preserve the
evidence gate and extend the evidence executors in this order:

1. normalize formula operands for event-driven and staffed precedents into
   first-class evidence atoms;
2. add executors for event-driven, staffed, support-operation, and flat-analog
   families while keeping disagreement and provenance gates;
3. rerun this frozen audit and only then evaluate a newly downloaded external
   holdout.

## Reproduce

```bash
python3 -m backend.scripts.evaluate_committee_estimator_v4_audit10
```
