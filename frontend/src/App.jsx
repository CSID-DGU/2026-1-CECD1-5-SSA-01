import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

const PIPELINE_STEPS = [
  { number: 1, title: 'PDF 파싱 + 조문 분할', tech: 'PyMuPDF' },
  { number: 2, title: '조문별 비용유발 판단', tech: 'Gemini + 법령 RAG' },
  { number: 3, title: '유사 사례 검색',       tech: 'pgvector ANN' },
  { number: 4, title: '추계서 자동 생성',     tech: 'Gemini + TAG' },
]

const VERDICT_META = {
  '추계서':    { label: '비용추계서',                     color: 'red',   emoji: '💰', desc: 'NABO 기준: 연 10억 이상 또는 한시 30억 이상 — 추계서 작성 필수' },
  '미첨부_1호': { label: '미첨부 1호 (비용 미미)',         color: 'green', emoji: '⚪', desc: 'NABO 기준: 연평균 10억 미만 또는 한시 30억 미만' },
  '미첨부_2호': { label: '미첨부 2호 (안보·기밀)',         color: 'gray',  emoji: '🔒', desc: 'NABO 기준: 국가안전보장·군사기밀 관련' },
  '미첨부_3호': { label: '미첨부 3호 (기술적 곤란)',        color: 'amber', emoji: '🟡', desc: 'NABO 기준: 선언적·권고적 또는 시행령 위임 등' },
  '미대상':    { label: '미대상 (재정변화 없음)',           color: 'blue',  emoji: '🔵', desc: 'NABO 기준: 정의 조항, 명칭 변경 등 재정규모 변화 없음' },
  // 기존 분류와의 하위 호환 (legacy)
  '추계필요': { label: '추계 필요',         color: 'red',   emoji: '💰', desc: '비용 발생' },
  '미첨부_A': { label: '비용 없음 (A유형)', color: 'green', emoji: '⚪', desc: '비용 미수반' },
  '미첨부_B': { label: '추계 곤란 (B유형)', color: 'amber', emoji: '🟡', desc: '기술적 곤란' },
  '미첨부_C': { label: '예산 흡수 (C유형)', color: 'blue',  emoji: '🔵', desc: '기존 예산 범위' },
}

const TRIGGER_TYPE_COLOR = {
  '직접지원': 'red', '위탁대행': 'orange', '시설구축': 'amber',
  '조직설치': 'purple', '대상확대': 'pink', '의무부과': 'rose',
  '없음': 'gray',
}

const STRENGTH_LABEL = {
  mandatory: '의무', semi_mandatory: '준의무',
  discretionary: '재량', aspirational: '선언적',
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(r.result)
    r.onerror = () => reject(new Error('파일을 읽지 못했습니다.'))
    r.readAsDataURL(file)
  })
}

function asList(value) {
  if (Array.isArray(value)) return value
  if (value === null || value === undefined) return []
  if (typeof value === 'object') {
    return [value.reason || value.item || JSON.stringify(value)]
  }
  return [String(value)]
}

