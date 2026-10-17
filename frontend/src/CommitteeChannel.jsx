import { useState } from 'react'

const STATUS = {
  computed: { label: '계산 완료', tone: 'green' },
  review_required: { label: '확인 필요', tone: 'amber' },
  blocked_missing_variables: { label: '입력 필요', tone: 'red' },
}

const ROUTE = {
  verified: {
    eyebrow: '1단계 · 검증된 선례',
    title: '자동으로 계산했어요',
    description: '산식과 필수 변수가 모두 있는 공식 추계서만 사용했습니다.',
  },
  recommended: {
    eyebrow: '2단계 · 유사 선례',
    title: '추천값을 확인해 주세요',
    description: '구조가 비슷한 공식 추계서를 참고했지만, 이 의안의 확정값은 아닙니다.',
  },
  input: {
    eyebrow: '3단계 · Human-in-the-loop',
    title: '없는 값만 입력해 주세요',
    description: '검증할 근거가 없는 금액은 임의로 만들지 않습니다.',
  },
}

const SOURCE_LABEL = {
  document: '조문에 명시',
  document_delta: '조문의 순증값',
  tag_prior: '선례 추천값',
  user_confirmed: '사용자 확정',
  optional_input: '선택 입력',
  missing: '입력 필요',
}

function formatAmount(value) {
  if (value === null || value === undefined) return '미확정'
  const won = Number(value) * 1000
  if (Math.abs(won) >= 100_000_000) {
    return `${(won / 100_000_000).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}억 원`
  }
  if (Math.abs(won) >= 10_000) {
    return `${(won / 10_000).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}만 원`
  }
  return `${won.toLocaleString('ko-KR')} 원`
}

function collectDrafts(result) {
  const drafts = {}
  for (const committee of result?.committees || []) {
    drafts[committee.id] = {}
    for (const [key, variable] of Object.entries(committee.variables || {})) {
      drafts[committee.id][key] = variable.value ?? ''
    }
  }
  return drafts
}

function routeLevel(committee) {
  if (committee.evidence_route?.level) return committee.evidence_route.level
  if (committee.status === 'computed') return 'verified'
  if (committee.status === 'review_required') return 'recommended'
  return 'input'
}

function candidateFacts(candidate) {
  const facts = []
  if (candidate.paid_members !== null && candidate.paid_members !== undefined) {
    facts.push(`유급 ${candidate.paid_members}명`)
  }
  if (candidate.annual_meetings !== null && candidate.annual_meetings !== undefined) {
    facts.push(`연 ${candidate.annual_meetings}회`)
  }
  if (candidate.meeting_unit_price !== null && candidate.meeting_unit_price !== undefined) {
    facts.push(`회당 ${(Number(candidate.meeting_unit_price) / 10_000).toLocaleString('ko-KR')}만 원`)
  }
  return facts.join(' · ') || '산식·변수 근거 검토 필요'
}

