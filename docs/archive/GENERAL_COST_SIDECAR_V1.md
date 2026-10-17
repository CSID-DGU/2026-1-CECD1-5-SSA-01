# 범용 비용추계 sidecar v1

조직·인건비에서 사용한 `item_profile + variable_evidence + formula` 구조를
일곱 가지 비용 성격으로 일반화한 로컬 후보 DB다. 기존 TAG 원본은 수정하지
않으며, 모든 신규 행은 검수 전 `candidate`로 저장한다.

## 비용 성격

- `personnel`: 인건비
- `goods_services`: 물건비
- `transfers`: 이전지출
- `capital`: 자본지출
- `tax_expenditure`: 조세감면
- `non_tax_revenue_loss`: 세외수입감소
- `equity_contribution`: 출자·출연

## 데이터 계층

1. `document_profiles.jsonl`: 22대 비용추계서 3,365건의 문서 단위 분류
2. `item_profiles.jsonl`: 비용 항목별 성격·세부 구성·산식 후보
3. `variable_evidence.jsonl`: 원문 변수, 정규화 값·단위, 출처, 이전 정책
4. `amount_observations.jsonl`: 공식 추계의 연도별 금액과 산식 문장
5. `formula_definitions.jsonl`: 비용 성격별 공통 산식 레지스트리

생성 위치는 `backend/generated/general_cost_sidecar_v1`이다.

## 현재 범위

22대 신규 수집 문서 중 100건은
`backend/generated/assembly_22_validation_holdout_v1`에 문서 단위로 분리했다.
해당 PDF와 이미 추출된 TAG 행은 개발용 폴더와 `*.jsonl`에서 격리되며,
기본 sidecar 빌더도 holdout manifest의 의안 ID·번호를 중복 차단한다.

- 22대 문서 프로필: 3,365건
- 22대 항목 구조화 완료: 976건
- 21·22대 기존 TAG 전체 구조화 문서: 1,378건
- 비용 항목 프로필: 3,346개
- 변수 근거: 9,805개
- 연도별 정답 관측치: 17,867개
- 필수 변수와 숫자가 모두 있는 산식: 733개
- 일부 변수만 있거나 값이 비어 있는 산식: 1,124개
- 산식 미연결: 1,489개
- 22대 미구조화 대기 문서: 2,389건

이 수치는 성능 점수가 아니라 초기 DB 적재 현황이다. 자동 분류와 변수 매핑은
모두 후보 상태이며, 홀드아웃 평가와 사람 검수를 통과한 행만 `verified`로
승격해야 한다.

## 재생성

```bash
python3 -m backend.scripts.build_general_cost_sidecar
python3 -m unittest backend.test_general_cost_sidecar -v
```

Supabase용 additive 스키마는
`backend/migrations/20260927_general_cost_evidence_sidecar_v1.sql`에 있다.

## 근거 기반 선례 선택기

`backend/general_cost_precedent_selector.py`는 유사도 상위 문서를 바로
계산에 사용하지 않는다. 다음 조건을 순서대로 검사한다.

1. 대상 법안의 컷오프보다 비용추계서 공식 회답일이 빠른가
2. 비용 성격과 비용 발생 메커니즘이 같은가
3. 실제로 금액에 포함된 사업 범위가 같은가
4. 집행기관과 정책 영역이 일치하는가
5. 과거 연도별 금액이 완결되어 있고 서로 모순되지 않는가
6. 비슷한 수준의 복수 선례가 20% 넘게 다르면 계산을 보류하는가

모든 조건을 통과한 경우에도 현재 sidecar 행은 `candidate`이므로 결과는
`exact_precedent_candidate`와 `computed_review`로 반환한다. 조건이
부족하면 `needs_review` 또는 `abstain`으로 종료하며 금액을 생성하지 않는다.

## 산식 연결 v2

선례 선택 후 연액을 일괄 복사하지 않고, 조직·행정운영 resolver와 같은
계약으로 일곱 가지 비용 성격을 연결한다.

1. 비용 성격·세부 구성·가용 피연산자로 버전 산식을 선택한다.
2. 피연산자는 한 개의 선택된 `profile_key`에서만 가져온다.
3. `target_specific`, `do_not_transfer`는 선례에서 자동 이전하지 않는다.
4. 대상 법안·사용자 확정값인 `formula_inputs`가 선례보다 우선한다.
5. 필수 변수가 비면 숫자를 만들지 않고 `needs_evidence`로 반환한다.

기념행사의 `1회 × 유사행사 단가`처럼 적용 조건이 고정된 산식만 규칙으로
보완하며, 의안별 금액은 하드코딩하지 않는다.

```bash
python3 -m backend.scripts.run_general_cost_precedent_selector \
  backend/generated/goods_holdout_2219945/target_profile_v2.json \
  --out backend/generated/goods_holdout_2219945/selection_v2.json \
  --resolver-out backend/generated/goods_holdout_2219945/prediction_v2.json
```

의안번호 `2219945` 홀드아웃에서는 회답일 컷오프와 범위·기관 게이트를
통과한 `2212028 목재의 날 기념행사`를 선택하여 연간 1억원을 제시했다.
기존에 선택했던 `2215595 차의 날 기념식 개최 및 홍보`는 홍보비가 함께
포함된 선례이므로 `PRICED_SCOPE_EXTRA:publicity`로 실행 대상에서 제외된다.
