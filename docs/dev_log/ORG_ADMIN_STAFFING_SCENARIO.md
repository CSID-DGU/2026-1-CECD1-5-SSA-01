# 담당관·전담인력 지정 비용 시나리오 라우팅

적용 버전: `estimator-v2.36.0`  
대상 검증: 2126655호 여성농어업인 담당관 지정

## 변경 내용

LLM 사건 추출 결과가 `committee_operation`이어도 다음 조건을 함께 만족하면
`personnel`·조직운영 채널로 재분류한다.

- 대상 객체에 담당관·전담인력·전문인력·전담담당자가 포함됨
- 원문에 `소속 직원 중 ... 지정/임명/배치/채용` 구조가 있음

실제 위원회가 아닌 담당직무를 회의수당 산식으로 보내는 오류를 차단하기 위한
결정적 후처리다. 일반적인 위원회 객체에는 적용되지 않는다.

## 시나리오 입력

담당관 지정은 법문만으로 신규채용을 확정할 수 없으므로 다음 입력을 요구한다.

- `existing_staff`: 기존 직원 지정. 신규 인력운영비를 0으로 두고 별도 업무수행비는 추가 확인
- `new_hires`: 신규채용. 대상 순증 인원과 인력비 기준 선례·표준값이 모두 있어야 계산
- 미선택: `STAFFING_SCENARIO_REQUIRED`로 보류

CLI 예시:

```bash
python3 -m backend.scripts.run_estimator_v2 2126655 \
  --staffing-scenario new_hires \
  --net-staff-count 8 --no-negative-search
```

## 검증 결과

기존에는 위원회 선례 `50명 × 20만원 × 연 4회`를 적용해 5년 200백만원을
산출했다. 변경 후에는 해당 행이 `personnel`로 라우팅된다.

- 시나리오 미선택: `STAFFING_SCENARIO_REQUIRED`
- `existing_staff`: 신규 인력운영비 0백만원(`EXISTING_STAFF_DESIGNATION_NO_INCREMENTAL_PERSONNEL`)
- `new_hires`, 8명: 현재 대상 이전 DB에 공공기관용 완결 인력비 묶음이 없어 `NO_TRANSFERABLE_ORGANIZATION_CASE`로 보류

마지막 보류는 금액을 임의로 채우지 않은 것이다. 다음 단계는 공공기관 기준의
보수·기관부담금·기본경비·자산취득비 표준값을 독립 근거와 함께 연결하는 일이다.
