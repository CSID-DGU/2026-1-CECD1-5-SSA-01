"""Committee incremental costs, separated from unquantified fish-sale losses."""
from backend.erce.reviewed_variable_rows import evidence_row

COMMITTEE_ID="mof_inland_cage_loss_compensation"


def aquaculture_compensation_rows():
    rows=[]
    for key,value,unit,target,role,note in (
        ("additional_paid_members",2,"person",True,"target_quantity",
         "정원 상한17−15만으로 확정하지 않음. 선례가 민간 전문가2명 실제 추가 위촉을 가정한 값. 다른 증원안에는 원문·위촉구성에 따른 별도 판단 필요"),
        ("annual_meetings",4,"meeting/year",False,"meeting_frequency_assumption",
         "해양수산부의2024년 회의4회 실적을 미래에 유지하는 가정. 2022·2023년은 각각1회여서 연4회가 고정 법정 주기라는 뜻이 아님"),
        ("meeting_unit_price",300000,"KRW/person/meeting",False,"attendance_payment_assumption",
         "정답 표의30만원은 추계 가정. 각주에 인용한2025예산편성 지침15만원+추가5만원과 차이가 있어 공식 공통 단가로 취급하지 않음. 실제 참석비·검토비 포함 여부 별도 확인 필요"),
    ):
        rows.append(evidence_row(
            evidence_key=f"2207048:committee:{key}:2025",variable_key=key,value=value,unit=unit,
            source_bill_no="2207048",available_at="2025-01-09",
            source_ref="2207048 비용추계서24B6334 PDF p.4~5: 해양수산부 위원회 운영실적 및 표2",
            source_url="backend/generated/assembly_22_pdfs/by_bill/2207048/cost_estimate.pdf",
            agency="해양수산부",policy_domain="내수면 가두리양식 손실보상",
            scope="현행 손실보상대책위원회의 추가 민간전문가 참석비",
            service_function="기존 위원회 유급 민간위원 증원",variable_role=role,
            reuse_policy="target_only" if target else "comparable",reviewed_at="2026-10-03",
            obtained_from="reviewed_answer",source_class="precedent_assumption",
            requires_applicability_note=True,allowed_routes=["committee_member_increase"],
            committee_identity=COMMITTEE_ID,limitation=note,
            observation_year=2024 if key=="annual_meetings" else None,
            historical_meetings={"2022":1,"2023":1,"2024":4} if key=="annual_meetings" else None,
            valid_from_year=2026,valid_to_year=2030,
        ))
    return rows
