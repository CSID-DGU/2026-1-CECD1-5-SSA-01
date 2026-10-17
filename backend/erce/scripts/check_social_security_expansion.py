import dataclasses
import json
from backend.erce.engine import estimate_routed_item
from backend.erce.web_bridge import calculate_erce_web_item
from backend.erce.central_social_committee_evidence import EXPANSION


def expansion_payload(mode="face_to_face"):
    method = "2209259:social_security_committee_expansion"
    keys = ["2209259:committee_expansion:incremental_unpaid_members",
            "2209259:committee_expansion:annual_meetings", f"2209259:committee_expansion:meeting_price:{mode}"]
    notes = dict(committee_scale_note="원문 상한30→35명. 정답의 추가 당연직1명·유급위촉4명 참고 구성, 실제 인원 확정값 아님.",
                 meeting_frequency_note="사회보장위원회2023·2024 각3회 본회의 실적 준용, 향후 연3회 가정.",
                 committee_payment_note="본회의 대면20만원·서면10만원. 정답은 매년 대면3회 가정, 분과회의 추가비용 제외.")
    return dict(bill_no="2209259", evidence_mode="development_review", cutoff_date="2026-10-10",
                route_key="committee_components", support_derivation=EXPANSION, payer="government",
                committee_role_profile="social_security_existing_committee_expansion", meeting_mode=mode,
                start_year=2026, years=5, expansion_scenario_confirmed=True, **notes,
                explicit_inputs={key: dict(value=value, unit="person", source_ref="2209259 원문PDF3쪽 제21조 상한개정")
                                 for key, value in (("old_member_limit", 30), ("new_member_limit", 35))},
                selected_evidence_keys=keys, evidence_selection_reasons={key: "동일 사회보장위원회 본회의 과업·구성 및 실적 참고" for key in keys},
                selected_method_keys=[method], method_selection_reasons={method: "기존 위원회 확대의 유급 순증만 계산"},
                method_confirmations={method: notes})


def run_regression():
    p = expansion_payload()
    engine = estimate_routed_item(p)
    web = calculate_erce_web_item({**p, "bill_no": "SIMILAR_SOCIAL_SECURITY_EXPANSION", "evidence_mode": "holdout"})
    annual = list(engine.annual_amounts_thousand)
    if annual != web["annualAmountsThousand"]:
        raise ValueError("개발 회귀와 웹 계산 불일치")
    total = sum(annual) * 1000
    return dict(bill_no="2209259", post_answer_regression=True, independent_evaluation=False,
                payload=p, result=dataclasses.asdict(engine), web_result=web,
                total_won=total, gold_total_won=12000000, error_percent=abs(total - 12000000) / 12000000 * 100,
                annual_matches=sum(value == 2400 for value in annual),
                official_scope_complete=annual == [2400] * 5 and web["status"] == "computed_review")


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
