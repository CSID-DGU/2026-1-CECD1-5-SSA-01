import { useEffect, useState } from 'react'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

const LABELS = {
  start_year: '추계를 시작할 연도',
  infertility_population_basis: '난임치료휴가 대상자 산정 근거',
  daily_leave_benefit: '1인당 하루 휴가급여', paid_leave_days: '연간 급여 지급일수',
  headcount: '새로 필요한 인원', headcount_by_grade: '직급별 새 인원',
  salary_by_grade: '직급별 1인당 연간 보수', salary_per_person: '1인당 연간 보수',
  annual_salary_difference: '1인당 연간 보수 차액', annual_salary_amount: '연간 인건비',
  employer_contribution_rate: '기관 부담금 비율', basic_expense_ratio: '기본경비 비율',
  asset_unit_price_per_person: '1인당 초기 장비·집기 비용',
  annual_operating_amount: '연간 운영비', annual_amount: '연간 비용',
  annual_project_budget: '연도별 사업비', annual_phase_cost: '단계별 연간 사업비',
  phase_start_offset_years: '사업 시작까지 걸리는 기간', phase_duration_years: '사업 기간',
  operation_headcount: '운영 인원', annual_labor_cost_per_person: '운영 인력 1인당 연간 인건비',
  committee_components: '위원회 회의 구성', initial_study_cost: '첫해 연구비',
  quantity: '필요 수량', unit_cost: '1개당 비용',
  service_quantity: '서비스 이용 건수', service_unit_cost: '건당 비용',
  frequency_per_year: '연간 시행 횟수', plan_unit_cost: '계획 수립 비용',
  survey_unit_cost: '조사 1회 비용', recurrence_interval_years: '실시 주기',
  recipient_count: '지원 대상자 수', annual_recipients: '연간 지원 대상자 수',
  benefit_per_recipient: '1인당 지원금', existing_benefit_per_recipient: '기존 1인당 지원금',
  subsidy_rate: '지원 비율', test_unit_cost: '1인당 검사비',
  existing_annual_cost: '기존 사업의 연간 비용',
  visits_per_recipient: '1인당 이용 횟수', cost_per_visit: '1회 이용 비용',
  base_population: '기준 대상자 수', excluded_recipients: '제외 대상자 수',
  additional_recipients: '추가 대상자 수', project_cost: '전체 사업비',
  premium_base: '보험료 산정 기준액', new_support_rate: '새 지원 비율',
  existing_support_amount: '기존 지원액', required_area: '필요 면적',
  insurance_benefit_cohorts: '급여 대상 환자군',
  government_support_rate: '건강보험 지출 증가분에 연동되는 국고지원율',
  premium_receipts_by_year: '연도별 건강보험료 수입',
  new_general_support_rate: '개정 후 일반회계 지원율',
  current_general_support_rate: '현행 일반회계 실효 지원율',
  current_support_end_year: '현행 지원 기준의 마지막 적용 연도',
  existing_insurance_benefit_cost: '기존 공단 급여비',
  construction_unit_cost: '면적당 공사비', asset_quantity: '구입 수량',
  asset_unit_cost: '자산 1개당 비용', tax_base: '과세 기준금액',
  tax_rate_change: '세율 변화', taxpayer_count: '대상 납세자 수',
  deduction_change: '1인당 공제액 변화', transaction_count: '연간 거래 건수',
  fee_change_per_case: '건당 수수료 변화', institution_count: '대상 기관 수',
  contribution_per_institution: '기관당 출연금', government_share: '정부 분담 비율',
  historical_annual_fee_revenues: '과거 연도별 수수료 수입', exemption_rate: '감면 비율',
  annual_case_count: '연간 추가 대상 사건 수', action_rate: '조치 시행 비율',
  notices_per_case: '사건당 통지 횟수', notice_unit_price: '통지 1회 비용',
  annual_births: '연간 출생아 수', historical_leave_recipients: '기존 휴가 수급자 수',
  historical_births: '기준연도 출생아 수', funded_days_before: '기존 지원 일수',
  funded_days_after: '변경 후 지원 일수', reference_days: '기준 지원 일수',
  grant_cap_per_reference_period: '기준기간 최대 지원금',
  participation_rate: '참여 비율', payments_per_year: '연간 지급 횟수',
}

