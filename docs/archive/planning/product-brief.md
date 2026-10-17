# 🚀 프로젝트 포트폴리오: 비용추계 자동화 시스템

## 1. 프로젝트 개요 (Project Overview)
* **프로젝트명**: 테이블 증강생성(TAG) 기술 기반 '비용추계 자동화' AI 시스템
* **한 줄 소개**: 생성형 AI와 파이썬 연산 엔진을 결합하여, 법안의 비용추계서를 자동으로 생성하고 근거를 투명하게 역추적하는 고신뢰 AI 시스템
* **개발 배경**: 법률안이나 자치법규 시행 시 예상되는 비용을 추산하는 '비용추계'는 필수 행정절차이나, 추계 인력의 절대적 부족과 업무의 비표준화로 인해 지연 및 부실화가 발생하고 있음 (예: 서울시의회 전체 자치법규 중 5%만 추계)

## 2. 문제 정의 및 해결 방안 (Problem & Solution)

### 기존의 문제점 (Pain Points)
1. **생성형 AI(LLM)의 한계**: 기존 RAG(검색 증강 생성) 기술은 일반 텍스트에는 강하나, 가격이나 임금 등 표(Table) 형태의 정형 데이터에 취약함.
2. **수치 연산의 할루시네이션(환각)**: LLM이 직접 연산을 수행할 경우 발생하는 고질적인 계산 오류 문제.
3. **산출 근거의 부재**: 계산된 결과값이 어떤 통계나 법령을 기준으로 산출되었는지 출처를 확인할 수 없음.

### 해결 방안 (Solutions)
1. **테이블 증강생성 (TAG, Table Augmented Generation)**: 정형 데이터에 특화된 검색 기술을 도입하여, 과거 산출 내역표와 통계청 표 데이터를 정확하게 검색하고 프롬프트에 증강함.
2. **하이브리드 엔진 (무결점 수치 연산)**: LLM은 문제를 분석하고 '계산 로직(Python Code)'만을 생성하며, 실제 계산은 파이썬 샌드박스(Symbolic Solver) 환경에서 실행하여 연산 정확도 100%를 보장.
3. **Evidence Tracing (근거 역추적)**: 산출된 수치의 원본 출처(통계표, 관련 법령 등)를 하이라이트하여 보여주는 '설명 가능한 AI(XAI)' 기술을 적용해 행정 문서로서의 신뢰성 확보.

## 3. 핵심 기능 (Core Features)
* **비용 조항 자동 추출**: PDF 및 HWP 형식의 법안 업로드 시, 문서를 파싱하고 RAG 및 LLM을 활용하여 비용 유발 조항과 대상/인원(트리거)을 자동 식별.
* **비용 구성 가설 추론**: 과거 비용추계서 DB를 참조하여 인건비, 운영비 등 비용 구성 가설을 수립하고, 공공 통계(KOSIS 등)에서 적절한 단가를 자동으로 매핑.
* **표준 서식 기반 추계서 생성**: 도출된 연산 결과와 근거 데이터를 바탕으로, 실제 업무에 바로 활용 가능한 표준 서식(HWP/PDF)의 비용추계서를 텍스트와 표 형태로 자동 포맷팅.
* **Human-in-the-Loop 대시보드**: AI가 산출한 결과물과 그 산출 근거를 사용자가 웹 에디터 화면에서 직접 검토하고 수정할 수 있는 워크플로우 지원.

## 4. 시스템 아키텍처 및 기술 스택 (Architecture & Tech Stack)

### 3계층 시스템 아키텍처
* **User Interface Layer**: 법안 업로드, Web Editor 기반 추계 대시보드, 검증 및 수정 도구
* **AI Core Engine Layer**: 
  * [전처리] OCR / Table Parsing, 메타데이터 태깅
  * [TAG 엔진] Dual-Encoder 기반 Retriever + Chain-of-Thought Generator + Python Sandbox Calculator
  * [후처리] 근거 매핑(XAI), 할루시네이션 필터링
* **Data Infrastructure Layer**: 법령/조례 원문 DB, 과거 추계서(표) DB, Vector Store, 공공 통계 API 연동

### 주요 기술 스택 (Tech Stack)
* **Backend**: Python (FastAPI)
* **Frontend**: Next.js (React)
* **AI / NLP**: OpenAI GPT-4o / Claude API, Sentence-Transformers (Embeddings)
* **Database / Vector DB**: PostgreSQL (pgvector), Pinecone / ChromaDB
* **Data Engineering**: pyhwp, PyMuPDF, Camelot (문서 파싱 및 표 추출 OCR)
* **Infrastructure**: RestrictedPython / Docker (샌드박스 연산 환경)

## 5. 정량적 성과 목표 및 기대 효과 (Impact & Goals)

### 성과 지표 (KPIs)
* **시간 단축**: 비용추계서 작성 시간 90% 이상 단축 (수작업 시 평균 10시간 → 1시간 이내)
* **비용 조항 식별 정확도**: 90% 이상 (F1-Score 기준)
* **연산 정확도**: 99% 이상 보장 (오차 허용 1% 이내)
* **산출근거 매핑 정확도**: 85% 이상 (Top-3 Hit Rate 기준)

### 기대 효과
* **행정 업무 혁신**: 수작업에 의존하던 추계 업무를 자동화하여 공무원의 업무 효율을 극대화.
* **예산 절감**: 건당 수천만 원에 달하는 고가의 외부 학술 용역을 월 구독형 AI 시스템으로 대체.
* **확장성(Scalability)**: 구축된 수치 연산 특화 고신뢰 AI 모델을 금융(심사), 건설(적산) 등 타 산업의 테이블 데이터 분석 솔루션으로 확장 가능.
