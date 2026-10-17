"""Run the separate evidence-first estimator and compare with the official table."""
from __future__ import annotations

import argparse
import glob
import json
import unicodedata
from pathlib import Path

import fitz

from backend.estimator_v2 import estimate_from_pdf
from backend.estimator_v2.evidence_fallback import attach_narrative_evidence_shadow
from backend.estimator_v2.harness import audit_missed_evidence
from backend.legacy.scripts.evaluate_assembly_batch import _parse_first_cost_table


FILES = Path("backend/generated/assembly_rag_seed_age21_50/files")


def _pdf(bill: str, answer: bool) -> Path | None:
    keyword = "비용추계서" if answer else "의안원문"
    candidates = [
        Path(path)
        for path in glob.glob(str(FILES / bill / "*.pdf"))
        if keyword in unicodedata.normalize("NFC", Path(path).name)
        and "미첨부" not in unicodedata.normalize("NFC", Path(path).name)
    ]
    return sorted(candidates, key=lambda path: (len(str(path)), str(path)))[0] if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bill", nargs="?", default="2126334")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--no-negative-search", action="store_true")
    parser.add_argument(
        "--net-staff-count",
        type=int,
        help="HITL: 조직변경에 따른 대상 순증 인원",
    )
    parser.add_argument(
        "--net-staff-key",
        help="순증 인원을 적용할 사건 ID·조문·조직명(복수 조직 의안에서 필수)",
    )
    parser.add_argument(
        "--staffing-scenario",
        choices=("existing_staff", "new_hires"),
        help=(
            "담당관·전담인력 지정의 추가재정 시나리오: "
            "기존 직원 지정 또는 신규채용"
        ),
    )
    parser.add_argument(
        "--annual-operating-budget-thousand",
        type=int,
        help="HITL: 조직 전체 연간 운영경비(천원)",
    )
    parser.add_argument(
        "--grade-composition",
        help='HITL: 조직 순증 인원의 직급 구성 (예: "고위:1,4급:3,5급:8,6급:5,7급:3")',
    )
    parser.add_argument(
        "--committee-draft",
        action="store_true",
        help="변수 0개로 막힌 위원회 행을 조문·코호트로 저신뢰 초안 채우기(review 필요)",
    )
    parser.add_argument(
        "--committee-bridge",
        action="store_true",
        help="위원회 항목을 v5(정규식, 안전) 산식으로 강제 대체(숫자 확정 안 함)",
    )
    parser.add_argument(
        "--research-plan-override",
        action="store_true",
        help="제정안의 신규 계획수립 의무가 possibly_incremental로 막히는 걸 우회(연구용역 검색 허용)",
    )
    parser.add_argument(
        "--subsidy-auto-scope",
        action="store_true",
        help="지원금(subsidy)을 자동계산 범위에 opt-in으로 포함(OUTSIDE_AUTO_SCOPE 우회)",
    )
    parser.add_argument(
        "--subsidy-formula-presenter",
        action="store_true",
        help="지원금 항목이 값 없어 막혀도 최유사 선례의 산식·변수명은 표시(새 호출 없음)",
    )
    parser.add_argument(
        "--subsidy-reclassify",
        action="store_true",
        help="개인 대상 급여 지급이 organization_change로 오분류된 경우 subsidy로 교정",
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="최종 신뢰 모드: --committee-bridge + --adversarial-verify 동시 적용",
    )
    parser.add_argument(
        "--adversarial-verify",
        action="store_true",
        help="위원회 선례 선택을 별도 LLM 반박 호출로 재검증(반박 성공 시 확정 취소)",
    )
    parser.add_argument(
        "--committee-key",
        help="위원회 HITL 값을 적용할 사건 ID·조문·위원회명",
    )
    parser.add_argument(
        "--incumbent-paid-members",
        type=float,
        help="HITL: 기존 제도의 수당 지급대상 인원",
    )
    parser.add_argument(
        "--committee-paid-members",
        type=float,
        help="HITL: 기존 제도 대비 순증 수당 지급대상 인원",
    )
    parser.add_argument(
        "--committee-unit-price-won",
        type=float,
        help="HITL: 1인 1회당 실제 수당(원)",
    )
    parser.add_argument(
        "--committee-annual-meetings",
        type=float,
        help="HITL: 실제 연간 회의 횟수",
    )
    parser.add_argument(
        "--draft-doc",
        action="store_true",
        help="정답지 형식의 비용추계서 초안(Markdown) 출력",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--no-db-audit",
        action="store_true",
        help="평가용 DB 미사용 근거 감사를 생략",
    )
    parser.add_argument(
        "--shadow-evidence",
        action="store_true",
        help="미확정 비용행에 서술형 DB 근거 후보를 붙이되 계산은 바꾸지 않음",
    )
    parser.add_argument(
        "--shadow-max-groups",
        type=int,
        default=None,
        help="보조 근거 검색 그룹 수 제한(API 호출 절약용)",
    )
    args = parser.parse_args()
    committee_values = {
        key: value
        for key, value in {
            "incumbent_paid_members": args.incumbent_paid_members,
            "paid_members": args.committee_paid_members,
            "unit_price_won": args.committee_unit_price_won,
            "annual_meetings": args.committee_annual_meetings,
        }.items()
        if value is not None
    }
    if committee_values and not args.committee_key:
        raise SystemExit("위원회 HITL 값에는 --committee-key가 필요합니다.")
    grade_composition = None
    if args.grade_composition:
        grade_composition = {}
        for pair in args.grade_composition.split(","):
            if ":" in pair:
                grade, count = pair.split(":", 1)
                grade_composition[grade.strip()] = float(count.strip())

    source = _pdf(args.bill, False)
    if not source:
        raise SystemExit(f"의안원문 PDF 없음: {args.bill}")
    result = estimate_from_pdf(
        source.read_bytes(),
        filename=source.name,
        refresh=args.refresh,
        include_non_attachment_search=not args.no_negative_search,
        organization_net_staff_count=(
            args.net_staff_count
            if not args.net_staff_key
            else None
        ),
        organization_net_staff_counts=(
            {args.net_staff_key: args.net_staff_count}
            if args.net_staff_key and args.net_staff_count
            else None
        ),
        organization_staffing_scenario=args.staffing_scenario,
        organization_annual_operating_budgets_thousand=(
            {"연간 조직 운영경비": args.annual_operating_budget_thousand}
            if args.annual_operating_budget_thousand
            else None
        ),
        organization_grade_composition=grade_composition,
        committee_draft_fill=args.committee_draft,
        adversarial_verify_committees=args.adversarial_verify or args.final,
        committee_formula_bridge=args.committee_bridge or args.final,
        subsidy_reclassify=args.subsidy_reclassify or args.final,
        research_plan_enactment_override=args.research_plan_override or args.final,
        subsidy_auto_scope=args.subsidy_auto_scope,
        subsidy_formula_presenter=args.subsidy_formula_presenter,
        committee_variable_inputs=(
            {args.committee_key: committee_values}
            if args.committee_key and committee_values
            else None
        ),
    )
    shadow_evidence = (
        attach_narrative_evidence_shadow(
            result,
            refresh=args.refresh,
            max_groups=args.shadow_max_groups,
        )
        if args.shadow_evidence
        else None
    )
    answer = _pdf(args.bill, True)
    official = None
    if answer:
        parsed = _parse_first_cost_table("\n".join(page.get_text() for page in fitz.open(answer)))
        official = parsed.get("total")
    system_million = round(result.total_thousand() / 1000)
    error = (
        round((system_million - official) / official * 100, 1)
        if official not in (None, 0)
        else None
    )
    evidence_audit = (
        None
        if args.no_db_audit or not answer
        else audit_missed_evidence(args.bill, result)
    )
    if args.json:
        payload = result.to_dict()
        payload["official_million"] = official
        payload["system_million"] = system_million
        payload["error_pct"] = error
        payload["evidence_audit"] = evidence_audit
        payload["shadow_evidence"] = shadow_evidence
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.draft_doc:
        from backend.estimator_v2.draft_document import render_draft_document

        print(render_draft_document(result))
        return

    print("=" * 78)
    print(f"[v2] {args.bill} {result.bill_name} / {result.doc_type}")
    print(f"공식 {official}백만원 | v2 {system_million}백만원 | 오차 {error}%")
    print(
        f"입력={result.input_hash[:10]} 데이터={result.dataset_fingerprint} "
        f"LLM캐시={result.cache_hit}"
    )
    print("=" * 78)
    for row in result.rows:
        amount = row.total_thousand / 1000
        recurrence = row.recurrence.mode if row.recurrence else "-"
        print(
            f"[{row.status.value:16}] {row.event.object[:31]:31} "
            f"{amount:8.1f}백만  {recurrence}"
        )
        print(f"  근거: {row.reason}")
        if row.selected_candidates:
            refs = ", ".join(
                f"{candidate.bill_no}:{candidate.item_name[:18]}({candidate.similarity:.3f})"
                for candidate in row.selected_candidates[:3]
            )
            print(f"  TAG: {refs}")
            print(
                f"  선택: {row.selection_method} confidence={row.selection_confidence:.2f} "
                f"/ {row.selection_reason}"
            )
        if row.narrative_evidence:
            refs = ", ".join(
                f"{evidence['bill_no']}({evidence['semantic_similarity']:.3f})"
                for evidence in row.narrative_evidence[:3]
            )
            print(f"  보조근거(shadow): {refs}")
        if row.non_attachment_evidence:
            refs = ", ".join(
                f"{evidence['bill_no']}({evidence['similarity']:.3f})"
                for evidence in row.non_attachment_evidence[:3]
            )
            print(f"  미첨부 반대근거: {refs}")
    if shadow_evidence:
        print("\n서술형 근거 보조 검색(shadow):")
        print(
            f"- 계산 변경={shadow_evidence['amounts_changed']} "
            f"그룹={len(shadow_evidence['groups'])}"
        )
        for group in shadow_evidence["groups"]:
            print(
                f"- {group['group']}: events={','.join(group['event_ids'])} "
                f"hits={group['hit_count']} top={group['top_bill_no']} "
                f"sim={group['top_similarity']}"
            )
    if evidence_audit:
        print("\nDB 근거 감사:")
        print(
            f"- 대상 정답 후보 제외={evidence_audit['target_excluded_from_candidate_search']} "
            f"누출={evidence_audit['target_leak']} "
            f"요약={evidence_audit['summary']}"
        )
        for item in evidence_audit["items"]:
            print(f"- {item['item_name']}: {item['status']}")
            for hit in item["independent_hits"][:2]:
                print(
                    f"  · {hit['bill_no']} {hit['bill_name'][:35]} "
                    f"anchor={hit['anchor']} strength={hit['strength']:.2f}"
                )
    print("\n경고:")
    for warning in result.warnings:
        print(f"- {warning}")


if __name__ == "__main__":
    main()