const STRUCTURED = new Set(['headcount_by_grade', 'salary_by_grade', 'committee_components', 'insurance_benefit_cohorts', 'premium_receipts_by_year'])
const SERIES = new Set(['annual_project_budget', 'historical_annual_fee_revenues', 'recipient_count'])
const PERCENT = /(?:rate|ratio|share)$/
const MONEY = /cost|price|amount|budget|salary|benefit|fee|tax_base|premium_base|revenues|deduction|contribution|grant_cap/

function variableMeta(key, routeKey) {
  if (key === 'benefit_per_recipient' && routeKey === 'transfer_child_asset_monthly') return { unit: '만원/월', engineUnit: 'KRW/person/month', factor: 10000 }
  if (key === 'payments_per_year') return { unit: routeKey === 'transfer_child_asset_monthly' ? '개월/년' : '회/년', engineUnit: routeKey === 'transfer_child_asset_monthly' ? 'month/year' : 'count/year', factor: 1 }
  if (key === 'infertility_population_basis') return { unit: '산정 근거', engineUnit: 'population_basis', factor: 1, structured: true }
  if (key === 'daily_leave_benefit') return { unit: '원/일', engineUnit: 'KRW/person/day', factor: 1 }
  if (key === 'paid_leave_days') return { unit: '일', engineUnit: 'day/person', factor: 1 }
  if (key === 'insurance_benefit_cohorts') return { unit: '환자군', engineUnit: 'cohort_bundle', factor: 1, structured: true }
  if (key === 'premium_receipts_by_year') return { unit: '연도별 원', engineUnit: 'KRW/year', factor: 1, structured: true }
  if (STRUCTURED.has(key)) return { unit: '상세 입력', engineUnit: 'structured', factor: 1, structured: true }
  if (PERCENT.test(key)) return { unit: '%', engineUnit: 'ratio', factor: 0.01 }
  if (MONEY.test(key)) return { unit: '만원', engineUnit: 'KRW', factor: 10000 }
  if (key === 'required_area') return { unit: '㎡', engineUnit: 'square_meter', factor: 1 }
  if (key.includes('year') || key.includes('duration')) return { unit: '년', engineUnit: 'year', factor: 1 }
  if (key.includes('frequency') || key.includes('visits') || key.includes('notices')) return { unit: '회', engineUnit: 'count', factor: 1 }
  return { unit: '명·건·개', engineUnit: 'count', factor: 1 }
}

function parseValue(raw, key, routeKey) {
  const meta = variableMeta(key, routeKey)
  if (meta.structured) {
    const parsed = JSON.parse(raw)
    if (parsed === null || typeof parsed !== 'object') throw new Error('형식에 맞는 값을 입력해 주세요.')
    return parsed
  }
  const pieces = SERIES.has(key) ? raw.split(',') : [raw]
  const values = pieces.map(part => Number(part.replace(/,/g, '').trim()))
  if (!values.length || values.some(value => !Number.isFinite(value)) || raw.trim() === '') {
    throw new Error('숫자를 확인해 주세요.')
  }
  return SERIES.has(key) && (key !== 'recipient_count' || values.length > 1)
    ? values.map(value => value * meta.factor) : values[0] * meta.factor
}

function parseCohortNumber(raw, label) {
  const parts = String(raw).split(',').map(part => part.trim().replace(/,/g, ''))
  if (!parts.length || parts.some(part => !part || !Number.isFinite(Number(part)) || Number(part) < 0)
    || (parts.length !== 1 && parts.length !== 5)) {
    throw new Error(`${label}: 숫자 하나 또는 5개 연도별 값을 입력해 주세요.`)
  }
  const values = parts.map(Number)
  return values.length === 1 ? values[0] : values
}

