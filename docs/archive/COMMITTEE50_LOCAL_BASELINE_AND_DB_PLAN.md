# 위원회 50건 로컬 기준선과 DB 정리 계획

## 결론

50건은 로컬 개발·회귀셋으로 사용하고, Supabase는 아직 수정하지 않는다.
원문과 정답지가 모두 있지만 이미 정답을 본 셋이므로 최종 일반화 성능을
주장하는 블라인드 셋으로는 쓸 수 없다.

## 로컬 무결성

- 평가 사례: 50건
- 원문 PDF: 50/50
- 정답 비용추계서 PDF: 50/50
- 제안일·의안명 메타데이터: 50/50
- 기존 건별 진단: 50/50
- 기존 `missing_inputs` 구조화: 40/50

`backend/scripts/build_committee50_manifest.py`가 파일 해시와 라벨 상태를 고정한다.
정답 PDF는 평가기만 열 수 있고 런타임 검색·추론 입력으로 사용하지 않는다.

## 1. DB 검색 전 원문 개체 게이트

LLM과 정답 PDF를 사용하지 않고 현재 `committee_gate.py`를 50건에 적용했다.

| 항목 | 결과 |
|---|---:|
| 조문 분리 성공 | 50/50 |
| 위원회 개체 1개 이상 탐지 | 46/50 |
| 미탐지 | 4/50 |
| 문장 조각·중첩 이름 노이즈 검출 | 42/50 |
| 미검수 검색에 바로 쓸 수 있는 청정 후보 | 4/50 |

`noisy`는 정답 개체가 없다는 뜻이 아니다. 정답 이름과 함께
`"그 밖에 위원회"`, `"사항 외에 위원회"` 같은 잘못된 개체가 동시에 생성된다는
뜻이다. 현재 상태에서 RAG 50건 점수를 바로 재면 DB가 아니라 오염된 검색어
성능을 측정하게 된다.

## 2. 계층형 근거 엔진 50건 결과

개체 추출과 근거 검색을 분리하기 위해, 원문에서 확인한 목표 개체 이름만
evaluator 전용 라벨로 넘겨 현재 계층형 엔진을 오프라인 실행했다. 라벨에는
정답 금액·산식·선례 의안번호가 없다.

| 경로 | 결과 |
|---|---:|
| 완결 선례 패키지 | 3/50 |
| 부분 근거 + HITL | 47/50 |
| HITL 비용개체 | 64개 |

완결 선례 3건은 기존 수동 DB 감사의 최선 선례와 모두 일치했다.

- `2215013 → 2213418`
- `2216353 → 2215377`
- `2217718 → 2213320`

이 결과는 전체 자동계산율이 6%라는 뜻이 아니라, 선례 전체를 그대로 실행해도
되는 강한 관계만 3건이라는 뜻이다.

## 3. 현재 DB가 못 채우는 값

64개 HITL 비용개체를 분해했다.

| 피연산자 | 요구 | 조문에서 확정 | DB 참고 제시 | 완전 미커버 |
|---|---:|---:|---:|---:|
| 유급위원 수 | 61 | 3 | 0 | 61 |
| 연간 회의횟수 | 58 | 6 | 0 | 58 |
| 1인·1회 단가 | 64 | 0 | 63 | 1 |

단가 63건은 직접 정답이 아니라 공식 지침 범위를 보여주는 사전값이므로 여전히
사용자 확인 대상이다. 가장 큰 구멍은 회의횟수와 유급위원 수다.

## 4. v1→v2 안전 이관 미리보기

v1 근거 atom 2,311개를 전부 옮기지 않고, 문장에서 근거 주체와 측정 범위가
명확한 것만 승격시켰다.

| 항목 | 개수 |
|---|---:|
| v1 atom | 2,311 |
| v2 안전 승격 observation | 16 |
| 실제 회의횟수 | 2 |
| 공식 단가 지침 | 14 |
| 명시적 target→evidence link | 2 |
| 격리 유지 | 2,295 |

2,295개를 삭제하는 것이 아니다. `subject`, `measurement_scope`, `evidence_kind`,
`transfer_policy`를 사람 또는 근거 제약 LLM이 확인하기 전까지 자동 계산에서만
격리한다.

## 5. DB 정리 순서

1. 원문 비용사건·위원회 개체 추출기를 고정한다.
2. 완결 선례 3건을 금액 라벨이 아닌 근거 관계 edge 후보로 수동 검수한다.
3. v2 안전 observation 16개만 먼저 staging한다.
4. DB에 선례가 있는 사례부터 회의횟수·유급위원 수의 근거 주체와 측정 범위를
   수동 검수해 v2에 추가한다.
5. 50건을 회귀하고 거짓 자동계산이 0인지 확인한다.
6. 구조를 고정한 뒤 새 미관측 위원회 의안으로 일반화 성능을 측정한다.

## 재현 명령

```bash
python3 -m backend.scripts.build_committee50_manifest --output /tmp/committee50_manifest.json
python3 -m backend.scripts.audit_committee50_source_entities --output /tmp/committee50_source_entity_audit.json
python3 -m backend.scripts.build_committee50_hierarchical_cases --output /tmp/committee50_hierarchical_cases.json
python3 -m backend.scripts.run_committee_hierarchical_holdout \
  --source /tmp/committee50_hierarchical_cases.json \
  --output /tmp/committee50_hierarchical_results.json
python3 -m backend.scripts.build_committee_semantic_evidence_v2 --output /tmp/committee_evidence_v2_preview.json
python3 -m backend.scripts.build_committee50_db_cleanup_preview \
  --hierarchy /tmp/committee50_hierarchical_results.json \
  --semantic-v2 /tmp/committee_evidence_v2_preview.json \
  --output /tmp/committee50_db_cleanup_preview.json
```

## 현재 판정

- 로컬 50건을 중심으로 DB를 정리하는 방향은 맞다.
- 현재 바로 Supabase를 바꾸는 것은 아니다.
- 검색 점수 튜닝보다 원문 개체 정규화와 v2 근거 의미 스키마 적재가 우선이다.
- 목표는 50건의 숫자를 외워 맞추는 것이 아니라, DB에 있는 근거를 놓치지 않고
  없는 근거는 HITL로 넘기는 것이다.
