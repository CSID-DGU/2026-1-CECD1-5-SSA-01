# 비용추계 DB 구축 파이프라인 진행상황

## 현재 Supabase 데이터 현황 (2026-05-21 기준)

### assembly_chunks (RAG 벡터 검색 대상)
| 구분 | chunks | 임베딩 | 상태 |
|------|--------|--------|------|
| 21대 추계서 | 8,312 | ✅ 완료 | |
| 21대 미첨부 | 6,357 | ✅ 완료 | |
| 22대 추계서 | 22,740 | 🔄 진행 중 | 임베딩 71% |
| 22대 미첨부 | 6,563 | ✅ 완료 | |
| legal_reference | 525 | ✅ 완료 | |
| **합계** | **~44,497** | | |

### 수집 범위
| 대수 | 추계서 | 미첨부 | 비고 |
|------|--------|--------|------|
| 21대 | 402건 | 417건 | 완료 |
| 22대 1차 | 993건 | 499건 | 추계서 임베딩 중 |
| 22대 2차 예정 | ~1,000건 | ~500건 | 미수집 |
| 22대 3차 예정 | ~1,185건 | ~500건 | 미수집 |

### TAG 구조화 (Supabase)
| 테이블 | 건수 | 상태 |
|--------|------|------|
| cost_estimate_structures | 402 | ✅ 21대 완료 |
| cost_estimate_items | 852 | ✅ 21대 완료 |
| cost_estimate_variables | 2,192 | ✅ 21대 완료 |
| cost_estimate_amounts | 4,254 | ✅ 21대 완료 |
| non_attachment_classifications | 201 | ⏸️ 스킵 |
| bill_cost_triggers | 8 | ⚠️ 미생성 |

## 수집 범위

- **21대 국회**: 819건 수집 완료 (추계서 402건 + 미첨부 417건)
  - 디스커버리: 5,000건 조회 → 에러 3,001건 (ZIP 다운로드 실패)
  - TAG 구조화: 로컬 JSONL 완료, Supabase 절반만 업로드됨
- **22대 국회**: 487건 조회 (추계서 11건, 미첨부 9건 확인) → 파이프라인 미실행
- **법령 참조 (legal_reference)**: 미적재

---

## 작업 로그

### [2026-05-21] TAG 구조화 데이터 전체 업로드

**목표**: 로컬 JSONL(402건)을 Supabase에 전량 업로드 (기존 199건 삭제 후 재삽입)

**실행 명령**:
```
python -m backend.scripts.upload_tag_structures_to_supabase --seed-dir backend/generated/assembly_rag_seed
```

**확인 결과**:
- TAG 추출은 로컬 JSONL에 이미 완료됨 (Gemini API 추가 호출 없음)
- cost_estimate_structures: 로컬 402건 / Supabase 199건 → **203건 미업로드**
- non_attachment: 로컬 417건 / Supabase 201건 → 216건 미업로드 (스킵 예정)
- Supabase에만 있고 로컬 없는 데이터: 0건 (불일치 없음)

**스크립트 수정 내용**:
- `upload_tag_structures_to_supabase.py`: `--skip-existing` (누락분만 추가), `--skip-non-attachment` 옵션 추가
- `extract_tag_structures.py`: `--skip-non-attachment` 옵션 추가 (이후 22대 추출 시 비용 절감)

**실행 명령**:
```
python -m backend.scripts.upload_tag_structures_to_supabase \
  --seed-dir backend/generated/assembly_rag_seed \
  --skip-existing --skip-non-attachment --skip-embedding
```

---

## 다음 작업 목록

- [x] TAG 구조화 데이터 전체 업로드 완료 (2026-05-21)
- [x] 22대 국회 디스커버리 완료 (2026-05-21, 25.5분)
  - 추계서: 3,185건 / 미첨부: 3,263건 / 에러: 112건
  - 저장: `backend/generated/cost_estimate_discovery_22.json`
- [x] 22대 1차 수집 완료 (추계서 993건 + 미첨부 499건)
- [x] 22대 1차 upload 완료
- [x] 22대 미첨부 임베딩 완료 (6,563건)
- [x] 22대 추계서 임베딩 완료 (22,740건)
- [x] 22대 추계서 TAG 추출 완료 (993건 → 976건 구조화)
- [x] 22대 TAG Supabase 업로드 완료 (structures 976 / items 2,494 / variables 7,613 / amounts 13,613)
- [ ] 22대 2차 수집 (추계서 ~1,000건 + 미첨부 ~500건)
- [ ] 22대 3차 수집 (나머지)
- [ ] TAG → analyzer 연결 (구조적 미연결 해결)
- [ ] 법령 참조 데이터 적재 (ingest_legal_reference)
- [ ] bill_cost_triggers 생성 (extract_tag_structures 재실행 필요)

### [2026-05-21] 22대 디스커버리

- 22대 전체 의안: 17,263건
- 목표: 추계서(cost_estimate) 있는 의안 발굴
- 출력: `backend/generated/cost_estimate_discovery_22.json`
- 옵션: concurrency=12, 전수조회