function formatAnnual(values) {
  return (values || []).map((value, index) =>
    `${index + 1}년차 ${value == null ? '—' : `${(value / 1000).toLocaleString()}백만원`}`
  ).join(' · ')
}

function candidateFor(item, variable) {
  if (variable === 'infertility_population_basis' || variable === 'daily_leave_benefit') {
    const row = (item.calculation?.referenceCandidates || []).find(candidate => candidate.variableKey === variable)
    if (!row) return null
    return { value: row.value, label: variable === 'daily_leave_benefit' ? `${Number(row.value).toLocaleString()}원/일` : '선례의 대상자 산정 방식', source: row.sourceRef, note: row.limitation }
  }
  if (variable === 'premium_receipts_by_year') {
    const row = (item.calculation?.referenceCandidates || [])
      .find(candidate => candidate.variableKey === variable)
    if (!row) return null
    return {
      value: row.value, label: '공식 전망 및 결산값 참고하기',
      source: row.sourceRef, note: row.limitation,
    }
  }
  if (variable === 'current_general_support_rate') {
    const row = (item.calculation?.referenceCandidates || [])
      .filter(candidate => candidate.variableKey === variable)
      .sort((left, right) => right.availableAt.localeCompare(left.availableAt))[0]
    if (!row) return null
    return {
      value: row.value,
      label: `${(Number(row.value) * 100).toFixed(1)}% 과거 실효율 후보`,
      source: row.sourceRef, note: row.limitation,
    }
  }
  if (variable === 'government_support_rate') {
    const row = (item.calculation?.referenceCandidates || [])
      .filter(candidate => candidate.variableKey === variable)
      .sort((left, right) => right.availableAt.localeCompare(left.availableAt))[0]
    if (!row) return null
    return {
      value: row.value, label: `${(row.value * 100).toLocaleString()}% 과거 실효율 후보`,
      source: `${row.sourceRef} (${row.sourceUrl})`, note: row.limitation,
    }
  }
  if (variable !== 'headcount' && variable !== 'headcount_by_grade') return null
  const scenarios = item.calculation?.staffingScenarios || []
  const candidate = scenarios.find(row => variable === 'headcount'
    ? Number.isFinite(Number(row.netStaff))
    : row.netStaffByGrade && Object.keys(row.netStaffByGrade).length > 0)
  if (!candidate) return null
  return {
    value: variable === 'headcount' ? candidate.netStaff : candidate.netStaffByGrade,
    label: variable === 'headcount' ? `${candidate.netStaff}명` : '직급별 인원 사용',
    source: `순증 인원 산정: ${candidate.formula}; ${(candidate.sourceRefs || []).join('; ')}`,
    note: candidate.assumption || candidate.warning || '',
  }
}

