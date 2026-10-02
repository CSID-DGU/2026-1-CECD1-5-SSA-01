import { useCallback, useEffect, useRef, useState } from 'react'
import ErceChat from './ErceChat'
import './App.css'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

const VERDICT_META = {
  '추계서':    { label: '비용추계서 작성 대상', color: 'red', desc: '재정지출 또는 수입 변화가 예상되어 비용추계서를 작성합니다.' },
  '미첨부_1호': { label: '미첨부 1호', color: 'green', desc: '예상 비용이 첨부 기준보다 적어 미첨부 사유서를 작성합니다.' },
  '미첨부_2호': { label: '미첨부 2호', color: 'gray', desc: '국가안전보장 또는 군사기밀 사유로 추계서를 첨부하지 않습니다.' },
  '미첨부_3호': { label: '미첨부 3호', color: 'amber', desc: '시행계획 등이 확정되지 않아 기술적으로 추계하기 곤란합니다.' },
  '미대상':    { label: '비용추계 미대상', color: 'blue', desc: '새로운 재정지출 또는 수입 변화가 확인되지 않았습니다.' },
  // 기존 분류와의 하위 호환 (legacy)
  '추계필요': { label: '추계 필요', color: 'red', desc: '비용 발생' },
  '미첨부_A': { label: '비용 없음', color: 'green', desc: '비용 미수반' },
  '미첨부_B': { label: '추계 곤란', color: 'amber', desc: '기술적 곤란' },
  '미첨부_C': { label: '기존 예산 활용', color: 'blue', desc: '기존 예산 범위' },
}