function App() {
  const [file, setFile] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentStep, setCurrentStep] = useState(-1)
  const [result, setResult] = useState(null)
  const [activeTab, setActiveTab] = useState('articles')
  const [expanded, setExpanded] = useState(null)
  const [modal, setModal] = useState(null)
  const [error, setError] = useState('')
  const [formType, setFormType] = useState(() =>
    localStorage.getItem('formType') || 'gyeonggi'
  )
  useEffect(() => {
    localStorage.setItem('formType', formType)
  }, [formType])
  const fileRef = useRef(null)

  useEffect(() => {
    if (!isProcessing) return
    const t = setInterval(() => setCurrentStep(p => (p < 3 ? p + 1 : p)), 2500)
    return () => clearInterval(t)
  }, [isProcessing])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) { setFile(f); setError('') }
  }, [])

  const start = async () => {
    if (!file) return
    setIsProcessing(true); setResult(null); setError(''); setCurrentStep(0)
    try {
      const content = await fileToDataUrl(file)
      const res = await fetch(`${API_BASE}/api/analyze_v2`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: file.name,
          mimeType: file.type,
          content,
          formType,  // 'gyeonggi' | 'assembly' → 백엔드 분류 기준 분기
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '분석 실패')
      setCurrentStep(4)
      setResult(data)
    } catch (e) {
      setCurrentStep(-1)
      setError(e.message)
    } finally {
      setIsProcessing(false)
    }
  }

  const reset = () => {
    setFile(null); setResult(null); setError(''); setCurrentStep(-1)
    setExpanded(null); setModal(null)
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-logo">
          <div className="header-logo-icon">⚖️</div>
          <div>
            <h1>비용추계 자동화 시스템</h1>
            <span>RAG + TAG 기반 조례안 분석</span>
          </div>
        </div>
        <div className="header-right">
          <div className="form-toggle">
            <span className="form-toggle-label">양식</span>
            <button
              className={`form-toggle-btn ${formType === 'gyeonggi' ? 'active' : ''}`}
              onClick={() => setFormType('gyeonggi')}
            >
              경기도
            </button>
            <button
              className={`form-toggle-btn ${formType === 'assembly' ? 'active' : ''}`}
              onClick={() => setFormType('assembly')}
            >
              국회
            </button>
          </div>
        </div>
      </header>

      <main className="main">
        {!result && (
          <>
            <section className="hero">
              <h2>
                <span className="gradient-text">조례안 PDF</span> 한 장이면<br />
                <span className="gradient-text">비용추계서</span>가 자동으로
              </h2>
              <p>
                과거 의안 819건 + 비용추계 법령 PDF + AI가 함께 분석합니다.<br />
                조문별 판단 · 종합 결론 · 산식 생성 · 근거 추적까지.
              </p>
            </section>

            <section className="upload-section">
              <div
                className={`upload-zone ${isDragging ? 'dragging' : ''}`}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileRef.current?.click()}
              >
                <input ref={fileRef} type="file" accept=".pdf"
                  onChange={(e) => { setFile(e.target.files[0]); setError('') }}
                  style={{ display: 'none' }} />
                <div className="upload-icon">📑</div>
                <h3>조례안 PDF를 끌어다 놓거나 클릭하세요</h3>
                <p>입법예고문, 조례안 원문 — 어떤 형식이든 OK</p>
                <div className="upload-formats"><span>PDF</span></div>
              </div>

              {file && (
                <div className="file-selected animate-fade-in">
                  <span className="file-selected-icon">📄</span>
                  <div className="file-selected-info">
                    <div className="name">{file.name}</div>
                    <div className="size">{(file.size / 1024).toFixed(1)} KB</div>
                  </div>
                  <button className="file-selected-remove"
                    onClick={(e) => { e.stopPropagation(); reset() }}>✕</button>
                </div>
              )}

              {error && <div className="status-banner error">{error}</div>}

              <button className="start-btn" disabled={!file || isProcessing} onClick={start}>
                {isProcessing ? '분석 중...' : '비용추계 분석 시작 →'}
              </button>
            </section>
          </>
        )}

        {currentStep >= 0 && !result && (
          <section className="pipeline-section animate-fade-in">
            <div className="pipeline-header">
              <span>⚙️</span>
              <h3>AI가 4단계로 분석 중</h3>
            </div>
            <div className="pipeline-steps">
              {PIPELINE_STEPS.map((step, idx) => (
                <div key={step.number} className={`pipeline-step ${
                  currentStep === idx ? 'active' : currentStep > idx ? 'completed' : ''
                }`}>
                  <div className="pipeline-step-number">
                    {currentStep > idx ? '✓' : step.number}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div className="pipeline-step-title">{step.title}</div>
                    <div className="pipeline-step-tech">{step.tech}</div>
                  </div>
                  {currentStep === idx && isProcessing && (
                    <div className="pipeline-step-spinner">
                      <div className="spinner" />처리 중
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {result && (
          <section className="animate-fade-in">
            <div className="result-hero">
              <button className="back-btn" onClick={reset}>← 새 조례안 분석</button>
              <h2 className="result-title">{result.billName}</h2>
              <div className="result-meta">
                <span>📅 {result.generatedAt}</span>
                <span>⚡ {result.elapsedSec}s</span>
                <span>📋 {result.totalArticles}개 조문 분석</span>
              </div>
            </div>

            <VerdictCard verdict={result.verdict} field={result.field} />
            {result.qaReport && <QaReport report={result.qaReport} />}

            <div className="tab-bar">
              <button className={`tab ${activeTab === 'articles' ? 'active' : ''}`}
                onClick={() => setActiveTab('articles')}>
                📋 조문별 분석 <span className="tab-count">{(result.articles || []).length}</span>
              </button>
              <button className={`tab ${activeTab === 'estimate' ? 'active' : ''}`}
                onClick={() => setActiveTab('estimate')}>
                💰 추계서 / 사유서
              </button>
              <button className={`tab ${activeTab === 'form' ? 'active' : ''}`}
                onClick={() => setActiveTab('form')}>
                📄 추계서 양식 <span className="tab-count">{formType === 'gyeonggi' ? '경기도' : '국회'}</span>
              </button>
              <button className={`tab ${activeTab === 'evidence' ? 'active' : ''}`}
                onClick={() => setActiveTab('evidence')}>
                📚 RAG 근거
              </button>
            </div>

            {activeTab === 'articles' && (
              <ArticlesView
                articles={result.articles || []}
                expanded={expanded}
                setExpanded={setExpanded}
                openModal={setModal}
              />
            )}
            {activeTab === 'estimate' && (
              <EstimateView
                result={result}
                estimate={result.estimate}
                nonAttachment={result.nonAttachment}
                refs={result.references}
                formType={formType}
                onResult={setResult}
                openModal={setModal}
              />
            )}
            {activeTab === 'form' && (
              <FormView result={result} formType={formType} setFormType={setFormType} />
            )}
            {activeTab === 'evidence' && (
              <EvidenceView refs={result.references} openModal={setModal} />
            )}
          </section>
        )}
      </main>

      {modal && <Modal data={modal} onClose={() => setModal(null)} />}
    </div>
  )
}

function QaReport({ report }) {
  if (!report || !report.issues || report.issues.length === 0) return null
  const tone = report.has_error ? 'qa-error' : report.has_warn ? 'qa-warn' : 'qa-ok'
  return (
    <div className={`qa-report ${tone}`}>
      <div className="qa-header">
        <span className="qa-summary">{report.summary}</span>
        <span className="qa-count">{report.issue_count}건 점검</span>
      </div>
      <div className="qa-issues">
        {report.issues.map((iss, i) => (
          <div key={i} className={`qa-issue qa-level-${iss.level}`}>
            <div className="qa-issue-head">
              <span className="qa-issue-badge">{iss.level === 'error' ? '❌' : iss.level === 'warn' ? '⚠️' : 'ℹ️'}</span>
              <span className="qa-issue-cat">{iss.category}</span>
            </div>
            <div className="qa-issue-detail">{iss.detail}</div>
            <div className="qa-issue-action">→ {iss.action}</div>
            {iss.items && (
              <div className="qa-issue-items">
                {Object.entries(iss.items).map(([name, vars]) => (
                  <div key={name} className="qa-item-block">
                    <div className="qa-item-name">[{name}]</div>
                    <div className="qa-item-vars">
                      {asList(vars).map((v, j) => <span key={j} className="qa-var-chip">{String(v)}</span>)}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {iss.missing_vars && iss.missing_vars.length > 0 && (
              <div className="qa-item-vars">
                {asList(iss.missing_vars).map((v, j) => <span key={j} className="qa-var-chip">{String(v)}</span>)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function VerdictCard({ verdict, field }) {
  const meta = VERDICT_META[verdict.type] || {
    label: verdict.label, color: 'gray', emoji: '❓', desc: ''
  }
  const confPct = Math.round((verdict.confidence || 0) * 100)
  return (
    <div className={`verdict-card verdict-${meta.color}`}>
      <div className="verdict-emoji">{meta.emoji}</div>
      <div className="verdict-body">
        <div className="verdict-label">{meta.label}</div>
        <div className="verdict-desc">{meta.desc}</div>
        {field && field.field && (
          <div className="verdict-field">📂 분야: <b>{field.field}</b></div>
        )}
        <div className="verdict-summary">{verdict.summary}</div>
        {verdict.nabo_reason && (
          <div className="verdict-nabo">
            <span className="verdict-nabo-label">NABO 기준 근거</span>
            <div className="verdict-nabo-text">{verdict.nabo_reason}</div>
          </div>
        )}
        <div className="verdict-confidence">
          <span>AI 신뢰도</span>
          <div className="confidence-bar">
            <div className="confidence-fill" style={{ width: `${confPct}%` }} />
          </div>
          <span className="confidence-pct">{confPct}%</span>
        </div>
      </div>
    </div>
  )
}

function ArticlesView({ articles, expanded, setExpanded, openModal }) {
  const triggered = articles.filter(a => a.cost_trigger).length
  return (
    <div className="animate-fade-in">
      <div className="articles-stats">
        <div className="stat-box red">
          <div className="stat-num">{triggered}</div>
          <div className="stat-label">비용 유발 조문</div>
        </div>
        <div className="stat-box gray">
          <div className="stat-num">{articles.length - triggered}</div>
          <div className="stat-label">비용 없음</div>
        </div>
      </div>

      <div className="articles-list">
        {articles.map((art, i) => (
          <ArticleRow
            key={i}
            art={art}
            isExpanded={expanded === i}
            onToggle={() => setExpanded(expanded === i ? null : i)}
            openModal={openModal}
          />
        ))}
      </div>
    </div>
  )
}

function ArticleRow({ art, isExpanded, onToggle, openModal }) {
  const tColor = TRIGGER_TYPE_COLOR[art.trigger_type] || 'gray'
  return (
    <div
      className={`article-row ${art.cost_trigger ? 'triggered' : 'safe'} ${isExpanded ? 'expanded' : ''}`}
      onClick={onToggle}
    >
      <div className="article-row-main">
        <div className="article-row-no">
          {art.cost_trigger ? '🔴' : '⚪'} {art.no}
        </div>
        <div className="article-row-meta">
          {art.cost_trigger ? (
            <>
              <span className={`badge badge-${tColor}`}>{art.trigger_type}</span>
              <span className="strength-text">
                {STRENGTH_LABEL[art.obligation_strength] || art.obligation_strength}
              </span>
            </>
          ) : (
            <span className="badge badge-gray">비용 없음</span>
          )}
        </div>
        {!isExpanded && (
          <div className="article-row-reason">{art.reason}</div>
        )}
        <div className="article-row-chevron">›</div>
      </div>

      {isExpanded && (
        <div className="article-detail">
          <div className="detail-block">
            <div className="detail-label">📄 AI 판단 근거</div>
            <div className="article-text-box">{art.reason}</div>
          </div>

          <div className="detail-block">
            <div className="detail-label">📜 조문 원문</div>
            <div className="article-text-box">{art.text}</div>
          </div>

          {art.legal_refs && art.legal_refs.length > 0 && (
            <div className="detail-block">
              <div className="detail-label">⚖️ 비용추계와 이해 (법령 PDF) 인용</div>
              <div className="ref-list">
                {art.legal_refs.map((r, i) => (
                  <div
                    key={i}
                    className="ref-card"
                    onClick={(e) => {
                      e.stopPropagation()
                      openModal({
                        title: '비용추계 이해 (법령 PDF)',
                        meta: `청크 ${r.chunk_id?.slice(-12) || ''} · 유사도 ${Math.round((r.similarity || 0) * 100)}%`,
                        body: r.content,
                      })
                    }}
                  >
                    <div className="ref-card-top">
                      <span className="ref-card-title">📘 법령 PDF · {r.chunk_id?.slice(-8) || ''}</span>
                      <span className="ref-card-sim">{Math.round((r.similarity || 0) * 100)}%</span>
                    </div>
                    <div className="ref-card-preview">{r.content?.slice(0, 100)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {art.similar_refs && art.similar_refs.length > 0 && (
            <div className="detail-block">
              <div className="detail-label">📚 유사 의안 추계서 사례</div>
              <div className="ref-list">
                {art.similar_refs.map((r, i) => (
                  <div
                    key={i}
                    className="ref-card"
                    onClick={(e) => {
                      e.stopPropagation()
                      openModal({
                        title: `${r.bill_no} ${r.bill_name || ''}`,
                        meta: `유사도 ${Math.round((r.similarity || 0) * 100)}%`,
                        body: r.content,
                      })
                    }}
                  >
                    <div className="ref-card-top">
                      <span className="ref-card-title">📋 {r.bill_no} · {r.bill_name?.slice(0, 25) || ''}</span>
                      <span className="ref-card-sim">{Math.round((r.similarity || 0) * 100)}%</span>
                    </div>
                    <div className="ref-card-preview">{r.content?.slice(0, 100)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SimilarCasesTable({ items, openModal }) {
  if (!items || items.length === 0) return null
  return (
    <div className="similar-cases">
      <div className="similar-cases-label">참고한 유사 사례</div>
      <table className="similar-cases-table">
        <thead>
          <tr>
            <th>의안번호</th>
            <th>법률명</th>
            <th>유사도</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.slice(0, 5).map((it, i) => (
            <tr key={i}>
              <td className="bill-no">{it.bill_no || '—'}</td>
              <td className="bill-name">{(it.bill_name || '').slice(0, 38)}</td>
              <td className="bill-sim">{Math.round((it.similarity || 0) * 100)}%</td>
              <td>
                <button
                  className="sim-view-btn"
                  onClick={() => openModal({
                    title: `${it.bill_no} ${it.bill_name || ''}`,
                    meta: `유사도 ${Math.round((it.similarity || 0) * 100)}%`,
                    body: it.content,
                  })}
                >
                  보기
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EstimateView({ result, estimate, nonAttachment, refs, formType, onResult, openModal }) {
  const similarCE = refs?.similar_bills_cost_estimate || []
  const similarNA = refs?.similar_bills_non_attachment || []
  const [drafts, setDrafts] = useState({})
  const [isRecomputing, setIsRecomputing] = useState(false)
  const [recomputeError, setRecomputeError] = useState('')

  const setDraft = (index, key, value) => {
    setDrafts(prev => ({
      ...prev,
      [index]: {
        ...(prev[index] || {}),
        [key]: value,
      },
    }))
  }

  const toNumber = value => {
    if (value === '' || value === null || value === undefined) return null
    const parsed = Number(String(value).replace(/,/g, ''))
    return Number.isFinite(parsed) ? parsed : null
  }

  const recompute = async () => {
    if (!estimate) return
    const userInputs = (estimate.items || []).map((item, index) => {
      const draft = drafts[index] || {}
      const baseAmount = toNumber(draft.base_amount_thousand)
      const unitCost = toNumber(draft.unit_cost)
      const target = toNumber(draft.target)
      const calc = item.calculation || {}
      const input = {
        item_index: index,
        recurrence: draft.recurrence || calc.recurrence || 'annual',
        start_year: toNumber(draft.start_year) || calc.start_year || 1,
        end_year: toNumber(draft.end_year) || calc.end_year || 5,
        growth_variable: draft.growth_variable ?? calc.growth_variable ?? null,
      }
      if (baseAmount !== null) {
        input.base_amount_thousand = baseAmount
      } else if (unitCost !== null || target !== null) {
        input.variables = {
          unit_cost: unitCost || 0,
          target: target || 1,
        }
      } else {
        return null
      }
      return input
    }).filter(Boolean)

    if (userInputs.length === 0) {
      setRecomputeError('재계산할 단가, 대상 수 또는 연간 기준금액을 입력하세요.')
      return
    }

    setIsRecomputing(true)
    setRecomputeError('')
    try {
      const res = await fetch(`${API_BASE}/api/recompute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          result,
          estimate,
          userInputs,
          formType,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || '재계산 실패')
      onResult(data)
    } catch (e) {
      setRecomputeError(e.message)
    } finally {
      setIsRecomputing(false)
    }
  }

  if (nonAttachment) {
    return (
      <div className="animate-fade-in">
        <div className="non-attach-card">
          <h3>📋 비용추계서 미첨부 사유서</h3>
          <div className="na-type-badge">{nonAttachment.type}유형</div>
          <p className="na-reason">{nonAttachment.reason_text}</p>
        </div>
        <SimilarCasesTable
          items={similarNA.length ? similarNA : similarCE}
          openModal={openModal}
        />
      </div>
    )
  }
  if (!estimate) {
    return <div className="empty">생성된 추계서가 없습니다.</div>
  }
  return (
    <div className="estimate-view animate-fade-in">
      <h3>💰 자동 생성 비용추계서</h3>
      {estimate.calculation_status && (
        <div className={`calc-status ${
          estimate.calculation_status.startsWith('computed')
            ? 'ok'
            : estimate.calculation_status.startsWith('estimated')
              ? 'estimated'
              : 'blocked'
        }`}>
          <span className="calc-status-label">계산 상태</span>
          <span>
            {estimate.calculation_status === 'computed_by_python'
              ? 'Python 계산기가 산출했습니다.'
              : estimate.calculation_status === 'computed_by_special_template'
                ? '국회 특별위원회 신설 템플릿으로 산출했습니다.'
              : estimate.calculation_status === 'estimated_by_tag'
                ? '유사 비용추계서 기반 초안입니다. 확인이 필요합니다.'
              : estimate.calculation_status === 'blocked_missing_variables'
                ? '필수 변수가 부족해 금액 계산을 차단했습니다.'
              : estimate.calculation_status === 'awaiting_user_input'
                ? '단가·대상 입력 후 재계산이 필요합니다.'
                : '구조화 산식이 없어 금액 계산을 차단했습니다.'}
          </span>
        </div>
      )}
      {estimate.verification_needed && Object.keys(estimate.verification_needed).length > 0 && (
        <div className="verify-block">
          <div className="verify-title">확인 필요 변수</div>
          {Object.entries(estimate.verification_needed).map(([name, vars]) => (
            <div key={name} className="verify-row">
              <span className="verify-name">{name}</span>
              <div className="vars-list">
                {asList(vars).map((v, j) => <span key={j} className="var-chip">{String(v)}</span>)}
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="estimate-items">
        {(estimate.items || []).map((item, i) => (
          <div key={i} className="estimate-item-card">
            <div className="estimate-item-header">
              <span className="item-order">{i + 1}</span>
              <div>
                <div className="item-name">{item.name}</div>
                <div className="item-category">{item.category} · 근거 {item.trigger_ref}</div>
              </div>
            </div>
            <div className="estimate-formula">
              <span className="formula-label">산식</span>
              <code>{item.formula}</code>
            </div>
            {item.formula_template && (
              <div className="formula-template-block">
                <div className="formula-template-head">
                  <span className="formula-template-label">{item.formula_template.label}</span>
                  <span className="formula-template-confidence">
                    신뢰도 {Math.round((item.formula_template.confidence || 0) * 100)}%
                  </span>
                </div>
                <code>{item.formula_template.standard_formula}</code>
                <div className="formula-template-vars">
                  {asList(item.formula_template.variables).map((v, j) => (
                    <span key={j} className="var-chip">{String(v)}</span>
                  ))}
                </div>
                <div className="formula-template-note">{item.formula_template.notes}</div>
                {item.formula_template.tag_formula_evidence?.length > 0 && (
                  <button
                    type="button"
                    className="evidence-mini-btn"
                    onClick={() => openModal({
                      title: `${item.formula_template.label} TAG 근거`,
                      meta: item.formula_template.source || 'TAG 산식 패턴',
                      body: item.formula_template.tag_formula_evidence.map((e, idx) =>
                        `${idx + 1}. ${e.bill_no || ''} ${e.bill_name || ''}\n` +
                        `항목: [${e.item_category || '-'}] ${e.item_name || '-'}\n` +
                        `산식: ${e.formula_text || '-'}\n` +
                        `점수: ${Math.round((e.score || 0) * 100)}`
                      ).join('\n\n'),
                    })}
                  >
                    TAG 산식 근거
                  </button>
                )}
              </div>
            )}
            {item.assumptions && item.assumptions.length > 0 && (
              <div className="assumptions-block">
                <div className="assumptions-label">📐 전제조건 (가정)</div>
                {item.assumptions.map((a, j) => {
                  const needInput = a.needs_user_confirm || a.value === null || a.value === undefined
                  return (
                    <div key={j} className={`assumption-row ${needInput ? 'need-input' : ''}`}>
                      <div className="assumption-head">
                        <span className="assumption-name">{a.name}</span>
                        {needInput ? (
                          <span className="assumption-input-badge">입력 필요</span>
                        ) : (
                          <span className="assumption-value">{typeof a.value === 'number' ? a.value.toLocaleString() : a.value} {a.unit}</span>
                        )}
                      </div>
                      {a.basis && <div className="assumption-basis">{a.basis}</div>}
                    </div>
                  )
                })}
              </div>
            )}
            {(item.reference_unit_costs || (item.reference_unit_cost ? [item.reference_unit_cost] : [])).length > 0 && (
              <div className="ref-cost-block">
                <span className="ref-cost-label">
                  {formType === 'assembly' ? '💡 추천 단가 후보' : '💡 국회 단가 참고값'}
                </span>
                <div className="ref-cost-list">
                  {(item.reference_unit_costs || [item.reference_unit_cost]).slice(0, 3).map((ref, refIdx) => (
                    <div key={refIdx} className="ref-cost-row">
                      <div className="ref-cost-main">
                        <span className="ref-cost-rank">{refIdx + 1}</span>
                        <div>
                          <div className="ref-cost-body">
                            <b>{Number(ref.value).toLocaleString()}{ref.unit}</b>
                            <span className="ref-cost-src"> · {ref.variable_name || '단가'} · 점수 {Math.min(100, Math.round((ref.score || 0) * 100))}</span>
                          </div>
                          <div className="ref-cost-src">{ref.ref_item} ({ref.source})</div>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="use-ref-btn compact"
                        onClick={() => setDraft(i, 'unit_cost', String(ref.value))}
                      >
                        사용
                      </button>
                    </div>
                  ))}
                </div>
                <div className="ref-cost-caveat">{item.reference_unit_cost?.caveat}</div>
              </div>
            )}
            {item.assumption_candidates && item.assumption_candidates.length > 0 && (
              <div className="assumption-candidates-block">
                <span className="assumption-candidates-label">국회 기준값 후보</span>
                <div className="assumption-candidates-list">
                  {item.assumption_candidates.slice(0, 5).map((candidate, idx) => (
                    <div key={idx} className="assumption-candidate-row">
                      <div className="assumption-candidate-main">
                        <span className="assumption-candidate-rank">{idx + 1}</span>
                        <div>
                          <div className="assumption-candidate-value">
                            <b>{candidate.label || candidate.variable_name}</b>
                            <span>
                              {typeof candidate.value === 'number'
                                ? candidate.value.toLocaleString()
                                : candidate.value} {candidate.unit || ''}
                            </span>
                          </div>
                          <div className="assumption-candidate-meta">
                            {candidate.year || '연도 미상'} · 반복 {candidate.repeat_count || 1}건 · {candidate.bill_no} {candidate.bill_name}
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="evidence-mini-btn"
                        onClick={() => openModal({
                          title: `${candidate.label || candidate.variable_name} 후보 근거`,
                          meta: `${candidate.bill_no || ''} ${candidate.bill_name || ''}`,
                          body:
                            `값: ${candidate.value?.toLocaleString?.() || candidate.value} ${candidate.unit || ''}\n` +
                            `연도: ${candidate.year || '-'}\n` +
                            `항목: ${candidate.item_name || '-'}\n` +
                            `반복: ${candidate.repeat_count || 1}건\n\n` +
                            `${candidate.source_text || '근거 문장이 없습니다.'}`,
                        })}
                      >
                        근거
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="recompute-panel">
              <div className="recompute-title">단가·대상 확정</div>
              <div className="recompute-grid">
                <label>
                  <span>단가</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    placeholder="천원 단위"
                    value={drafts[i]?.unit_cost || ''}
                    onChange={(e) => setDraft(i, 'unit_cost', e.target.value)}
                  />
                </label>
                <label>
                  <span>대상 수</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    placeholder="명/개소/건"
                    value={drafts[i]?.target || ''}
                    onChange={(e) => setDraft(i, 'target', e.target.value)}
                  />
                </label>
                <label>
                  <span>연간 기준금액</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    placeholder="직접 입력, 천원"
                    value={drafts[i]?.base_amount_thousand || ''}
                    onChange={(e) => setDraft(i, 'base_amount_thousand', e.target.value)}
                  />
                </label>
                <label>
                  <span>반복</span>
                  <select
                    value={drafts[i]?.recurrence || item.calculation?.recurrence || 'annual'}
                    onChange={(e) => setDraft(i, 'recurrence', e.target.value)}
                  >
                    <option value="annual">매년</option>
                    <option value="one_time">1회성</option>
                  </select>
                </label>
              </div>
              <div className="recompute-subgrid">
                <label>
                  <span>시작</span>
                  <input
                    type="number"
                    min="1"
                    max="5"
                    value={drafts[i]?.start_year || item.calculation?.start_year || 1}
                    onChange={(e) => setDraft(i, 'start_year', e.target.value)}
                  />
                </label>
                <label>
                  <span>종료</span>
                  <input
                    type="number"
                    min="1"
                    max="5"
                    value={drafts[i]?.end_year || item.calculation?.end_year || 5}
                    onChange={(e) => setDraft(i, 'end_year', e.target.value)}
                  />
                </label>
                {item.reference_unit_cost && (
                  <button
                    type="button"
                    className="use-ref-btn"
                    onClick={() => setDraft(i, 'unit_cost', String(item.reference_unit_cost.value))}
                  >
                    {formType === 'assembly' ? '추천값 사용' : '참고값 사용'}
                  </button>
                )}
              </div>
            </div>
            {item.variables_needed && (
              <div className="estimate-variables">
                <span className="vars-label">필요 변수</span>
                <div className="vars-list">
                  {asList(item.variables_needed).map((v, j) => (
                    <span key={j} className="var-chip">{String(v)}</span>
                  ))}
                </div>
              </div>
            )}
            {item.kosis_lookups && item.kosis_lookups.length > 0 && (
              <div className="kosis-block">
                <div className="kosis-label">📊 KOSIS 자동 조회값</div>
                {item.kosis_lookups.map((k, j) => (
                  <div key={j} className="kosis-row">
                    <div className="kosis-name">
                      {k.variable} <span className="kosis-source">({k.source})</span>
                    </div>
                    <div className="kosis-values">
                      {asList(k.year_values).map((yv, idx) => (
                        <span key={idx} className="kosis-year-value">
                          <b>{yv.year || '-'}</b>: {typeof yv.value === 'number'
                            ? (yv.value > 1000 ? yv.value.toLocaleString() : yv.value)
                            : yv.value} {k.unit}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {item.requires_review && (
              <div className="review-note">
                <span>확인 필요: {item.review_reason || '유사사례 기반 추정값입니다.'}</span>
                {item.evidence_basis && (
                  <button
                    className="evidence-mini-btn"
                    onClick={() => openModal({
                      title: `${item.name} 추정 근거`,
                      meta: item.evidence_basis.label || '유사 비용추계서 기반',
                      body: (item.evidence_basis.amount_candidates || []).map((c, idx) =>
                        `${idx + 1}. ${c.bill_no || ''} ${c.bill_name || ''}\n` +
                        `항목: [${c.category || '-'}] ${c.name || '-'}\n` +
                        `금액: ${Number(c.amount_thousand || 0).toLocaleString()}천원 / 점수 ${Math.round((c.score || 0) * 100)}%\n` +
                        `산식: ${c.formula || '-'}`
                      ).join('\n\n') || '표시할 근거가 없습니다.',
                    })}
                  >
                    근거 보기
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="recompute-actions">
        {recomputeError && <span className="recompute-error">{recomputeError}</span>}
        <button className="recompute-btn" disabled={isRecomputing} onClick={recompute}>
          {isRecomputing ? '재계산 중...' : '입력값으로 재계산'}
        </button>
      </div>

      {estimate.year_estimates && estimate.year_estimates.length > 0 && (
        <div className="year-grid">
          {estimate.year_estimates.map((y, i) => (
            <div key={i} className="year-card">
              <div className="year-label">{y.year}차년도</div>
              <div className="year-amount">
                {y.amount_thousand !== null && y.amount_thousand !== undefined
                  ? `${(y.amount_thousand / 1000).toLocaleString()}백만원`
                  : '—'}
              </div>
              {y.requires_review && <div className="year-note warn">확인 필요</div>}
              {y.note && <div className="year-note">{y.note}</div>}
            </div>
          ))}
        </div>
      )}

      <SimilarCasesTable items={similarCE} openModal={openModal} />
    </div>
  )
}

function EvidenceView({ refs, openModal }) {
  return (
    <div className="animate-fade-in">
      <EvidenceSection title="📋 유사 비용추계서 사례"
        items={refs.similar_bills_cost_estimate || []}
        openModal={openModal} kind="bill" />
      <EvidenceSection title="📄 유사 미첨부 사유서"
        items={refs.similar_bills_non_attachment || []}
        openModal={openModal} kind="bill" />
      <EvidenceSection title="⚖️ 비용추계와 이해 (법령 PDF) 인용"
        items={refs.legal_references || []}
        openModal={openModal} kind="legal" />
    </div>
  )
}

function EvidenceSection({ title, items, openModal, kind }) {
  if (!items.length) return null
  return (
    <div className="evidence-section">
      <h4>{title}</h4>
      <div className="evidence-cards">
        {items.map((it, i) => (
          <div
            key={i}
            className="ref-card"
            onClick={() => openModal(kind === 'bill' ? {
              title: `${it.bill_no} ${it.bill_name || ''}`,
              meta: `유사도 ${Math.round((it.similarity || 0) * 100)}%`,
              body: it.content,
            } : {
              title: '비용추계 이해 (법령 PDF)',
              meta: `청크 ${it.chunk_id?.slice(-12) || ''} · 유사도 ${Math.round((it.similarity || 0) * 100)}%`,
              body: it.content,
            })}
          >
            <div className="ref-card-top">
              <span className="ref-card-title">
                {kind === 'bill'
                  ? `📋 ${it.bill_no} · ${(it.bill_name || '').slice(0, 35)}`
                  : `📘 법령 PDF · ${it.chunk_id?.slice(-12) || ''}`}
              </span>
              <span className="ref-card-sim">{Math.round((it.similarity || 0) * 100)}%</span>
            </div>
            <div className="ref-card-preview">{(it.content || '').slice(0, 120)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function FormView({ result, formType, setFormType }) {
  const renderKey = `${formType}:${result?.generatedAt || ''}:${result?.billName || ''}`
  const [rendered, setRendered] = useState({ key: '', html: '', err: '' })
  const html = rendered.key === renderKey ? rendered.html : ''
  const err = rendered.key === renderKey ? rendered.err : ''
  const loading = rendered.key !== renderKey

  useEffect(() => {
    let alive = true
    fetch(`${API_BASE}/api/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result, format: formType }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text())
        return r.text()
      })
      .then((text) => {
        if (alive) setRendered({ key: renderKey, html: text, err: '' })
      })
      .catch((e) => {
        if (alive) setRendered({ key: renderKey, html: '', err: e.message })
      })
    return () => { alive = false }
  }, [result, formType, renderKey])

  const handlePrint = () => {
    const w = window.open('', '_blank')
    if (!w) return
    w.document.write(html)
    w.document.close()
    setTimeout(() => w.print(), 500)
  }

  const handleDownloadHtml = () => {
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `비용추계서_${formType === 'gyeonggi' ? '경기도' : '국회'}_${Date.now()}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="form-view animate-fade-in">
      <div className="form-toolbar">
        <div className="form-pickr">
          <button
            className={`pickr-btn ${formType === 'gyeonggi' ? 'active' : ''}`}
            onClick={() => setFormType('gyeonggi')}
          >
            🟦 경기도 별지 제1호
          </button>
          <button
            className={`pickr-btn ${formType === 'assembly' ? 'active' : ''}`}
            onClick={() => setFormType('assembly')}
          >
            🟥 국회 별지 제2호
          </button>
        </div>
        <div className="form-actions">
          <button className="form-btn" onClick={handlePrint}>🖨️ 인쇄 / PDF</button>
          <button className="form-btn" onClick={handleDownloadHtml}>📥 HTML 다운로드</button>
        </div>
      </div>

      <div className="form-preview-wrap">
        {loading && <div className="empty">양식 렌더링 중...</div>}
        {err && <div className="status-banner error">{err}</div>}
        {!loading && !err && html && (
          <iframe
            className="form-preview-frame"
            srcDoc={html}
            title="비용추계서 미리보기"
          />
        )}
      </div>
    </div>
  )
}

function Modal({ data, onClose }) {
  useEffect(() => {
    const onEsc = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{data.title}</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        {data.meta && <div className="modal-meta">{data.meta}</div>}
        <div className="modal-body">{data.body}</div>
      </div>
    </div>
  )
}

export default App