export default function ErceChat({ result }) {
  const erce = result.erce || {}
  const items = erce.items || []
  const [answers, setAnswers] = useState({})
  const [skipped, setSkipped] = useState({})
  const [calculations, setCalculations] = useState({})
  const [input, setInput] = useState('')
  const [committeeDraft, setCommitteeDraft] = useState({ members: '', meetings: '', rate: '' })
  const [insuranceDraft, setInsuranceDraft] = useState([
    { name: '', cases: '', days: '', dailyBenefit: '' },
  ])
  const [inputError, setInputError] = useState('')
  const [running, setRunning] = useState(false)
  const [showAdditional, setShowAdditional] = useState(false)
  const [draftResult, setDraftResult] = useState(null)
  const [draftRetry, setDraftRetry] = useState(0)
  const [reportStartYear, setReportStartYear] = useState(() => String(items.find(item => item.startYear)?.startYear || ''))

  const allQuestions = items.flatMap(item => {
    if (item.calculation?.status === 'computed_review') return []
    return (item.calculation?.missingVariables || item.requiredVariables || [])
      .filter(variable => !item.explicitInputs?.[variable])
      .map(variable => ({ item, variable, id: `${item.itemIndex}:${variable}` }))
  })
  const questions = showAdditional ? allQuestions : allQuestions.slice(0, 4)
  const additionalQuestionCount = allQuestions.length - questions.length
  const current = questions.find(question => !answers[question.id] && !skipped[question.id])
  const finished = questions.length - questions.filter(question => !answers[question.id] && !skipped[question.id]).length
  const computed = items.filter(item => (calculations[item.itemIndex] || item.calculation)?.status === 'computed_review')
  const allComputed = items.length > 0 && computed.length === items.length
  const toEngineItem = item => ({
    name: item.name, trigger_ref: item.triggerRef,
    route_key: item.routeKey, bill_no: erce.billNo, years: 5,
    start_year: answers[`${item.itemIndex}:start_year`]?.value ?? item.startYear,
    explicit_inputs: {
      ...item.explicitInputs,
      ...Object.fromEntries(Object.entries(answers)
        .filter(([id]) => id.startsWith(`${item.itemIndex}:`))
        .map(([id, value]) => [id.slice(id.indexOf(':') + 1), value])),
    },
    cutoff_date: item.proposeDate || '', policy_domain: item.policyDomain || '',
    staffing_context: item.staffingContext || {}, staffing_inputs: item.staffingInputs || {},
  })
  const chosenStartYear = Number(reportStartYear || items.map(item => toEngineItem(item).start_year).find(Boolean))
  const draftRequest = allComputed && Number.isInteger(chosenStartYear) && chosenStartYear >= 1900 && chosenStartYear <= 2200
    ? JSON.stringify({
      bill_name: result.billName, bill_no: erce.billNo, start_year: chosenStartYear, years: 5,
      items: items.map(toEngineItem),
      exclusions: [
        ...(erce.unmappedArticles || []).map(row => `${row.name || '미연결 조문'}: ${row.reason || '산식 미확정'}`),
        ...(erce.deferredItems || []).map(row => `${row.name || '검토 보류 항목'}: ${row.reason || '실시 여부·규모 미확정'}`),
        ...(erce.reviewCandidates || []).map(row => `${row.name || '추가 비용 가능성'}: 별도 검토 필요`),
      ],
    }) : null
  const draftMatches = draftResult?.request === draftRequest && draftResult?.attempt === draftRetry
  const draft = draftMatches ? draftResult?.data : null
  const draftError = draftMatches ? draftResult?.error || '' : ''
  const draftRunning = Boolean(draftRequest && !draft && !draftError)

  useEffect(() => {
    const controller = new AbortController()
    if (!draftRequest) return () => controller.abort()
    fetch(`${API_BASE}/api/erce/draft`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: draftRequest, signal: controller.signal,
    }).then(async response => {
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || '초안을 만들지 못했어요.')
      if (data.status !== 'draft_ready') throw new Error('아직 확인이 필요한 값이 있어요. 금액을 다시 확인해 주세요.')
      if (!controller.signal.aborted) setDraftResult({ request: draftRequest, attempt: draftRetry, data })
    }).catch(error => {
      if (!controller.signal.aborted) setDraftResult({ request: draftRequest, attempt: draftRetry, error: error.message })
    })
    return () => controller.abort()
  }, [draftRequest, draftRetry])

  const downloadDraft = () => {
    if (!draft) return
    const url = URL.createObjectURL(new Blob([draft.markdown], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${(result.billName || '비용추계').replace(/[\\/:*?"<>|]/g, '_')}_초안.md`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const saveAnswer = async (value, source) => {
    if (!current) return
    const { item, variable, id } = current
    const meta = variableMeta(variable, item.routeKey)
    const updated = {
      ...answers,
      [id]: { value, unit: meta.engineUnit, source_ref: source || '사용자가 직접 입력한 추계 가정(별도 확인 필요)' },
    }
    setAnswers(updated)
    setInput('')
    setInputError('')
    const remaining = allQuestions.some(question => question.item.itemIndex === item.itemIndex && !updated[question.id])
    if (remaining) return
    setRunning(true)
    try {
      const explicitInputs = { ...item.explicitInputs }
      for (const question of allQuestions.filter(row => row.item.itemIndex === item.itemIndex)) {
        if (updated[question.id]) explicitInputs[question.variable] = updated[question.id]
      }
      const response = await fetch(`${API_BASE}/api/erce/estimate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          route_key: item.routeKey, bill_no: erce.billNo, years: 5, start_year: explicitInputs.start_year?.value ?? item.startYear,
          explicit_inputs: explicitInputs, cutoff_date: item.proposeDate || '',
          policy_domain: item.policyDomain || '',
          staffing_context: item.staffingContext || {}, staffing_inputs: item.staffingInputs || {},
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || '계산하지 못했어요.')
      setCalculations(previous => ({ ...previous, [item.itemIndex]: data }))
      if (variable === 'committee_components') setCommitteeDraft({ members: '', meetings: '', rate: '' })
    } catch (error) {
      setAnswers(answers)
      setInputError(error.message)
    } finally {
      setRunning(false)
    }
  }

  const submit = event => {
    event.preventDefault()
    if (!current || running) return
    try {
      if (current.variable === 'committee_components') {
        const members = Number(committeeDraft.members)
        const meetings = Number(committeeDraft.meetings)
        const rate = Number(committeeDraft.rate)
        if ([committeeDraft.members, committeeDraft.meetings, committeeDraft.rate].some(value => !String(value).trim())
          || ![members, meetings, rate].every(value => Number.isFinite(value) && value > 0)) {
          throw new Error('세 값을 모두 입력해 주세요.')
        }
        saveAnswer([{
          paid_members: members, annual_meetings: meetings, meeting_unit_price: rate * 10000,
        }], `사용자가 입력한 가정: 민간위원 ${members}명, 연 ${meetings}회, 회당 ${rate}만원`)
      } else if (current.variable === 'insurance_benefit_cohorts') {
        const cohorts = insuranceDraft.map((row, index) => ({
          label: row.name.trim() || `환자군 ${index + 1}`,
          eligible_cases: parseCohortNumber(row.cases, `환자군 ${index + 1} 대상 건수`),
          covered_days_per_case: parseCohortNumber(row.days, `환자군 ${index + 1} 지원일수`),
          insurer_daily_benefit: parseCohortNumber(row.dailyBenefit, `환자군 ${index + 1} 일당 공단급여비`),
        }))
        saveAnswer(cohorts, '사용자가 입력한 환자군·지원일수·일당 공단급여비(시나리오별 근거 확인 필요)')
      } else {
        saveAnswer(parseValue(input, current.variable, current.item.routeKey), '')
      }
    }
    catch (error) { setInputError(error instanceof SyntaxError ? 'JSON 형식을 확인해 주세요.' : error.message) }
  }

  if (result.analysisMode === 'manual_required') {
    return <section className="chat-shell"><div className="chat-bubble assistant">PDF는 받았어요. 자동 분석을 사용하려면 ERCE의 AI 분석 모드를 켜야 해요.</div></section>
  }

  return (
    <section className="chat-shell" aria-label="비용추계 대화">
      <div className="chat-progress"><span>비용추계 초안</span><span>{finished} / {questions.length}개 진행</span></div>
      <div className="chat-bubble assistant">
        <span className="chat-eyebrow">PDF 분석 완료</span>
        <strong>{result.billName || '의안'}을 확인했어요.</strong>
        <p>{items.length ? `우선 추계할 항목 ${items.length}개를 찾았어요. 문서에서 확인한 값은 다시 묻지 않을게요.` : '바로 계산할 항목은 찾지 못했어요. 조문 검토가 필요합니다.'}</p>
      </div>

      {computed.length > 0 && <div className="chat-result-list">
        {computed.map(item => {
          const output = calculations[item.itemIndex] || item.calculation
          return <div className="chat-result" key={item.itemIndex}>
            <span className="chat-check">✓</span>
            <div><strong>{item.name || '비용 항목'} 계산 초안</strong><p>{formatAnnual(output.annualAmountsThousand)}</p>
              <details><summary>계산 근거 보기</summary><p>{item.formula}</p><p>{(output.sourceRefs || []).join(' · ') || '입력된 값과 의안 원문을 사용했습니다.'}</p></details>
            </div>
          </div>
        })}
      </div>}

      {current && <>
        <div className="chat-bubble assistant question">
          <span className="chat-eyebrow">{current.item.name || '비용 항목'} · {finished + 1}번째 확인</span>
          <strong>{LABELS[current.variable] || current.variable}을 알 수 있을까요?</strong>
          <p>의안에서 확정할 수 없어 비워뒀어요. 모르면 건너뛰어도 됩니다. 임의의 숫자는 넣지 않을게요.</p>
        </div>
        {(() => {
          const candidate = candidateFor(current.item, current.variable)
          return candidate && <button className="chat-candidate" type="button" disabled={running}
            onClick={() => saveAnswer(candidate.value, candidate.source)}>
            <span>참고할 수 있는 후보값</span><strong>{candidate.label} 사용하기 →</strong>
            <small>{candidate.note || candidate.source}</small>
          </button>
        })()}
        {current.variable === 'insurance_benefit_cohorts' && (() => {
          const references = (current.item.calculation?.referenceCandidates || [])
            .filter(row => (row.variableKey === 'insurer_daily_benefit' && !row.stayBand)
              || row.variableKey === 'covered_days_per_case_max')
          return references.length > 0 && <div className="chat-reference-list">
            <strong>발의일 전에 공개된 참고값</strong>
            {references.map(row => <p key={row.evidenceKey}>
              {row.variableKey === 'insurer_daily_benefit'
                ? `${row.scenarioKey}형 · 2024년 일당 공단부담액 ${Number(row.value).toLocaleString()}원`
                : `${row.patientGroup === 'medical_critical' ? '의료최고도' : '의료고도'} · 시범사업 최대 ${row.value}일`}
            </p>)}
            <small>시범사업 기준을 전국 대상자 수나 실제 평균 지원일수로 사용하면 안 됩니다. 180일 초과 구간은 별도 단가가 필요해요.</small>
          </div>
        })()}
        <form className="chat-compose" onSubmit={submit}>
          {current.variable === 'insurance_benefit_cohorts' ? <div className="chat-insurance-cohorts">
            <small>한 번에 하나의 A/B/C 간병 시나리오만 계산해요. 환자군별 대상 건수·지원일수·일당 <b>공단 부담액</b>을 입력해 주세요. 연도별 대상 건수는 쉼표로 구분한 5개 숫자도 가능합니다.</small>
            {insuranceDraft.map((row, index) => <div className="chat-insurance-row" key={index}>
              <div className="chat-insurance-row-head"><strong>환자군 {index + 1}</strong>{insuranceDraft.length > 1 && <button type="button" onClick={() => setInsuranceDraft(previous => previous.filter((_, i) => i !== index))}>삭제</button>}</div>
              <div className="chat-component-fields">
                <label>구분<input value={row.name} onChange={event => setInsuranceDraft(previous => previous.map((item, i) => i === index ? { ...item, name: event.target.value } : item))} placeholder="예: 의료고도 180일 이하" /></label>
                <label>연간 급여대상 입원 건수<input inputMode="decimal" value={row.cases} onChange={event => setInsuranceDraft(previous => previous.map((item, i) => i === index ? { ...item, cases: event.target.value } : item))} placeholder="건수 또는 연도별 5개" /></label>
                <label>건당 지원일수<input inputMode="decimal" value={row.days} onChange={event => setInsuranceDraft(previous => previous.map((item, i) => i === index ? { ...item, days: event.target.value } : item))} placeholder="일" /></label>
                <label>일당 공단급여비<input inputMode="decimal" value={row.dailyBenefit} onChange={event => setInsuranceDraft(previous => previous.map((item, i) => i === index ? { ...item, dailyBenefit: event.target.value } : item))} placeholder="원" /></label>
              </div>
            </div>)}
            <button type="button" className="chat-revisit" onClick={() => setInsuranceDraft(previous => [...previous, { name: '', cases: '', days: '', dailyBenefit: '' }])}>환자군 추가</button>
          </div> : current.variable === 'committee_components' ? <div className="chat-component-fields">
            <label>유급 민간위원 수<input inputMode="numeric" value={committeeDraft.members}
              onChange={event => setCommitteeDraft(previous => ({ ...previous, members: event.target.value }))}
              placeholder="명" /></label>
            <label>연간 회의 횟수<input inputMode="numeric" value={committeeDraft.meetings}
              onChange={event => setCommitteeDraft(previous => ({ ...previous, meetings: event.target.value }))}
              placeholder="회" /></label>
            <label>1인당 회의수당<input inputMode="decimal" value={committeeDraft.rate}
              onChange={event => setCommitteeDraft(previous => ({ ...previous, rate: event.target.value }))}
              placeholder="만원" /></label>
          </div> : variableMeta(current.variable).structured ? <textarea
            aria-label={`${LABELS[current.variable] || current.variable} 입력`} value={input}
            onChange={event => setInput(event.target.value)}
            placeholder={current.variable === 'premium_receipts_by_year' ? '{"2023": 81518000000000, "2024": 85100000000000}' : current.variable === 'headcount_by_grade' ? '{"5급": 1, "6급": 2}' : '항목별 값을 JSON으로 입력'}
            rows={3} /> : <div className="chat-input-wrap">
            <input aria-label={`${LABELS[current.variable] || current.variable} 입력`} inputMode="decimal"
              value={input} onChange={event => setInput(event.target.value)}
              placeholder={SERIES.has(current.variable) ? '연도별 숫자를 쉼표로 구분' : '숫자를 입력해 주세요'} />
            <span>{variableMeta(current.variable, current.item.routeKey).unit}</span>
          </div>}
          <div className="chat-actions"><button type="button" className="chat-skip" disabled={running}
            onClick={() => { setSkipped(previous => ({ ...previous, [current.id]: true })); setInput(''); setInputError('') }}>모르겠어요</button>
            <button type="submit" className="chat-submit" disabled={(current.variable === 'committee_components'
              ? Object.values(committeeDraft).some(value => !String(value).trim())
              : current.variable === 'insurance_benefit_cohorts'
                ? insuranceDraft.some(row => !row.cases.trim() || !row.days.trim() || !row.dailyBenefit.trim())
                : !input.trim()) || running}>{running ? '계산 중…' : '확인'}</button></div>
          {inputError && <p className="chat-error" role="alert">{inputError}</p>}
          <small>직접 입력한 값은 ‘사용자 가정’으로 표시됩니다. 계산 전에 근거를 다시 확인해 주세요.</small>
        </form>
      </>}

      {!current && <div className="chat-bubble assistant question">
        <strong>지금 확인할 질문은 여기까지예요.</strong>
        <p>{questions.some(question => skipped[question.id])
          ? '모르는 값은 비워뒀어요. 해당 항목의 금액은 확정하지 않았습니다.'
          : '계산된 금액은 검토용 초안입니다. 적용 범위와 근거를 확인해 주세요.'}</p>
      </div>}
      {(erce.unmappedArticles || []).length > 0 && <div className="chat-note">산식을 확정하지 못한 조문 {erce.unmappedArticles.length}개는 계산에서 제외했어요.</div>}
      {(erce.deferredItems || []).length > 0 && <div className="chat-note">실시 여부나 규모가 정해지지 않은 항목 {erce.deferredItems.length}개는 지금 숫자를 묻지 않고 검토 대상으로 남겼어요.</div>}
      {(erce.reviewCandidates || []).length > 0 && <div className="chat-note">추가 비용 가능성 {(erce.reviewCandidates || []).length}건은 아직 금액에 포함하지 않았어요.</div>}
      {additionalQuestionCount > 0 && <div className="chat-note">다른 확인값 {additionalQuestionCount}개는 우선 질문에서 제외했어요. 필요한 경우 이어서 검토할 수 있어요.</div>}
      {additionalQuestionCount > 0 && !current && <button className="chat-revisit" type="button" onClick={() => setShowAdditional(true)}>나머지 항목도 검토하기</button>}
      {Object.keys(skipped).length > 0 && <button className="chat-revisit" type="button" onClick={() => setSkipped({})}>건너뛴 질문 다시 보기</button>}
      {allComputed && <div className="chat-bubble assistant">
        <strong>금액을 모두 계산했어요. 비용추계서 초안으로 정리할게요.</strong>
        <p>초안에 사용할 시작연도를 확인해 주세요. 입력한 가정과 근거도 함께 담아요.</p>
        <label>추계 시작연도 <input className="chat-report-year" aria-label="초안 추계 시작연도"
          type="number" min="1900" max="2200" value={reportStartYear || (chosenStartYear || '')}
          onChange={event => setReportStartYear(event.target.value)} placeholder="예: 2026" /></label>
        {draftRunning && <p role="status">확인한 값으로 다시 계산하고 초안을 정리하고 있어요.</p>}
        {draftError && <><p className="chat-error" role="alert">{draftError}</p><button className="chat-revisit" type="button" onClick={() => setDraftRetry(value => value + 1)}>다시 만들기</button></>}
      </div>}
      {draft && <article className="chat-draft" aria-label="비용추계서 초안">
        <span className="chat-eyebrow">검토용 · 공식 비용추계서가 아닙니다</span>
        <h3>{draft.title} 비용추계서 초안</h3>
        <h4>Ⅰ. 비용추계 결과</h4><p>{draft.summary}</p>
        <small>단위: 천원</small>
        <div className="chat-draft-table"><table><thead><tr><th>항목</th>
          {Array.from({ length: draft.years }, (_, i) => <th key={i}>{draft.startYear + i}</th>)}<th>합계</th>
        </tr></thead><tbody>
          {draft.items.map((item, index) => <tr key={index}><th>{item.name}</th>
            {item.annualAmountsThousand.map((value, i) => <td key={i}>{value.toLocaleString()}</td>)}
            <td>{item.annualAmountsThousand.reduce((sum, value) => sum + value, 0).toLocaleString()}</td></tr>)}
          <tr><th>합계</th>{draft.annualAmountsThousand.map((value, i) => <td key={i}>{value.toLocaleString()}</td>)}<td>{draft.totalAmountThousand.toLocaleString()}</td></tr>
        </tbody></table></div>
        <h4>Ⅱ. 재정수반요인</h4>
        {draft.items.map((item, index) => <p key={index}>{item.triggerRef || '조문 확인 필요'} · {item.name}</p>)}
        <h4>Ⅲ. 추계의 전제와 상세내역</h4>
        {draft.items.map((item, index) => <details key={index}><summary>{item.name} · 산식과 입력 근거</summary>
          <p>{item.formula}</p>
          {Object.entries(item.resolvedVariables).map(([key, row]) => <p key={key}>
            <strong>{LABELS[key] || key}</strong>: {JSON.stringify(row.value)} {row.unit}<br /><small>{row.source_ref}</small>
          </p>)}
        </details>)}
        <h4>Ⅳ. 부대의견 및 검토사항</h4>
        <p>사용자 입력과 선례 가정의 적용 조건, 중복 지원 및 비용 항목의 누락 여부를 검토해 주세요. 입력하지 않은 선택 변수에는 산식 기본값이 적용됩니다.</p>
        {draft.exclusions.map((text, index) => <p className="chat-note" key={index}>미산출·검토 보류: {text}</p>)}
        <button className="chat-revisit" type="button" onClick={downloadDraft}>초안 내려받기 (.md)</button>
      </article>}
    </section>
  )
}