const CALC_STATUS_TEXT = {
  computed_by_python: '확정된 기준값으로 계산했습니다.',
  computed_by_special_template: '국회 비용추계 기준과 확정된 전제값으로 산출했습니다.',
  computed_with_tag_structure: '공식 비용추계서 사례를 기준으로 산출했습니다.',
  computed_with_tag_estimates: '유사 비용추계서의 동일 산식 금액을 적용해 초안을 생성했습니다.',
  computed_with_evidence: '공식 비용추계 사례의 산식과 전제값 후보를 활용해 초안을 생성했습니다.',
  computed_partial_by_python: '계산 가능한 항목을 우선 산출하고 일부 항목은 검토 대상으로 남겼습니다.',
  estimated_by_tag: '유사 비용추계서 기반 초안입니다.',
  needs_external_data: '대상 규모·단가·실적 자료가 있으면 더 정밀하게 보정할 수 있습니다.',
  needs_policy_input: '사업 규모나 운영방식 전제를 보정하면 더 정밀하게 재계산할 수 있습니다.',
  blocked_missing_variables: '필수 기준값 입력이 필요합니다.',
  blocked_no_structured_formula: '산식을 구성할 근거가 부족합니다.',
  awaiting_user_input: '근거 없는 금액을 생성하지 않았습니다. 표시된 필수 값을 입력하면 재계산합니다.',
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

function cleanExtractedText(value) {
  return String(value || '')
    .replace(/\r/g, '')
    .replace(/([가-힣])\s*\n\s*([가-힣])/g, '$1$2')
    .replace(/[ \t]*\n[ \t]*/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

function comparableInputValue(candidate, request) {
  const value = Number(candidate?.value)
  if (!Number.isFinite(value)) return null
  const sourceUnit = String(candidate?.unit || '').replace(/\s+/g, '')
  const targetUnit = String(request?.unit || '').replace(/\s+/g, '')
  if (!sourceUnit || !targetUnit) return null
  if (sourceUnit === targetUnit) return value
  const moneyFactors = { 원: 1, 천원: 1000, 만원: 10000, 백만원: 1000000 }
  const source = sourceUnit.match(/^(백만원|만원|천원|원)(.*)$/)
  const target = targetUnit.match(/^(백만원|만원|천원|원)(.*)$/)
  if (!source || !target || source[2] !== target[2]) return null
  return value * moneyFactors[source[1]] / moneyFactors[target[1]]
}

function evidenceModal(item, kind = 'bill') {
  const similarity = Math.round((item.similarity || 0) * 100)
  if (kind === 'legal') {
    return {
      title: '비용추계 기준 근거',
      sourceLabel: '법령 및 작성 기준',
      meta: `관련도 ${similarity}% · 근거 ID ${item.chunk_id?.slice(-12) || '-'}`,
      body: cleanExtractedText(item.content),
    }
  }
  return {
    title: item.bill_name || '유사 비용추계 사례',
    sourceLabel: `국회 의안 ${item.bill_no || '-'}`,
    meta: `관련도 ${similarity}%`,
    body: cleanExtractedText(item.content),
  }
}

function App() {
  const [file, setFile] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentStep, setCurrentStep] = useState(-1)
  const [processingProgress, setProcessingProgress] = useState(0)
  const [result, setResult] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [modal, setModal] = useState(null)
  const [error, setError] = useState('')
  const formType = 'assembly'
  const fileRef = useRef(null)

  useEffect(() => {
    if (!import.meta.env.DEV || new URLSearchParams(window.location.search).get('demo') !== '2200555') return
    const controller = new AbortController()
    fetch('/erce_demo_2200555.json', { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('예시를 불러오지 못했어요.'); return response.json() })
      .then(data => { if (!controller.signal.aborted) setResult(data) })
      .catch(error => { if (!controller.signal.aborted) setError(error.message) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!isProcessing) return
    const t = setInterval(() => setProcessingProgress(value => Math.min(90, value + (90 - value) * 0.07)), 900)
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
    setIsProcessing(true); setResult(null); setError(''); setCurrentStep(0); setProcessingProgress(6)
    try {
      const content = await fileToDataUrl(file)
      setCurrentStep(1)
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
      setProcessingProgress(100)
      setResult(data)
    } catch (e) {
      setCurrentStep(-1)
      setProcessingProgress(0)
      setError(e.message)
    } finally {
      setIsProcessing(false)
    }
  }

  const reset = () => {
    setFile(null); setResult(null); setError(''); setCurrentStep(-1)
    setProcessingProgress(0)
    setExpanded(null); setModal(null)
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-logo">
          <div className="header-logo-icon">CE</div>
          <div>
            <h1>비용추계 자동화 시스템</h1>
            <span>의안 분석 및 비용추계서 작성</span>
          </div>
        </div>
        <div className="header-right">
          <span className="form-toggle-label">국회 의안 · ERCE</span>
        </div>
      </header>

      <main className="main">
        {!result && !isProcessing && (
          <>
            <section className="hero">
              <h2>
                의안 PDF에서 ERCE 산식 검토까지
              </h2>
              <p>
                비용유발 조문을 확인하고, ERCE 산식에 필요한 값과 근거를 검토합니다.
              </p>
            </section>

            <section className="upload-section">
              <div
                className={`upload-zone ${isDragging ? 'dragging' : ''}`}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={event => { if (isProcessing) { event.preventDefault(); return } handleDrop(event) }}
                onClick={() => { if (!isProcessing) fileRef.current?.click() }}
              >
                <input ref={fileRef} type="file" accept=".pdf" disabled={isProcessing}
                  onChange={(e) => { setFile(e.target.files[0]); setError('') }}
                  style={{ display: 'none' }} />
                <div className="upload-icon">PDF</div>
                <h3>의안 PDF를 올려주세요</h3>
                <p>파일을 끌어오거나 눌러서 선택해 주세요. 텍스트가 포함된 PDF를 지원합니다.</p>
                <div className="upload-formats"><span>PDF</span></div>
              </div>

              {file && (
                <div className="file-selected animate-fade-in">
                  <span className="file-selected-icon">PDF</span>
                  <div className="file-selected-info">
                    <div className="name">{file.name}</div>
                    <div className="size">{(file.size / 1024).toFixed(1)} KB</div>
                  </div>
                  <button className="file-selected-remove"
                    disabled={isProcessing}
                    onClick={(e) => { e.stopPropagation(); reset() }}>✕</button>
                </div>
              )}

              {error && <div className="status-banner error">{error}</div>}

              <button className="start-btn" disabled={!file || isProcessing} onClick={start}>
                {isProcessing ? <><span className="spinner" /> 분석하고 있어요</> : '분석 시작'}
              </button>
            </section>
          </>
        )}

        {isProcessing && !result && (
          <section className="analysis-progress-card animate-fade-in" role="status" aria-live="polite">
            <div className="analysis-document" aria-hidden="true"><span>PDF</span><i /><i /><i /><div className="analysis-scan" /></div>
            <span className="analysis-progress-tag">GPT-6.1 Sol · Medium</span>
            <h3>{currentStep === 0 ? '분석할 문서를 준비하고 있어요' : '법안 내용을 꼼꼼히 살펴보고 있어요'}</h3>
            <p>{processingProgress < 75 ? '비용이 발생하는 조문과 계산에 필요한 값을 확인해요.' : '분석을 기다리고 있어요. 문서에 따라 조금 더 걸릴 수 있어요.'}</p>
            <div className="analysis-gauge" role="progressbar" aria-label="분석 대기 진행 표시" aria-valuetext="분석 응답 대기 중 · 예상 진행 표시">
              <div style={{ width: `${processingProgress}%` }} />
            </div>
            <div className="analysis-progress-footer"><span>분석 중<span className="analysis-dots">…</span></span><small>예상 진행 표시 · 완료되면 자동으로 넘어가요</small></div>
          </section>
        )}

        {result && (
          <section className="result-flow animate-fade-in">
            <div className="result-hero">
              <button className="back-btn" onClick={reset}>← 새 의안 분석</button>
              <div className="result-analysis-label">분석 완료{result.erce?.billNo ? ` · 의안 ${result.erce.billNo}` : ''}</div>
              <h2 className="result-title">함께 비용추계 초안을 만들어볼게요</h2>
              {result.analysisMode === 'manual_demo' && <p>개발 예시 · 2200555 정부 적립금 항목의 확인한 값을 미리 채웠어요. 실제 PDF 자동 분석 결과는 아닙니다.</p>}
            </div>
            <ErceChat key={`${result.analysisMode}-${result.generatedAt}`} result={result} />
            <details className="chat-article-details">
              <summary>분석한 조문 자세히 보기 ({(result.articles || []).length}개)</summary>
              <ArticlesView
                articles={result.articles || []}
                expanded={expanded}
                setExpanded={setExpanded}
                openModal={setModal}
              />
            </details>
          </section>
        )}
      </main>

      {modal && <Modal data={modal} onClose={() => setModal(null)} />}
    </div>
  )
}

function GuidedMissingInputs({ estimate, drafts, setVariableDraft, recompute, isRecomputing, recomputeError }) {
  const requests = (estimate?.human_input?.requests || []).filter(request => request.blocking)
  const [openSuggestions, setOpenSuggestions] = useState({})
  const [chosenSources, setChosenSources] = useState({})
  if (!requests.length) return null
  const entered = requests.filter(request =>
    String(drafts[request.item_index]?.variables?.[request.variable] ?? '').trim() !== ''
  ).length

  return (
    <section className="guided-input" aria-label="추계에 필요한 정보">
      <div className="guided-input-header">
        <div className="guided-input-eyebrow">한 걸음만 더</div>
        <h3>기존 추계 계산에 필요한 정보를 확인해 주세요</h3>
        <p>찾을 수 있는 근거는 먼저 반영했습니다. 아래 값은 확인되지 않아 임의로 채우지 않았어요.</p>
        <div className="guided-input-progress">{entered} / {requests.length}개 입력</div>
      </div>

      <div className="guided-input-cards">
        {requests.map((request, index) => {
          const candidates = (request.suggested_values || []).filter(candidate =>
            Number.isFinite(Number(candidate?.value)) && (candidate?.bill_no || candidate?.source_text)
          )
          const draft = drafts[request.item_index]?.variables?.[request.variable] ?? ''
          const showCandidates = Boolean(openSuggestions[request.id])
          const chosen = chosenSources[request.id]
          return (
            <div className="guided-input-card" key={request.id}>
              <div className="guided-input-card-top">
                <span className="guided-input-index">{index + 1}</span>
                <span className="guided-input-item">{request.item || '비용 항목'}</span>
                {draft !== '' && <span className="guided-input-done">입력됨</span>}
              </div>
              <h4>{request.prompt}</h4>
              <p className="guided-input-explain">
                {request.basis || '의안과 현재 연결된 자료만으로는 이 값을 확인할 수 없어요.'}
              </p>
              <div className="guided-input-control">
                <label htmlFor={`guided-${request.id}`}>
                  {request.variable}{request.unit ? ` · ${request.unit}` : ''}
                </label>
                <input
                  id={`guided-${request.id}`}
                  type="number"
                  inputMode="decimal"
                  min="0"
                  placeholder="값을 입력해 주세요"
                  value={draft}
                  onChange={event => {
                    setVariableDraft(request.item_index, request.variable, event.target.value)
                    setChosenSources(prev => ({ ...prev, [request.id]: null }))
                  }}
                />
              </div>
              <button
                className="guided-suggestion-toggle"
                type="button"
                aria-expanded={showCandidates}
                onClick={() => setOpenSuggestions(prev => ({ ...prev, [request.id]: !prev[request.id] }))}
              >
                {showCandidates ? '추천값 접기' : '유사 사례 값 제시받기'} <span aria-hidden="true">→</span>
              </button>
              {showCandidates && (
                <div className="guided-suggestions">
                  {candidates.length ? (
                    <>
                      <p>유사 사례의 참고값이에요. 현재 의안에 맞는지 확인한 뒤 선택해 주세요.</p>
                      {candidates.map((candidate, candidateIndex) => {
                        const value = comparableInputValue(candidate, request)
                        return (
                          <div className="guided-suggestion" key={`${request.id}-${candidate.bill_no || 'source'}-${candidateIndex}`}>
                            <div className="guided-suggestion-head">
                              <strong>{Number(candidate.value).toLocaleString()}{candidate.unit || ''}</strong>
                              <span>{candidate.bill_name || `의안 ${candidate.bill_no || '-'}`}</span>
                            </div>
                            <div className="guided-suggestion-source">
                              {candidate.bill_no && <span>의안 {candidate.bill_no}</span>}
                              {candidate.year && <span>{candidate.year}년 기준</span>}
                            </div>
                            {candidate.source_text && (
                              <p className="guided-suggestion-evidence">{cleanExtractedText(candidate.source_text)}</p>
                            )}
                            {value !== null ? (
                              <button type="button" className="guided-suggestion-use" onClick={() => {
                                setVariableDraft(request.item_index, request.variable, String(value))
                                setChosenSources(prev => ({ ...prev, [request.id]: candidate.bill_no ? `의안 ${candidate.bill_no}` : '근거 문서' }))
                              }}>
                                이 값 입력하기
                              </button>
                            ) : (
                              <span className="guided-suggestion-unit-note">단위가 달라 직접 확인이 필요해요</span>
                            )}
                          </div>
                        )
                      })}
                    </>
                  ) : (
                    <p>지금은 이 값에 맞는 유사 사례를 찾지 못했어요. 자료가 없다면 미확정으로 남겨둘 수 있습니다.</p>
                  )}
                </div>
              )}
              {chosen && <p className="guided-selected-note">{chosen}의 값을 참고해 입력했어요. 재계산 전 다시 확인해 주세요.</p>}
            </div>
          )
        })}
      </div>
      <div className="guided-input-footer">
        <div>
          <strong>{entered === requests.length ? '필요한 값을 모두 입력했어요.' : '모르는 값은 비워두셔도 됩니다.'}</strong>
          <span>입력하지 않은 항목은 금액을 확정하지 않고 남겨둡니다.</span>
        </div>
        <button type="button" className="guided-recompute-btn" disabled={!entered || isRecomputing} onClick={recompute}>
          {isRecomputing ? '계산 중...' : '입력한 값으로 다시 계산'}
        </button>
      </div>
      {recomputeError && <div className="recompute-error" role="alert">{recomputeError}</div>}
    </section>
  )
}

function VariableEditorPanel({
  estimate,
  drafts,
  setDraft,
  setVariableDraft,
  recompute,
  isRecomputing,
  recomputeError,
}) {
  const items = estimate?.items || []
  const allRequests = estimate?.human_input?.requests || []
  const blockingRequests = allRequests.filter(request => request.blocking)
  const requests = blockingRequests.length > 0 ? blockingRequests : allRequests
  const needsRequiredInput = blockingRequests.length > 0
  if (!items.length) return null
  return (
    <div className="variable-editor-panel">
      <div className="variable-editor-head">
        <div>
          <div className="variable-editor-title">
            {needsRequiredInput ? '필수 값 입력 후 재계산' : '계산에 쓴 가정값 확인'}
          </div>
          <div className="variable-editor-desc">
            {needsRequiredInput
              ? '아래 값만 입력하면 기존 산식으로 바로 다시 계산합니다.'
              : '자동 산출된 전제값을 확인하거나 필요한 경우 보정하세요.'}
          </div>
        </div>
        <button
          type="button"
          className="recompute-all-btn"
          disabled={isRecomputing}
          onClick={recompute}
        >
          {isRecomputing ? '재계산 중' : '입력값으로 바로 재계산'}
        </button>
      </div>
      {requests.length > 0 && (
        <div className="human-input-list">
          <div className="human-input-summary">
            <strong>{needsRequiredInput ? `${blockingRequests.length}개 값 입력 필요` : '선택 확인'}</strong>
            <span>{needsRequiredInput ? '근거 없는 금액은 자동으로 채우지 않습니다.' : '현재 값을 바꾸고 싶을 때만 입력하세요.'}</span>
          </div>
          {requests.map((request) => (
            <div key={request.id} className={`human-input-row ${request.blocking ? 'blocking' : ''}`}>
              <div className="human-input-copy">
                <div className="human-input-item">{request.item}</div>
                <div className="human-input-prompt">{request.prompt}</div>
                {request.basis && <div className="human-input-basis">{request.basis}</div>}
                {request.suggested_values?.length > 0 && (
                  <div className="human-input-suggestions">
                    참고 후보 {request.suggested_values.map((candidate, index) => (
                      <span key={`${request.id}-${index}`}>
                        {Number(candidate.value).toLocaleString()}{candidate.unit || ''}
                        {candidate.bill_no ? ` · ${candidate.bill_no}` : ''}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <label>
                <span>{request.variable}{request.unit ? ` (${request.unit})` : ''}</span>
                <input
                  type="number"
                  inputMode="decimal"
                  placeholder={request.current_value != null ? String(request.current_value) : '값 입력'}
                  value={drafts[request.item_index]?.variables?.[request.variable] ?? ''}
                  onChange={(e) => setVariableDraft(request.item_index, request.variable, e.target.value)}
                />
              </label>
            </div>
          ))}
        </div>
      )}
      <div className="variable-editor-table">
        {requests.length === 0 && items.map((item, i) => {
          const calc = item.calculation || {}
          const variables = item.assumption_strategy?.length
            ? item.assumption_strategy.map(row => row.variable)
            : asList(item.variables_needed)
          return (
            <div key={i} className="variable-editor-row">
              <div className="variable-editor-item">
                <div className="variable-editor-name">{item.name}</div>
                <div className="variable-editor-formula">{item.selected_formula?.formula || item.formula || '-'}</div>
                <div className="variable-editor-vars">
                  {variables.slice(0, 5).map((v, j) => (
                    <span key={j} className="var-chip">{String(v)}</span>
                  ))}
                </div>
              </div>
              <label>
                <span>연간 기준금액</span>
                <input
                  type="number"
                  inputMode="decimal"
                  placeholder={calc.base_amount_thousand != null ? String(calc.base_amount_thousand) : '천원'}
                  value={drafts[i]?.base_amount_thousand || ''}
                  onChange={(e) => setDraft(i, 'base_amount_thousand', e.target.value)}
                />
              </label>
              <label>
                <span>단가</span>
                <input
                  type="number"
                  inputMode="decimal"
                  placeholder="천원"
                  value={drafts[i]?.unit_cost || ''}
                  onChange={(e) => setDraft(i, 'unit_cost', e.target.value)}
                />
              </label>
              <label>
                <span>대상 수</span>
                <input
                  type="number"
                  inputMode="decimal"
                  placeholder="명/개소"
                  value={drafts[i]?.target || ''}
                  onChange={(e) => setDraft(i, 'target', e.target.value)}
                />
              </label>
              <label>
                <span>반복</span>
                <select
                  value={drafts[i]?.recurrence || calc.recurrence || 'annual'}
                  onChange={(e) => setDraft(i, 'recurrence', e.target.value)}
                >
                  <option value="annual">매년</option>
                  <option value="one_time">1회성</option>
                  <option value="periodic">주기적</option>
                </select>
              </label>
            </div>
          )
        })}
      </div>
      {recomputeError && <div className="recompute-error">{recomputeError}</div>}
    </div>
  )
}

// Legacy views are retained in source but disconnected from the ERCE web flow.
// eslint-disable-next-line no-unused-vars
function VerdictCard({ verdict, field }) {
  const meta = VERDICT_META[verdict.type] || {
    label: verdict.label, color: 'gray', desc: ''
  }
  return (
    <div className={`verdict-card verdict-${meta.color}`}>
      <div className="verdict-status">
        <span className="verdict-status-dot" />
        분석 결과
      </div>
      <div className="verdict-body">
        <div className="verdict-label">{meta.label}</div>
        <div className="verdict-desc">{meta.desc}</div>
        {field && field.field && (
          <div className="verdict-field">분야 <b>{field.field}</b></div>
        )}
        <div className="verdict-summary">{verdict.summary}</div>
        {verdict.basis?.reasons?.length > 0 ? (
          <div className="verdict-basis">
            <div className="verdict-basis-title">{verdict.basis.title || '판단 근거'}</div>
            {verdict.basis.reasons.map((row, idx) => (
              <div key={idx} className="verdict-basis-row">
                <span>{row.label}</span>
                <p>{row.text}</p>
              </div>
            ))}
          </div>
        ) : verdict.nabo_reason && (
          <div className="verdict-nabo">
            <span className="verdict-nabo-label">판단 근거</span>
            <div className="verdict-nabo-text">{verdict.nabo_reason}</div>
          </div>
        )}
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
  const articleReason = art.reason || art.route_reason || art.change_summary || '추가 검토가 필요합니다.'
  const triggerLabel = art.trigger_type || (art.route_key ? 'ERCE 산식 후보' : '산식 선택 필요')
  return (
    <div
      className={`article-row ${art.cost_trigger ? 'triggered' : 'safe'} ${isExpanded ? 'expanded' : ''}`}
      onClick={onToggle}
    >
      <div className="article-row-main">
        <div className="article-row-no">
          <span className={`article-status-dot ${art.cost_trigger ? 'cost' : 'none'}`} />
          {art.no}
        </div>
        <div className="article-row-meta">
          {art.cost_trigger ? (
            <>
              <span className={`badge badge-${tColor}`}>{triggerLabel}</span>
              <span className="strength-text">
                {STRENGTH_LABEL[art.obligation_strength] || art.obligation_strength || (art.quote_verified ? '원문 확인' : '원문 확인 필요')}
              </span>
            </>
          ) : (
            <span className="badge badge-gray">비용 없음</span>
          )}
        </div>
        {!isExpanded && (
          <div className="article-row-reason">{articleReason}</div>
        )}
        <div className="article-row-chevron">›</div>
      </div>

      {isExpanded && (
        <div className="article-detail">
          <div className="detail-block">
            <div className="detail-label">판단 근거</div>
            <div className="article-text-box">{cleanExtractedText(articleReason)}</div>
          </div>

          <div className="detail-block">
            <div className="detail-label">관련 조문</div>
            <div className="article-text-box article-source-text">
              {cleanExtractedText(art.text)}{art.source_page ? ` (PDF ${art.source_page}쪽)` : ''}
            </div>
          </div>

          {art.legal_refs && art.legal_refs.length > 0 && (
            <div className="detail-block">
              <div className="detail-label">비용추계 기준 근거</div>
              <div className="ref-list">
                {art.legal_refs.map((r, i) => (
                  <div
                    key={i}
                    className="ref-card"
                    onClick={(e) => {
                      e.stopPropagation()
                      openModal(evidenceModal(r, 'legal'))
                    }}
                  >
                    <div className="ref-card-top">
                      <span className="ref-card-title">법령 및 작성 기준</span>
                      <span className="ref-card-sim">관련도 {Math.round((r.similarity || 0) * 100)}%</span>
                    </div>
                    <div className="ref-card-preview">{cleanExtractedText(r.content).slice(0, 150)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {art.similar_refs && art.similar_refs.length > 0 && (
            <div className="detail-block">
              <div className="detail-label">유사 비용추계 사례</div>
              <div className="ref-list">
                {art.similar_refs.map((r, i) => (
                  <div
                    key={i}
                    className="ref-card"
                    onClick={(e) => {
                      e.stopPropagation()
                      openModal(evidenceModal(r, 'bill'))
                    }}
                  >
                    <div className="ref-card-top">
                      <span className="ref-card-title">{r.bill_no} · {r.bill_name?.slice(0, 36) || ''}</span>
                      <span className="ref-card-sim">관련도 {Math.round((r.similarity || 0) * 100)}%</span>
                    </div>
                    <div className="ref-card-preview">{cleanExtractedText(r.content).slice(0, 150)}</div>
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
                  onClick={() => openModal(evidenceModal(it, 'bill'))}
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

function ErceConnection({ erce, result, file, onResult }) {
  const staffingLabels = {
    planned_staff_total: '계획 정원',
    existing_staff_total: '기존 인원',
    incoming_staff_total: '전입·재배치 인원',
    parent_staff_total: '모기관 정원',
    target_population: '대상 관할인구',
    parent_population: '모기관 관할인구',
    population_per_staff: '공무원 1인당 관할인구',
    planned_staff_by_grade: '직급별 계획 인원',
    existing_staff_by_grade: '직급별 기존 인원',
    incoming_staff_by_grade: '직급별 전입 인원',
  }
  const [drafts, setDrafts] = useState(() => Object.fromEntries(
    (erce.items || []).map(item => [item.itemIndex, Object.fromEntries(
      Object.entries(item.explicitInputs || {}).map(([key, row]) => [key, {
        value: typeof row.value === 'number' ? String(row.value) : JSON.stringify(row.value),
        unit: row.unit,
        source_ref: row.source_ref,
      }])
    )])
  ))
  const [results, setResults] = useState(() => Object.fromEntries(
    (erce.items || []).filter(item => item.calculation).map(item => [item.itemIndex, item.calculation])
  ))
  const [errors, setErrors] = useState({})
  const [staffingDrafts, setStaffingDrafts] = useState({})
  const [running, setRunning] = useState(null)
  const [manualRoutes, setManualRoutes] = useState({})
  const [aiDraftText, setAiDraftText] = useState('')
  const [aiDraftError, setAiDraftError] = useState('')
  const routeOptions = erce.routeOptions || []
  const manualItems = (erce.unmappedArticles || []).flatMap(article => {
    const option = routeOptions.find(row => row.routeKey === manualRoutes[article.itemIndex])
    return option ? [{
      ...option,
      itemIndex: article.itemIndex,
      name: article.name,
      scopeNote: '사용자가 선택한 산식입니다. 해당 조문에 적용 가능한지 확인해 주세요.',
    }] : []
  })
  const routedItems = [...(erce.items || []), ...manualItems]

  const updateField = (itemIndex, variable, field, value) => {
    setDrafts(previous => ({
      ...previous,
      [itemIndex]: {
        ...(previous[itemIndex] || {}),
        [variable]: {
          ...(previous[itemIndex]?.[variable] || {}),
          [field]: value,
        },
      },
    }))
  }

  const updateStaffingField = (itemIndex, variable, field, value) => {
    setStaffingDrafts(previous => ({
      ...previous,
      [itemIndex]: {
        ...(previous[itemIndex] || {}),
        [variable]: { ...(previous[itemIndex]?.[variable] || {}), [field]: value },
      },
    }))
  }

  const applyStaffingCandidate = (item, scenario) => {
    const isGrade = item.routeKey === 'personnel_grade'
    if (isGrade ? !scenario.netStaffByGrade : scenario.netStaff == null) return
    const key = isGrade ? 'headcount_by_grade' : 'headcount'
    setDrafts(previous => ({
      ...previous,
      [item.itemIndex]: {
        ...(previous[item.itemIndex] || {}),
        [key]: {
          value: isGrade ? JSON.stringify(scenario.netStaffByGrade) : String(scenario.netStaff),
          unit: isGrade ? 'person/grade' : 'person',
          source_ref: `순증 인원 산정(${scenario.formula}): ${scenario.sourceRefs.join('; ')}`,
        },
      },
    }))
  }

  const calculate = async item => {
    const itemDraft = drafts[item.itemIndex] || {}
    const explicitInputs = {}
    const staffingInputs = { ...(item.staffingInputs || {}) }
    try {
      for (const variable of item.requiredVariables) {
        const row = itemDraft[variable] || {}
        if (!String(row.value || '').trim()) continue
        const raw = String(row.value).trim()
        const value = raw.startsWith('{') || raw.startsWith('[')
          ? JSON.parse(raw)
          : Number(raw.replace(/,/g, ''))
        if (typeof value === 'number' && !Number.isFinite(value)) {
          throw new Error(`${variable}: 숫자 또는 JSON 형식으로 입력해 주세요.`)
        }
        explicitInputs[variable] = {
          value,
          unit: String(row.unit || '').trim(),
          source_ref: String(row.source_ref || '').trim(),
        }
      }
      for (const [key, row] of Object.entries(staffingDrafts[item.itemIndex] || {})) {
        if (!String(row.value || '').trim()) continue
        const value = key.endsWith('_by_grade')
          ? JSON.parse(String(row.value))
          : Number(String(row.value).replace(/,/g, ''))
        if (!String(row.source_ref || '').trim()
          || (key.endsWith('_by_grade') ? !value || Array.isArray(value) || typeof value !== 'object'
            : !Number.isFinite(value) || value < 0)) {
          throw new Error(`${staffingLabels[key] || key}: 유효한 값과 근거가 필요합니다.`)
        }
        staffingInputs[key] = {
          value, unit: key.endsWith('_by_grade') ? 'person/grade'
            : key === 'population_per_staff' ? 'person/staff' : 'person',
          source_ref: String(row.source_ref).trim(), source_kind: 'user_confirmed',
        }
      }
    } catch (error) {
      setErrors(previous => ({ ...previous, [item.itemIndex]: error.message }))
      return
    }
    setRunning(item.itemIndex)
    setErrors(previous => ({ ...previous, [item.itemIndex]: '' }))
    try {
      const response = await fetch(`${API_BASE}/api/erce/estimate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          route_key: item.routeKey,
          bill_no: erce.billNo,
          years: 5,
          explicit_inputs: explicitInputs,
          cutoff_date: item.proposeDate || '',
          staffing_context: item.staffingContext || {},
          staffing_inputs: staffingInputs,
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || 'ERCE 계산에 실패했습니다.')
      setResults(previous => ({ ...previous, [item.itemIndex]: data }))
    } catch (error) {
      setErrors(previous => ({ ...previous, [item.itemIndex]: error.message }))
    } finally {
      setRunning(null)
    }
  }

  const submitAiDraft = async () => {
    setAiDraftError('')
    try {
      if (!file) throw new Error('PDF 파일을 다시 선택해 주세요.')
      const aiDraft = JSON.parse(aiDraftText)
      const content = await fileToDataUrl(file)
      const response = await fetch(`${API_BASE}/api/analyze_v2`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, content, aiDraft }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || 'AI 분석 결과 검증에 실패했습니다.')
      onResult(data)
    } catch (error) {
      setAiDraftError(error.message)
    }
  }

  return (
    <section className="erce-connection">
      <h4>ERCE 엔진</h4>
      {result?.analysisMode === 'manual_required' && (
        <div className="erce-connection-item">
          <strong>개발용 AI 분석 결과 입력</strong>
          <p>현재는 API 크레딧을 사용하지 않습니다. 이 의안의 조문·산식·명시 변수를 AI와 검토한 JSON을 붙여넣어 주세요.</p>
          <textarea
            aria-label="AI 분석 JSON"
            value={aiDraftText}
            onChange={event => setAiDraftText(event.target.value)}
            placeholder="AI 분석 JSON"
            rows={10}
          />
          <button type="button" onClick={submitAiDraft}>ERCE에 반영</button>
          {aiDraftError && <p className="erce-error">{aiDraftError}</p>}
        </div>
      )}
      <p>의안에서 확인된 변수와 근거만 계산에 사용합니다. 부족한 값은 입력이 필요하며, 금액은 원 단위로 입력해 주세요.</p>
      <p>아래 필수 변수는 ERCE 산식 기준이며, 계산 요청 시 ERCE가 부족한 값을 다시 확인합니다.</p>
      {(erce.reviewCandidates || []).length > 0 && (
        <div className="erce-connection-item">
          <strong>추가 비용 검토 후보</strong>
          {erce.reviewCandidates.map(candidate => (
            <p key={`${candidate.routeKey}-${candidate.triggerRef}`}>
              {candidate.routeKey === 'personnel_asset' ? '신규 자산취득비' : candidate.routeKey}: {candidate.reason}
              <small>근거 조문: {candidate.triggerRef} · 확인할 값: {candidate.missingVariables.join(', ')}</small>
            </p>
          ))}
        </div>
      )}
      {(erce.unmappedArticles || []).length > 0 && (
        <div className="erce-connection-item">
          <strong>산식 선택이 필요한 조문</strong>
          <p>자동으로 확정하기 어려워 기존 추계 로직으로 넘기지 않았습니다. 해당하는 ERCE 산식을 직접 선택할 수 있습니다.</p>
          {erce.unmappedArticles.map(article => (
            <div className="erce-manual-route" key={article.itemIndex}>
              <label htmlFor={`erce-route-${article.itemIndex}`}>{article.name}</label>
              <span>{article.text}</span>
              {article.reason && <small>{article.reason}</small>}
              <select
                id={`erce-route-${article.itemIndex}`}
                value={manualRoutes[article.itemIndex] || ''}
                onChange={event => {
                  setManualRoutes(previous => ({ ...previous, [article.itemIndex]: event.target.value }))
                  setDrafts(previous => ({ ...previous, [article.itemIndex]: {} }))
                  setResults(previous => ({ ...previous, [article.itemIndex]: null }))
                  setErrors(previous => ({ ...previous, [article.itemIndex]: '' }))
                }}
              >
                <option value="">산식 선택</option>
                {routeOptions.map(option => (
                  <option value={option.routeKey} key={option.routeKey}>{option.label}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}
      {routedItems.length === 0 && <p>연결된 산식이 없습니다. 비용유발 조문과 산식 선택을 확인해 주세요.</p>}
      {routedItems.map(item => {
        const output = results[item.itemIndex]
        return (
          <div className="erce-connection-item" key={item.itemIndex}>
            <strong>{item.name}</strong>
            <p>{item.formula}</p>
            <small>{item.scopeNote}</small>
            {(item.observedVariables || []).length > 0 && (
              <div className="erce-observed">
                <strong>의안에서 확인한 값</strong>
                {item.observedVariables.map((row, index) => (
                  <p key={`${row.key}-${index}`}>
                    {row.key}: {String(row.value)} {row.unit} · {row.source_ref}
                  </p>
                ))}
              </div>
            )}
            {item.requiredVariables.map(variable => (
              <div className="erce-variable-row" key={variable}>
                <label>{variable}</label>
                <input
                  aria-label={`${variable} 값`}
                  placeholder="값 (숫자 또는 JSON)"
                  value={drafts[item.itemIndex]?.[variable]?.value || ''}
                  onChange={event => updateField(item.itemIndex, variable, 'value', event.target.value)}
                />
                <input
                  aria-label={`${variable} 단위`}
                  placeholder="단위"
                  value={drafts[item.itemIndex]?.[variable]?.unit || ''}
                  onChange={event => updateField(item.itemIndex, variable, 'unit', event.target.value)}
                />
                <input
                  aria-label={`${variable} 근거`}
                  placeholder="근거 문서·조문"
                  value={drafts[item.itemIndex]?.[variable]?.source_ref || ''}
                  onChange={event => updateField(item.itemIndex, variable, 'source_ref', event.target.value)}
                />
              </div>
            ))}
            <button type="button" onClick={() => calculate(item)} disabled={running === item.itemIndex}>
              {running === item.itemIndex ? '계산 중…' : 'ERCE로 계산'}
            </button>
            {errors[item.itemIndex] && <p className="erce-error">{errors[item.itemIndex]}</p>}
            {output?.status === 'needs_input' && (
              <p>추가 입력 필요: {output.missingVariables.join(', ')}</p>
            )}
            {(output?.staffingScenarios || []).length > 0 && (
              <div className="erce-observed">
                <strong>순증 인원 산정 방법 후보</strong>
                {output.staffingScenarios.map(scenario => (
                  <p key={scenario.methodKey}>
                    {scenario.label} ({scenario.candidateRole}): {scenario.formula}
                    {scenario.grossStaff != null && ` · 예상 정원 ${scenario.approximateInputs.length ? '약 ' : ''}${scenario.grossStaff}명`}
                    {scenario.netStaff != null && ` · 순증 ${scenario.netStaff}명`}
                    {scenario.netStaffByGrade && ` · 직급별 ${JSON.stringify(scenario.netStaffByGrade)}`}
                    {scenario.missingInputs.length > 0 && ` · 확인 필요: ${scenario.missingInputs.map(key => staffingLabels[key] || key).join(', ')}`}
                    {scenario.warning && ` · ${scenario.warning}`}
                    <small>적용 가정: {scenario.assumption}. {scenario.nextStep}. 근거: {scenario.sourceRefs.join('; ') || '입력 대기'}</small>
                    {((scenario.status === 'ready_for_salary_calculation' && item.routeKey === 'personnel_grade')
                      || (scenario.status === 'ready_for_grade_breakdown' && item.routeKey === 'personnel_average')) && (
                      <button type="button" onClick={() => applyStaffingCandidate(item, scenario)}>
                        이 순증 인원 사용
                      </button>
                    )}
                  </p>
                ))}
                {[...new Set(output.staffingScenarios.flatMap(scenario => scenario.missingInputs))].map(key => (
                  <div className="erce-variable-row" key={key}>
                    <label>{staffingLabels[key] || key}</label>
                    <input
                      aria-label={`${staffingLabels[key] || key} 값`}
                      placeholder={key.endsWith('_by_grade') ? '{"5급": 1, "6급": 2}' : '인원 또는 인구'}
                      value={staffingDrafts[item.itemIndex]?.[key]?.value || ''}
                      onChange={event => updateStaffingField(item.itemIndex, key, 'value', event.target.value)}
                    />
                    <input
                      aria-label={`${staffingLabels[key] || key} 근거`}
                      placeholder="근거 문서·쪽수"
                      value={staffingDrafts[item.itemIndex]?.[key]?.source_ref || ''}
                      onChange={event => updateStaffingField(item.itemIndex, key, 'source_ref', event.target.value)}
                    />
                  </div>
                ))}
              </div>
            )}
            {output?.status === 'needs_review' && (
              <p className="erce-error">계산 전 검토 필요: {output.reason}</p>
            )}
            {output?.status === 'computed_review' && (
              <p>연도별 금액(백만원): {output.annualAmountsThousand.map(value => value == null ? '—' : (value / 1000).toLocaleString()).join(' / ')}</p>
            )}
          </div>
        )
      })}
      {erce.unmappedCount > 0 && <small>{erce.unmappedCount}개 조문은 자동 연결하지 않았습니다.</small>}
    </section>
  )
}

// eslint-disable-next-line no-unused-vars
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

  const setVariableDraft = (index, variable, value) => {
    setDrafts(prev => ({
      ...prev,
      [index]: {
        ...(prev[index] || {}),
        variables: {
          ...(prev[index]?.variables || {}),
          [variable]: value,
        },
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
      const exactVariables = Object.fromEntries(
        Object.entries(draft.variables || {})
          .map(([name, value]) => [name, toNumber(value)])
          .filter(([, value]) => value !== null)
      )
      const requestedBase = exactVariables['연간 기준금액']
      const calc = item.calculation || {}
      const input = {
        item_index: index,
        recurrence: draft.recurrence || calc.recurrence || 'annual',
        start_year: toNumber(draft.start_year) || calc.start_year || 1,
        end_year: toNumber(draft.end_year) || calc.end_year || 5,
        growth_variable: draft.growth_variable ?? calc.growth_variable ?? null,
      }
      if (baseAmount !== null || requestedBase !== undefined) {
        input.base_amount_thousand = baseAmount ?? requestedBase
      } else if (Object.keys(exactVariables).length > 0) {
        input.variables = exactVariables
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
      setRecomputeError('변경한 값이 없습니다.')
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
          <h3>비용추계서 미첨부 사유서</h3>
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
  const yearRows = estimate.year_estimates || []
  const computedYearRows = yearRows.filter(row => row.amount_thousand != null)
  const hasComputedAmount = computedYearRows.length > 0
  const hasBlockingInput = Number(estimate.human_input?.blocking_count || 0) > 0
  const totalAmount = hasComputedAmount
    ? estimate.total_amount_thousand ?? computedYearRows.reduce((sum, row) => sum + Number(row.amount_thousand), 0)
    : null
  const averageAmount = hasComputedAmount
    ? estimate.average_amount_thousand ?? Math.round(totalAmount / computedYearRows.length)
    : null
  return (
    <div className="estimate-view animate-fade-in">
      <div className="section-heading">
        <div>
          <h3>비용추계서</h3>
          <p>추계 결과와 산출 근거를 한 화면에서 확인합니다.</p>
        </div>
      </div>
      {formType === 'assembly' && result?.erce && (
        <ErceConnection erce={result.erce} />
      )}
      {hasBlockingInput && (
        <GuidedMissingInputs
          estimate={estimate}
          drafts={drafts}
          setVariableDraft={setVariableDraft}
          recompute={recompute}
          isRecomputing={isRecomputing}
          recomputeError={recomputeError}
        />
      )}
      <div className="estimate-summary">
        <div className="summary-main">
          <span>{hasBlockingInput && hasComputedAmount ? '계산된 항목 부분합' : '총 추가재정소요'}</span>
          <strong>{totalAmount != null ? `${(totalAmount / 1000).toLocaleString()}백만원` : '미확정'}</strong>
        </div>
        <div className="summary-sub">
          <span>{hasBlockingInput && hasComputedAmount ? '계산된 항목 연평균' : '연평균'}</span>
          <strong>{averageAmount != null ? `${(averageAmount / 1000).toLocaleString()}백만원` : '미확정'}</strong>
        </div>
        {estimate.template_label && (
          <div className="summary-source">
            <span>적용 구조</span>
            <strong>{estimate.template_label}</strong>
          </div>
        )}
      </div>
      {yearRows.length > 0 && (
        <div className="year-grid primary">
          {yearRows.map((y, i) => (
            <div key={i} className="year-card">
              <div className="year-label">{y.year_label || `${y.year}차년도`}</div>
              <div className="year-amount">
                {y.amount_thousand !== null && y.amount_thousand !== undefined
                  ? `${(y.amount_thousand / 1000).toLocaleString()}백만원`
                  : '—'}
              </div>
            </div>
          ))}
        </div>
      )}
      {estimate.calculation_status && (
        <div className={`calc-status ${
          estimate.calculation_status.startsWith('computed')
            ? 'ok'
            : estimate.calculation_status.startsWith('estimated')
              ? 'estimated'
              : 'blocked'
        }`}>
          <span className="calc-status-label">산출 상태</span>
          <span>{CALC_STATUS_TEXT[estimate.calculation_status] || '초안을 생성했습니다.'}</span>
        </div>
      )}
      {estimate.estimation_status?.reason && (
        <div className={`calc-status ${estimate.estimation_status.blocking ? 'blocked' : 'ok'}`}>
          <span className="calc-status-label">산출 근거</span>
          <span>{estimate.estimation_status.reason}</span>
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
            {item.year_amounts_thousand?.length > 0 && (
              <div className="item-year-strip">
                {item.year_amounts_thousand.map((amount, idx) => (
                  <span key={idx}>{idx + 1}차 {(Number(amount || 0) / 1000).toLocaleString()}백만원</span>
                ))}
              </div>
            )}
            {(item.selected_formula || item.formula_template || item.reference_unit_costs || item.assumption_candidates || item.kosis_lookups || item.tag_structure_evidence) && (
              <details className="item-detail">
                <summary>산출 근거 자세히</summary>
                {item.selected_formula && (
                  <div className="selected-formula-block">
                    <div className="selected-formula-head">
                      <span>{item.selected_formula.label || '산식 선택 근거'}</span>
                      {item.selected_formula.confidence && <span>{Math.round((item.selected_formula.confidence || 0) * 100)}%</span>}
                    </div>
                    <code>{item.selected_formula.formula || item.formula || '-'}</code>
                    {item.selected_formula.basis && (
                      <div className="formula-template-note">{item.selected_formula.basis}</div>
                    )}
                  </div>
                )}
                {item.tag_structure_evidence && (
                  <div className="selected-formula-block">
                    <div className="selected-formula-head">
                      <span>적용 근거 문서</span>
                      <span>{Math.round((item.tag_structure_evidence.similarity || 0) * 100)}%</span>
                    </div>
                    <div className="formula-template-note">
                      {item.tag_structure_evidence.bill_no} {item.tag_structure_evidence.bill_name}
                    </div>
                  </div>
                )}
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
                {(item.reference_unit_costs || (item.reference_unit_cost ? [item.reference_unit_cost] : [])).length > 0 && (
                  <div className="ref-cost-block">
                <span className="ref-cost-label">
                  {formType === 'assembly' ? '추천 단가 후보' : '국회 단가 참고값'}
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
                {item.kosis_lookups && item.kosis_lookups.length > 0 && (
                  <div className="kosis-block">
                <div className="kosis-label">KOSIS 조회값</div>
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
              </details>
            )}
            {item.requires_review && (
              <div className="review-note">
                <span>{item.review_reason || '가정값 기반 초안입니다.'}</span>
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
                {item.analogy_evidence && (
                  <button
                    className="evidence-mini-btn"
                    onClick={() => openModal({
                      title: `${item.name} 유사사례 근거`,
                      meta: `${item.analogy_evidence.bill_no || ''} ${item.analogy_evidence.bill_name || ''}`,
                      body:
                        `기준 항목: ${item.analogy_evidence.item_name || '-'}\n` +
                        `근거 조문: ${item.analogy_evidence.trigger_ref || '-'}\n` +
                        `적용 방식: ${item.analogy_evidence.application || '-'}\n` +
                        `구조 유사도: ${Math.round((item.analogy_evidence.score || 0) * 100)}%`,
                    })}
                  >
                    유사사례 근거
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      {!hasBlockingInput && (
        <details className="estimate-tools">
          <summary>가정값 확인·수정</summary>
          <VariableEditorPanel
            estimate={estimate}
            drafts={drafts}
            setDraft={setDraft}
            setVariableDraft={setVariableDraft}
            recompute={recompute}
            isRecomputing={isRecomputing}
            recomputeError={recomputeError}
          />
        </details>
      )}
      {similarCE.length > 0 && (
        <details className="estimate-tools">
          <summary>유사 비용추계서</summary>
          <SimilarCasesTable items={similarCE} openModal={openModal} />
        </details>
      )}
    </div>
  )
}

// eslint-disable-next-line no-unused-vars
function EvidenceView({ result, refs, openModal }) {
  const hasReferenceItems = Boolean(
    refs?.similar_bills_cost_estimate?.length ||
    refs?.similar_bills_non_attachment?.length ||
    refs?.legal_references?.length
  )
  return (
    <div className="animate-fade-in">
      <div className="section-heading">
        <div>
          <h3>판단 근거</h3>
          <p>작성 대상 판단, 발생 비용, 참고 문서를 확인합니다.</p>
        </div>
      </div>
      <DecisionBasisSection result={result} openModal={openModal} />
      <EvidenceSection title="유사 비용추계서"
        items={refs?.similar_bills_cost_estimate || []}
        openModal={openModal} kind="bill" />
      <EvidenceSection title="유사 미첨부 사유서"
        items={refs?.similar_bills_non_attachment || []}
        openModal={openModal} kind="bill" />
      <EvidenceSection title="법령 및 작성 기준"
        items={refs?.legal_references || []}
        openModal={openModal} kind="legal" />
      {!hasReferenceItems && (
        <div className="evidence-empty">
          외부 RAG 근거가 비어 있어도 위의 작성 대상 판단근거와 공식 추계 사례 기준으로 결과를 구성했습니다.
        </div>
      )}
    </div>
  )
}

function DecisionBasisSection({ result, openModal }) {
  const verdict = result?.verdict || {}
  const basisRows = verdict.basis?.reasons || []
  const estimate = result?.estimate || {}
  const source = estimate.tag_structure_source
  if (!basisRows.length && !verdict.summary && !verdict.nabo_reason && !source) return null
  return (
    <div className="decision-basis-section">
      <div className="decision-basis-head">
        <div>
          <h4>{verdict.basis?.title || '작성 대상 판단 근거'}</h4>
          <p>왜 비용추계서 작성 대상인지와 어떤 자료를 근거로 삼았는지 정리했습니다.</p>
        </div>
        {source && (
          <button
            type="button"
            className="evidence-mini-btn"
            onClick={() => openModal({
              title: '참고 공식 비용추계서',
              meta: `국회 의안 ${source.bill_no || '-'}`,
              body:
                `${source.bill_name || '-'}\n` +
                `구조 유사도: ${Math.round((source.similarity || 0) * 100)}%\n\n` +
                `이 문서의 비용항목과 연도별 금액 구조를 현재 의안의 추계 초안 구성에 사용했습니다.`,
            })}
          >
            근거 보기
          </button>
        )}
      </div>
      <div className="decision-basis-grid">
        {basisRows.length > 0 ? basisRows.map((row, idx) => (
          <div key={idx} className="decision-basis-row">
            <span>{row.label}</span>
            <p>{row.text}</p>
          </div>
        )) : (
          <>
            {verdict.summary && (
              <div className="decision-basis-row">
                <span>판단 사유</span>
                <p>{verdict.summary}</p>
              </div>
            )}
            {verdict.nabo_reason && (
              <div className="decision-basis-row">
                <span>근거</span>
                <p>{verdict.nabo_reason}</p>
              </div>
            )}
          </>
        )}
      </div>
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
            onClick={() => openModal(evidenceModal(it, kind))}
          >
            <div className="ref-card-top">
              <span className="ref-card-title">
                {kind === 'bill'
                  ? `${it.bill_no} · ${(it.bill_name || '').slice(0, 45)}`
                  : '비용추계 법령 및 작성 기준'}
              </span>
              <span className="ref-card-sim">관련도 {Math.round((it.similarity || 0) * 100)}%</span>
            </div>
            <div className="ref-card-preview">{cleanExtractedText(it.content).slice(0, 180)}</div>
            <div className="ref-card-action">근거 상세보기</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// eslint-disable-next-line no-unused-vars
function FormView({ result, formType, setFormType }) {
  const renderKey = `${formType}:${result?.generatedAt || ''}:${result?.billName || ''}`
  const [rendered, setRendered] = useState({ key: '', html: '', err: '' })
  const [downloadingPdf, setDownloadingPdf] = useState(false)
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

  const handleDownloadPdf = async () => {
    setDownloadingPdf(true)
    try {
      const response = await fetch(`${API_BASE}/api/export/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result, format: formType }),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.error || 'PDF 생성에 실패했습니다.')
      }
      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition') || ''
      const matchedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)
      const fallbackName = `${result?.billName || '비용추계서'}_비용추계서_${formType === 'assembly' ? '국회' : '경기도'}.pdf`
      const downloadName = matchedName ? decodeURIComponent(matchedName[1]) : fallbackName
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = downloadName
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      window.alert(e.message)
    } finally {
      setDownloadingPdf(false)
    }
  }

  return (
    <div className="form-view animate-fade-in">
      <div className="form-toolbar">
        <div className="form-pickr">
          <button
            className={`pickr-btn ${formType === 'gyeonggi' ? 'active' : ''}`}
            onClick={() => setFormType('gyeonggi')}
          >
            경기도 양식
          </button>
          <button
            className={`pickr-btn ${formType === 'assembly' ? 'active' : ''}`}
            onClick={() => setFormType('assembly')}
          >
            국회 양식
          </button>
        </div>
        <div className="form-actions">
          <button className="form-btn" onClick={handleDownloadPdf} disabled={loading || downloadingPdf}>
            {downloadingPdf ? 'PDF 생성 중...' : 'PDF 다운로드'}
          </button>
          <button className="form-btn" onClick={handlePrint}>인쇄</button>
          <button className="form-btn" onClick={handleDownloadHtml}>HTML 다운로드</button>
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
          <div>
            {data.sourceLabel && <div className="modal-source">{data.sourceLabel}</div>}
            <h3>{data.title}</h3>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        {data.meta && <div className="modal-meta">{data.meta}</div>}
        <div className="modal-content-label">근거 원문</div>
        <div className="modal-body">
          {data.sourceLabel ? cleanExtractedText(data.body) : data.body}
        </div>
      </div>
    </div>
  )
}

export default App