export default function CommitteeResult({ result, onResult, apiBase }) {
  const [drafts, setDrafts] = useState(() => collectDrafts(result))
  const [isRecomputing, setIsRecomputing] = useState(false)
  const [error, setError] = useState('')

  const committees = result?.committees || []
  const previewTotal = result?.summary?.previewTotalThousand
  const flowCounts = { verified: 0, recommended: 0, input: 0 }
  for (const committee of committees) flowCounts[routeLevel(committee)] += 1
  const editableCount = flowCounts.recommended + flowCounts.input

  const updateDraft = (committeeId, key, value) => {
    setDrafts(current => ({
      ...current,
      [committeeId]: { ...(current[committeeId] || {}), [key]: value },
    }))
  }

  const recompute = async () => {
    const userInputs = []
    for (const committee of committees) {
      // A complete verified package is already executable evidence. It must
      // not be silently overwritten by the old preview variables.
      if (committee.calculation_mode === 'verified_package') continue
      for (const key of Object.keys(committee.variables || {})) {
        const value = drafts?.[committee.id]?.[key]
        if (value === '' || value === null || value === undefined) continue
        userInputs.push({ committeeId: committee.id, variable: key, value: Number(value) })
      }
    }
    if (userInputs.length === 0) {
      setError('확인할 값을 하나 이상 입력해 주세요.')
      return
    }
    setIsRecomputing(true)
    setError('')
    try {
      const response = await fetch(`${apiBase}/api/recompute_committee`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result, userInputs }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || '재계산하지 못했습니다.')
      setDrafts(collectDrafts(data))
      onResult(data)
    } catch (reason) {
      setError(reason.message)
    } finally {
      setIsRecomputing(false)
    }
  }

  if (committees.length === 0) {
    return (
      <div className="committee-empty">
        <span className="committee-channel-kicker">위원회 전용 채널</span>
        <h3>위원회 설치·구성 조문을 찾지 못했어요.</h3>
        <p>{result.scope?.description}</p>
      </div>
    )
  }

  return (
    <div className="committee-workspace">
      <section className="committee-summary">
        <div>
          <span className="committee-channel-kicker">위원회 전용 채널</span>
          <h3>{result.scope?.committeeCount}개 위원회를 찾아 근거 수준별로 나눠었어요.</h3>
          <p>자동 계산과 추천값, 직접 입력을 구분해 보여줍니다.</p>
        </div>
        <div className="committee-total">
          <span>5개년 계산·미리보기 합계</span>
          <strong>{formatAmount(previewTotal)}</strong>
          {editableCount > 0 && <small>{editableCount}건은 확인 전 초안입니다.</small>}
        </div>
      </section>

      <section className="committee-flow-stats" aria-label="근거 수준별 결과">
        {Object.entries(ROUTE).map(([level, meta]) => (
          <div className={`committee-flow-stat ${level}`} key={level}>
            <span>{meta.eyebrow}</span>
            <strong>{flowCounts[level]}건</strong>
            <small>{meta.title}</small>
          </div>
        ))}
      </section>

      {result.summary?.isPartial && (
        <div className="committee-scope-notice">
          이 결과는 위원회 회의수당 중심의 부분 추계입니다. 인건비·조사용역·지원사업비는 범위 밖으로 표시합니다.
        </div>
      )}

      <div className="committee-list">
        {committees.map(committee => {
          const level = routeLevel(committee)
          const route = ROUTE[level]
          const status = STATUS[committee.status] || STATUS.blocked_missing_variables
          const isVerifiedPackage = committee.calculation_mode === 'verified_package'
          const candidates = committee.reference_candidates || []
          const amountLabel = level === 'verified' ? '확정 연간액' : level === 'recommended' ? '예상 연간액' : '연간액'
          return (
            <article className={`committee-card route-${level}`} key={committee.id}>
              <div className="committee-card-head">
                <div>
                  <div className="committee-card-meta">
                    <span className={`committee-status ${status.tone}`}>{status.label}</span>
                    <span>{committee.change_type_label}</span>
                  </div>
                  <h3>{committee.name}</h3>
                  <p className="committee-formula">{committee.formula}</p>
                </div>
                <div className="committee-card-amount">
                  <span>{amountLabel}</span>
                  <strong>{formatAmount(committee.annual_amount_thousand)}</strong>
                  <small>5개년 {formatAmount(committee.total_amount_thousand)}</small>
                </div>
              </div>

              <div className={`committee-evidence-route ${level}`}>
                <div>
                  <span>{route.eyebrow}</span>
                  <strong>{route.title}</strong>
                </div>
                <p>{committee.evidence_route?.summary || route.description}</p>
                {committee.evidence_route?.selected_bill_no && (
                  <small>선택 선례 · 의안 {committee.evidence_route.selected_bill_no}</small>
                )}
              </div>

              {isVerifiedPackage ? (
                <div className="committee-line-items">
                  <div className="committee-section-title">
                    <strong>계산에 쓴 항목</strong>
                    <span>산식·변수·시계열 검증 완료</span>
                  </div>
                  {(committee.verified_line_items || []).map((line, index) => (
                    <div className="committee-line-item" key={`${line.item_name}-${index}`}>
                      <div>
                        <strong>{line.item_name}</strong>
                        <span>{line.formula}</span>
                      </div>
                      <b>{formatAmount(line.full_year_thousand)}</b>
                    </div>
                  ))}
                  {(committee.evidence_route?.warnings || []).map((warning, index) => (
                    <p className="committee-route-warning" key={index}>{warning}</p>
                  ))}
                </div>
              ) : (
                <div className="committee-variable-grid">
                  {Object.entries(committee.variables || {}).map(([key, variable]) => (
                    <label className={`committee-variable ${variable.blocking ? 'blocking' : ''}`} key={key}>
                      <span className="committee-variable-label">
                        {variable.label}
                        <em className={variable.confirmed ? 'confirmed' : ''}>
                          {variable.confirmed ? '확정' : SOURCE_LABEL[variable.source_type] || '검토'}
                        </em>
                      </span>
                      <div className="committee-input-wrap">
                        <input
                          type="number"
                          value={drafts?.[committee.id]?.[key] ?? ''}
                          placeholder="값 입력"
                          onChange={event => updateDraft(committee.id, key, event.target.value)}
                        />
                        <span>{variable.unit}</span>
                      </div>
                      <small title={variable.basis}>{variable.basis}</small>
                    </label>
                  ))}
                </div>
              )}

              {candidates.length > 0 && (
                <div className="committee-candidate-panel">
                  <div className="committee-section-title">
                    <strong>왜 이 값을 추천했나요?</strong>
                    <span>시점 오염을 막고 제안일 이전 추계서만 검색</span>
                  </div>
                  <div className="committee-candidate-list">
                    {candidates.map((candidate, index) => (
                      <div className="committee-candidate" key={`${candidate.bill_no}-${index}`}>
                        <span>{index + 1}</span>
                        <div>
                          <strong>{candidate.committee_name || candidate.bill_name}</strong>
                          <small>의안 {candidate.bill_no} · {candidateFacts(candidate)}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {committee.paid_member_adjustment?.applied && (
                <div className="committee-adjustment">
                  <strong>순증 인원 반영</strong>
                  <span>{committee.paid_member_adjustment.basis}</span>
                </div>
              )}

              {committee.out_of_scope?.length > 0 && (
                <div className="committee-exclusions">
                  <strong>이 채널에서 제외:</strong> {committee.out_of_scope.join(', ')}
                </div>
              )}

              <details className="committee-advanced-details">
                <summary>조문과 검색 근거 자세히 보기</summary>
                <div className="committee-details">
                  <div>
                    <h4>계산 근거 조문 {committee.articles?.length || 0}건</h4>
                    {(committee.articles || []).map((article, index) => (
                      <div className="committee-article" key={`${article.no}-${index}`}>
                        <strong>{article.no}</strong>
                        <p>{article.text}</p>
                      </div>
                    ))}
                  </div>
                  <div>
                    <h4>기존 RAG 검색 {committee.references?.length || 0}건</h4>
                    {(committee.references || []).map(reference => (
                      <div className="committee-reference" key={reference.bill_no}>
                        <strong>{reference.bill_no} · {reference.bill_name}</strong>
                        <span>{(reference.retrieval || []).join(' + ')} · 유사도 {Math.round((reference.similarity || 0) * 100)}%</span>
                        <p>{reference.content}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </details>
            </article>
          )
        })}
      </div>

      {error && <div className="status-banner error">{error}</div>}
      {result.feedbackQueue?.queued > 0 && (
        <div className="committee-feedback-saved">
          확정값 {result.feedbackQueue.queued}건을 로컬 검토 큐에 저장했습니다. DB에는 아직 올리지 않았습니다.
        </div>
      )}
      {editableCount > 0 && (
        <button className="committee-recompute" onClick={recompute} disabled={isRecomputing}>
          {isRecomputing ? '재계산 중...' : '확인한 값으로 바로 재계산'}
        </button>
      )}
    </div>
  )
}
