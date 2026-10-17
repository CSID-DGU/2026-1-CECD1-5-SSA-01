# Committee Estimator v4: relation-first formula routing

## Why v4 exists

The v3 estimator was intentionally narrow: it estimated a single committee
with `paid members × annual meetings × unit price`.  A five-bill stress set
showed that this was not enough.  Official estimates also used:

- a main committee + subordinate committee + support organization;
- one committee repeated across many local governments;
- an analogous institution's annual operating budget;
- a staffed committee with payroll and basic operating costs.

The problem was therefore upstream of amount selection.  A better variable
reranker cannot repair a wrongly scoped clause or a wrongly selected formula.

## Runtime design

1. Extract a committee only from an explicit establishment predicate.
2. Follow contiguous governance provisions by relation, not by a fixed number
   of following articles.
3. Stop at the next independent institution or unrelated policy provision.
4. Select a formula family before retrieving values.
5. Use embeddings only to create a precedent shortlist.
6. Require relation identity, complete operands, direct provenance, and
   cross-precedent agreement before exposing a numeric draft.
7. Ask for human input when any hard evidence gate fails.

Current formula families are:

- `meeting_allowance`
- `compound_committee_allowance`
- `committee_support_operation`
- `committee_support_bundle`
- `multi_instance_operating_baseline`
- `staffed_committee_operation`
- `analog_flat_operating_budget`
- `event_driven_committee`

No bill number or official target amount is referenced by runtime code.

## Evaluation status

The five bills below are a development regression set, not an unseen holdout:

- 2124970
- 2215935
- 2216468
- 2216517
- 2216520

Their observed failures informed the v4 design.  Across 13 committee formula
units identifiable in the official calculation descriptions:

| Metric | Result |
|---|---:|
| Committee/formula units detected | 13 / 13 |
| Correct formula family | 13 / 13 |
| Automatic numeric drafts | 2 / 13 |
| Automatic drafts within 20% | 2 / 2 |
| Numeric MAPE | 11.54% |
| Target-answer leakage | 0 |

The two numeric drafts are compound support-committee cases.  v4 selected a
different bill with the same main/subordinate/support relation structure and
all five operands present.  It estimated 715 million won over five years,
versus the official 641 million won.  The difference is mainly first-year
proration and price escalation, which v4 deliberately does not yet infer.

The earlier 2216468 case remains HITL because no earlier precedent contains
the same complete compound structure.  This is expected abstention, not a
numeric success.

Ten earlier v3 committee targets were also checked for extraction regressions;
v4 detected all ten and routed multi-instance, staffed, and compound bodies to
their separate formula families.

An additional ten-bill audit then exposed weaker generalization outside that
development set: 10/11 official formula units were detected, 7/11 received the
correct broad family, 6/11 had a strictly complete formula structure, and no
numeric draft passed the evidence gate.  See
`docs/dev_log/COMMITTEE_ESTIMATOR_V4_AUDIT10.md`.  These results supersede any
broader interpretation of the development-set 13/13 result.

v4.1 converted those failures into general structural rules.  The same audit
now passes 11/11 formula units with no false independent event, while the
original five-bill 13/13 regression and ten earlier family checks still pass.
Because the fixes were derived from this audit, 11/11 is a regression result,
not an unseen-holdout result.  Automatic numeric coverage on the audit remains
0/11.

## Known limitations and next work

- Numeric coverage remains low.  Multi-instance, analogous flat-budget,
  staffed, and subordinate-only formula executors still return HITL.
- The evidence layer stores some compound formulas inside profile source text.
  v4 normalizes the support-bundle case at runtime; these operands should
  later be persisted as first-class evidence atoms.
- Effective dates, first-year proration, and inflation schedules are not yet
  part of the v4 formula executor.
- The 13/13 formula result is a regression result.  A newly frozen external
  holdout is required before making a generalization claim.

## Reproduce

```bash
python3 -m backend.scripts.evaluate_committee_estimator_v4_structure
python3 -m py_compile backend/committee_estimator_v4/*.py
```

`pytest` is not installed in the current local Python environment.  The
parameterless v3/v4 tests were executed through a small import-based runner;
30 tests passed.
