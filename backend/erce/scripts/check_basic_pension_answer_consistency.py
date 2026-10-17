"""Conditional consistency audit, never a source of fitted recipient counts."""


def audit():
    # 2026: only lower30 changes, and other bands stay unchanged.
    # If the historical per-band reduction proportion is identical in both
    # scenarios, its own factor cancels out of the cost/standard ratio.
    old=350387;new=400000;displayed_after_lower=15.1;displayed_delta=1.1
    implied_delta=displayed_after_lower*(1-old/new)
    low=(displayed_after_lower-.05)*(1-old/new)
    high=(displayed_after_lower+.05)*(1-old/new)
    return dict(diagnostic_only=True,year=2026,
        assumptions=["동일한소득구간수급자수가개정전후유지",
                     "같은구간평균감액비율을개정전후기준액에비례적용",
                     "30~50%와50%초과는2026년에변경없음"],
        old_reference=old,new_reference=new,gold_after_lower30_trillion=displayed_after_lower,
        implied_delta_trillion=implied_delta,rounding_interval=[low,high],
        displayed_delta_interval=[displayed_delta-.05,displayed_delta+.05],
        consistent_under_assumptions=False,
        conclusion="위비례가정하에서는표시반올림으로설명불가.실제처리에서대상구성·감액산정이다른지작성근거확인필요.정답이틀렸다고단정하거나총액에맞춰비율역산금지")
