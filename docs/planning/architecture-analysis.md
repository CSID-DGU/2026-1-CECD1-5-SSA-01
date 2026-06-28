# 비용추계 자동화 시스템 - 기획서 분석 및 구현 계획

> 작성일: 2026-04-23  
> 기반 문서: 비용추계자동화시스템기획서.md

---

## 📋 프로젝트 개요

**과제명**: 테이블 증강생성(TAG) 기술 기반 '비용추계 자동화' 시스템 개발

**핵심 목표**: 법안(PDF/HWP)을 업로드하면 AI가 비용 유발 조항을 분석하고, 관련 통계·단가를 자동으로 찾아 **비용추계서(표+텍스트)**를 자동 생성하는 시스템

**해결하는 문제**:
- 기존 생성형 AI(LLM)의 **수치 연산 오류(Hallucination)** 문제 해결
- 산출 근거 부재 문제 → **Evidence Tracing** 기능으로 해결
- 비용추계 인력 부족 → **자동화**로 해결 (10시간 → 1시간)

---

## 🏗️ 시스템 아키텍처 (3계층 구조)

### Layer 1: User Interface (UI/UX)
| 구성요소 | 설명 |
|---------|------|
| **법안 업로드** | HWP/PDF 문서 업로드 인터페이스 |
| **추계 대시보드** | Web Editor 기반 실시간 편집/조회 |
| **Human-in-the-Loop 검증** | 사용자가 AI 결과를 검토/수정하는 도구 |

### Layer 2: AI Core Engine (TAG & Logic)
| 모듈 | 세부 기능 |
|------|---------|
| **전처리 모듈** | OCR/Table Parsing, 비용조항 추출, 메타데이터 태깅 |
| **TAG Main Engine** | Retriever(Semantic Search) + Generator(LLM) + Calculator(Python Sandbox) |
| **후처리 모듈** | 보고서 포맷팅, 근거 데이터 매핑, 할루시네이션 필터 |

### Layer 3: Data Infrastructure
| 저장소 | 데이터 유형 |
|--------|-----------|
| **법령/조례 DB** | Raw Text (원문) |
| **비용추계 선례 DB** | Structured Table (과거 추계서) |
| **공공 통계 API** | KOSIS/OpenData 연동 |
| **Vector Store** | Embeddings (벡터 검색용) |

> **핵심 설계 원칙**: LLM은 **로직(Python 코드)만 생성**하고, 실제 수치 계산은 **샌드박스 Python Solver**가 수행 → 계산 정확도 99% 보장

---

## ⚙️ 시스템 작동 흐름 (3단계 파이프라인)

### Step 1: 비용 유발 조문 추출 (RAG + LLM)
- 원문 구조화
- 비용 유발 조문 추출
- 조문/트리거 추출 (대상, 인원)
- 재정 키워드 식별 (Must/May)

### Step 2: 비용 구성 가설 추론 (LLM)
- 유사 사례 참조 (Few-shot)
- 비용 항목 시나리오 생성
- 가설 수립 (인건비, 운영비 등)
- 기존 비용추계서 DB 참조

### Step 3: 비용 계산 및 추계 (TAG)
- Table QA & 연산
- 정형 데이터 쿼리 (공무원임금표, 연구과제별 예산통계 등)
- 수식 매핑 및 계산
- 근거 포함 산출 내역 (XAI) 매핑

**출력물**: 비용추계서 (HWP/PDF 표준 서식) + 산출 기초 설명

---

## 🎯 정량적 목표

| 지표 | 목표치 | 측정 방법 |
|------|-------|---------|
| 비용항목 식별 정확도 | **90% 이상** | F1-Score |
| 산출근거 매핑 정확도 | **85% 이상** | Top-3 Hit Rate |
| 비용계산 정확도 | **99%** | 오차 허용 1% 이내 |
| 문서작성 시간 단축률 | **90% 이상** | 10시간 → 1시간 |
| 사용자 만족도 | **4.0/5.0 이상** | 설문조사 |

---

## 🧪 검증 프로세스 (3단계)

| 단계 | 방법 | 내용 |
|------|------|------|
| **1단계: Unit Test** | 과거 데이터 100건 | Gold Standard 설정, AI vs 실제 수치 비교 |
| **2단계: Integration Test** | 전문가 블라인드 평가 | 5인 전문가 논리적 흐름·서식 완성도 5점 척도 |
| **3단계: Pilot Test** | 현장 시범 적용 | 지방의회 협력기관, 수정 횟수·만족도 조사 |

**고도화**: Error Analysis → 모델 Fine-tuning → UI/UX 개선 반복

---

## 🔧 핵심 기술 모듈

### 데이터 엔지니어링
- HWP/PDF 파서 (OCR + Table Parsing)
- 국회 비용추계서 1만 건 수집 파이프라인
- 통계청(KOSIS) API 연동
- 테이블 구조(Header-Value) 보존 임베딩

### AI 코어 엔진
- **Retriever**: Dual-Encoder 기반 테이블 검색기
- **Generator**: LLM + Chain-of-Thought 프롬프팅
- **Calculator**: Python Sandbox (Symbolic Solver) + 이상 탐지

### 후처리 및 출력
- 보고서 포맷팅 (HWP/PDF 표준 서식)
- Evidence Tracing (근거 역추적 + 하이라이트)
- 할루시네이션 필터

### 웹 인터페이스
- 법안 업로드 UI
- 추계 대시보드 (Web Editor)
- Human-in-the-Loop 검토/수정 도구

---

## 📐 추천 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | Python (FastAPI) |
| **Frontend** | Next.js (React) |
| **LLM** | OpenAI GPT-4o / Claude API |
| **Vector DB** | Pinecone / Weaviate / ChromaDB |
| **RDBMS** | PostgreSQL |
| **문서 파싱** | pyhwp, PyMuPDF, Camelot |
| **임베딩** | Sentence-Transformers / OpenAI Embeddings |
| **Sandbox** | RestrictedPython / Docker Container |
| **배포** | Docker + AWS/GCP |

---

## 👥 연구팀 구성 (7명)

| 역할 | 인원 | 담당 업무 |
|------|------|---------|
| 기술책임자 | 1명 | AI 시스템 아키텍처 설계 총괄 (경력 20년+) |
| AI 코어팀 | 2명 | NLP/LLM 파인튜닝, TAG 검색 엔진 최적화 |
| 시스템 개발팀 | 2명 | 데이터 파이프라인, Python 연산 엔진 구현 |
| 도메인 전문가 | 2명 | 비용추계 로직 검수, 학습 데이터 QA |

---

## 📈 기대효과

- **업무 혁신**: 수작업 비용추계 → 자동화 (효율 10배 향상)
- **신뢰성 확보**: 설명 가능한 AI(XAI)로 투명한 산출 근거 제시
- **비용 절감**: 건당 수천만원 외부 용역 → 월 구독형 AI 시스템
- **시장 창출**: 금융(심사), 건설(적산) 등 타 산업 확장 가능
