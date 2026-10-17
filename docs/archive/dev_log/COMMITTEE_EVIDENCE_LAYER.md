# Committee Evidence Layer

## 왜 추가했는가

기존 TAG 데이터에는 비용추계 항목·변수·금액이 있었지만, 검색에 필요한 위원회의 법적·운영 구조와 변수별 출처가 분리되어 있지 않았다. 그 결과 다음이 같은 `target_count`로 보이거나, 대상 조문과 추계서의 유사사례 설명이 섞였다.

- 전체 위원 수와 실제 수당 지급대상 수
- 기존 대비 순증 위원 수
- 전국에 설치되는 위원회 개수
- 사건 수와 회의당 처리 건수
- 상설 위원회의 연간 회의 수와 비정기 위원회의 건당 회의 수

이 계층은 기존 TAG 테이블을 덮어쓰지 않는 additive schema다.

## 구조

`committee_profiles`는 검색용 구조 프로필을 저장한다.

- 위원회 명칭, 소속기관, 상설·한시·사건발생형
- 기능 분류, 법정 전체 위원 수, 수당 대상 수
- 분과위원회·사무국 존재 여부
- 산식 시그니처와 검토 필요 여부
- 프로필을 만든 원문과 출처 종류

`committee_evidence_atoms`는 계산 피연산자와 출처를 원자 단위로 저장한다.

- `paid_members`, `incremental_paid_members`, `committee_instances`
- `annual_meetings`, `meetings_per_event`, `events_per_year`
- `meeting_unit_price`, `formula_expression`
- 직접 진술·가정·유사사례·공식지침 등 도출 방식
- 다른 의안에 직접 쓸 수 있는지 여부와 품질 플래그

법적 프로필 값은 검색 특성으로만 사용하고 다른 의안의 숫자로 복사하지 않도록 `do_not_transfer`로 저장한다.

## 오염 방지 원칙

1. 위원회 프로필은 대상 위원회 명칭 주변의 설치·기능·구성 문장만 사용한다.
2. 비용 변수는 추계서의 넓은 근거 문맥을 유지한다.
3. 기존 변수 행이 비어 있어도 보고서에 명시된 단순 곱셈식만 보수적으로 복구한다.
4. `유사사례를 참고하여` 만든 값은 다시 자동 준용하지 않고 검토 후보로만 남긴다.
5. 전체 위원 수가 100명을 넘거나 수당 대상 수보다 작으면 프로필 필드에서 격리한다.
6. 값이 없으면 만들지 않고 `partial` 또는 `requires_review`로 남긴다.

## 현재 로컬 백필 결과

2026-08-02 기준 두 TAG seed 전체를 결정적으로 다시 처리한 결과다.

- 원본 위원회 비용항목: 385개
- 위원회 프로필: 335개
- 근거 원자: 2,311개
- 실행 가능한 산식 시그니처: 142개
- 보고서 명시식에서 복구한 피연산자: 3개
- 논리 검증으로 격리한 프로필 필드: 7개
- 중복 키·고아 근거: 0개

보수적으로 검사 가능한 명시 산식 5건은 피연산자 재계산 결과 모두 20% 이내였고, 4건은 1% 이내였다. 기존 TAG 금액 행 한 건은 원문 `350만원`이 `35만원`으로 저장된 10배 단위 오류도 감사 하네스가 발견했다. 이 오류는 원본을 몰래 수정하지 않고 감사 결과에 남긴다.

## 대표 검증

- 공무원보수위원회: 법정 전체 27명과 기존 대비 순증 수당대상 8명을 분리했다.
- 국가인공지능데이터센터진흥위원회: 비어 있던 변수 행 대신 원 보고서의 `민간위원 6명 × 20만원 × 연 3회`를 출처와 함께 복구했다. 다만 이 값 자체가 유사사례 기반이므로 자동 재차용은 막는다.
- 위원후보추천위원회: 상설 `연 3회`가 아니라 선출·지명 사건마다 열리는 `건당 3회`로 분류한다.
- 국립대학병원발전위원회: 법에 없는 전체 위원 수는 확정하지 않고, 추계서의 민간위원 11명·25만원·연 4회만 검토 후보로 보존한다.

## 실행

```bash
python3 -m backend.scripts.backfill_committee_evidence
python3 -m backend.scripts.audit_committee_evidence \
  --output backend/generated/committee_evidence_v1/audit.json
```

원격 업로드는 먼저 [20260802_committee_evidence.sql](../../backend/migrations/20260802_committee_evidence.sql)을 적용한 뒤에만 수행한다.

```bash
python3 -m backend.scripts.backfill_committee_evidence --upload
```

현재 로컬 Supabase CLI 로그인 계정에는 애플리케이션이 사용하는 원격 프로젝트가 표시되지 않아, 원격 migration/upload는 실행하지 않았다. 로컬 JSON evidence는 `committee_estimator_v3`가 읽어 기존 TAG 후보의 누락된 실행 변수를 보강한다. 기존 변수가 있으면 절대 덮어쓰지 않는다.
