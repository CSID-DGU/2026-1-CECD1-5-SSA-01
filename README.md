# 법안 비용추계 자동화

의안 원문 PDF를 올리면 **조문 분석 → 근거 수집 → 계산 → 비용추계서 초안**까지 만들어 주는 서비스입니다.
모든 숫자에 기관·문서·기준시점·공개일이 붙고, 발의일 이후에 공개된 자료는 쓰지 않습니다.

## 핵심 설계

AI는 **판단**만 하고, **숫자와 계산은 코드**가 책임집니다.

| 단계 | 담당 | 하는 일 |
|---|---|---|
| ① 문서 읽기 | 코드 | PDF 텍스트, 의안번호, 발의일(= 자료 사용 기준일) |
| ② 조문 분석 | AI | 지급대상·지급액·지급연도·추계 제외 항목 설계 → 코드가 인용문과 금액을 원문과 글자 단위로 대조, 틀리면 되돌려 다시 쓰게 함 |
| ③ 원장 검색 | 코드 | 기준정보 원장(3,200여 행)에서 발의일 이전 공개 자료만, 이 의안 자신의 정답값은 제외 |
| ④ 근거 선택 | AI | 후보 중 조문 범위·기준시점이 맞는 행 선택 (후보 밖 ID는 코드가 거부) |
| ⑤ 웹 검색 | AI + 코드 | 원장에 없는 값만 웹에서 찾고, 코드가 원문 페이지를 직접 열어 숫자를 확인 |
| ⑥ 계산 | 코드 | 공개일·단위·합계 점검 후 계산, 비용추계서 초안 생성 |

## 결과 (AI가 해당 의안의 추계서를 보지 않고 실행)

| 의안 | 이 시스템 | 국회예산정책처 | 오차 |
|---|---:|---:|---:|
| 민생회복지원금 지급을 위한 특별법안 (2200563) | 13조 2,882억원 | 13조 3,227억원 | −0.26% |
| 2024년 민생위기 극복을 위한 특별조치법안 (2200037) | 12조 8,313억원 ~ 17조 9,639억원 | 12조 8,193억원 ~ 17조 9,471억원 | +0.09% |
| 청년농어민기본소득에 관한 법률안 (2211090) | 611억원 | 1조 825억원 | −94% (대상자 통계 오선택, 개선 중) |

## 실행

```bash
pip install -r requirements.txt
cd frontend && npm ci && npx vite build --config vite.nabo.config.js && cd ..
NABO_ACCESS_KEY=<접속 비밀번호> python3 -m backend.nabo_style.web     # http://localhost:8010
cloudflared tunnel --url http://localhost:8010                          # (선택) 외부 공개 주소
```

`backend/.env`에 `OPENAI_API_KEY`가 필요합니다. 모델은 `NABO_AI_MODEL`(기본 `gpt-6.1-sol`)로 바꿀 수 있습니다.
개발 중에는 `NABO_ACCESS_KEY` 없이 서버를 띄우고 `cd frontend && npx vite`로 `http://localhost:5173/nabo.html`을 엽니다.

## 프로젝트 구조

```
backend/
  nabo_style/            ★ 메인 서비스
    web.py               API 서버 + 화면 서빙 + 비밀번호
    ai_pipeline.py       업로드 → AI 판단 → 코드 검증 → 계산 파이프라인
    support_payment.py   현금 지원금 산식 계산기 (모든 값에 근거 카드)
    ledger.py            기준정보 원장 (큐레이션 + ERCE DB 읽기 전용 + 추계서 추출 + 웹 추가분)
    ledger_search.py     자연어 원장 검색 → AI 검색어 변환 → 웹 검색
    report.py            비용추계서 초안 (국회예산정책처 회답서 체계, PDF·Word)
    display.py           화면용 짧은 출처·단위 표기
    data/                큐레이션 원장
    research/            원장·선례 구축에 쓴 연구용 스크립트
  erce/, server.py, …    이전 엔진 ERCE (원장 데이터 원천, 비교용으로 보존)
  scripts/               의안 PDF 수집 등 데이터 수집 도구
  tests/                 테스트
  legacy/                지금 쓰지 않는 실험 엔진 (committee·tag·engines·subsidy 등, 삭제 없이 보관)
  generated/             수집·가공 데이터 (git 제외)
frontend/
  nabo.html, src/nabo/   ★ 서비스 화면 (새 추계 / 추계 내역 / 기준정보 원장)
  index.html, src/*.jsx  이전 ERCE 화면
docs/
  nabo_style/            서비스 비교 기록·정답 대조 (코드가 참조)
  erce/                  ERCE 사례 기록 (코드가 참조)
  career/                포트폴리오·면접 문서
  archive/               이전 설계 문서·실험 로그·옛 README
archive/                 이전 산출물·데이터 묶음·면접 준비 자료
조례안/, 비용추계서/       ERCE가 쓰는 원자료
```

## API

인증: `Authorization: Bearer <NABO_ACCESS_KEY>` (브라우저는 로그인 쿠키)

| 용도 | 방식 | 경로 |
|---|---|---|
| 추계 시작 (`pdf_b64` 또는 `bill_no`) | POST | `/api/nabo/ai/run` |
| 진행 상황·결과 | GET | `/api/nabo/ai/job/{job}` |
| 추계 내역 / 상세 | GET | `/api/nabo/ai/runs`, `/api/nabo/ai/run/{run_id}` |
| 값 직접 입력 후 재계산 | POST | `/api/nabo/ai/recompute` |
| 비용추계서 초안 (`?format=doc`면 Word) | GET | `/api/nabo/ai/report/{run_id}` |
| 의안 원문 PDF | GET | `/api/nabo/ai/pdf/{run_id}` |
| 원장 검색 / AI 검색 / 웹 검색 / 원장 추가 | GET·POST | `/api/nabo/ledger`, `/ledger/ai`, `/ledger/web`, `/ledger/add` |

## 지원 범위와 한계

- 현재 **현금 지원금**(수당·지원금·기본소득) 법안을 지원합니다.
- 웹 검색으로 가져온 값의 공개일은 AI 보고값이며, 화면에 그 사실을 표시합니다.
- 비용추계서는 **초안**이며 담당자 검토가 필요합니다.
