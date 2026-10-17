import { useEffect, useRef, useState } from 'react'
import { userMessage } from './userMessages'
import { formatReferenceValue, referenceCandidates, selectedEvidenceContext } from './erceCandidates'
import { displayValue, displaySources } from './erceDisplay'
import ErceEvidence from './ErceEvidence'

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

export default function ErceChat({ result, onRetryAnalysis }) {
  const erce = result.erce || {}
  const [recoveredItems, setRecoveredItems] = useState({})
  const items = (erce.items || []).map(item => recoveredItems[item.itemIndex] || item)
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
  const [draftRequested, setDraftRequested] = useState(false)
  const [pdfDownloading, setPdfDownloading] = useState(false)
  const [pdfError, setPdfError] = useState('')
  const [confirmedAssumptions, setConfirmedAssumptions] = useState({})
  const inputFormRef = useRef(null)
  const [reportStartYear, setReportStartYear] = useState(() => String(items.find(item => item.startYear)?.startYear || ''))
  useEffect(() => {
    let closed = []
    const expand = () => {
      closed = [...document.querySelectorAll('.chat-draft details:not([open])')]
      closed.forEach(element => { element.open = true })
    }
    const restore = () => { closed.forEach(element => { element.open = false }); closed = [] }
    window.addEventListener('beforeprint', expand)
    window.addEventListener('afterprint', restore)
    return () => { window.removeEventListener('beforeprint', expand); window.removeEventListener('afterprint', restore) }
  }, [])

  const allQuestions = items.flatMap(item => {
    if (item.assumptionConfirmationRequired && !confirmedAssumptions[item.itemIndex]) return []
    if (item.calculation?.status === 'needs_review') return []
    if (item.calculation?.status === 'computed_review') return []
    return (item.calculation?.missingVariables || item.requiredVariables || [])
      .filter(variable => !item.explicitInputs?.[variable])
      .map(variable => ({ item, variable, id: `${item.itemIndex}:${variable}` }))
  })
  const questions = showAdditional ? allQuestions : allQuestions.slice(0, 4)
  const additionalQuestionCount = allQuestions.length - questions.length
  const current = questions.find(question => !answers[question.id] && !skipped[question.id])
  const finished = questions.length - questions.filter(question => !answers[question.id] && !skipped[question.id]).length
  const computed = items.filter(item => (!item.assumptionConfirmationRequired || confirmedAssumptions[item.itemIndex])
    && (calculations[item.itemIndex] || item.calculation)?.status === 'computed_review')
  const allComputed = items.length > 0 && computed.length === items.length
  const reviewBlocked = items.some(item => item.calculation?.status === 'needs_review')
  const toEngineItem = item => ({
    ...selectedEvidenceContext(item, answers),
    name: item.name, trigger_ref: item.triggerRef,
    change_summary: item.scopeNote || item.decisionReason || '',
    source_quote: item.reviewedSourceQuote || (result.articles?.[item.itemIndex]?.quote_verified ? result.articles[item.itemIndex].text : ''),
    route_key: item.routeKey, bill_no: erce.billNo, years: 5,
    start_year: answers[`${item.itemIndex}:start_year`]?.value ?? item.startYear,
    explicit_inputs: {
      ...item.explicitInputs,
      ...Object.fromEntries(Object.entries(answers)
        .filter(([id, row]) => id.startsWith(`${item.itemIndex}:`) && !row.evidenceKey)
        .map(([id, value]) => [id.slice(id.indexOf(':') + 1), value])),
    },
    cutoff_date: item.evidenceCutoff || item.proposeDate || '', policy_domain: item.policyDomain || '',
    staffing_context: item.staffingContext || {}, staffing_inputs: item.staffingInputs || {},
  })
  const chosenStartYear = Number(reportStartYear || items.map(item => toEngineItem(item).start_year).find(Boolean))
  const draftRequest = draftRequested && allComputed && Number.isInteger(chosenStartYear) && chosenStartYear >= 1900 && chosenStartYear <= 2200
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
      if (!controller.signal.aborted) setDraftResult({ request: draftRequest, attempt: draftRetry, error: userMessage(error) })
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

  const downloadPdf = async () => {
    if (!draft || !draftRequest || pdfDownloading) return
    setPdfDownloading(true)
    setPdfError('')
    try {
      const response = await fetch(`${API_BASE}/api/erce/draft/pdf`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: draftRequest,
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error || 'PDF를 만들지 못했어요.')
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `${(result.billName || '의안').replace(/[\\/:*?"<>|]/g, '_')}_비용추계서_초안.pdf`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (error) {
      setPdfError(userMessage(error))
    } finally {
      setPdfDownloading(false)
    }
  }

  const saveAnswer = async (value, source, candidate = null) => {
    if (!current) return
    const { item, variable, id } = current
    const meta = variableMeta(variable, item.routeKey)
    const updated = {
      ...answers,
      [id]: { value, unit: candidate?.unit || meta.engineUnit,
        source_ref: source || '사용자가 직접 입력한 추계 가정(별도 확인 필요)',
        ...(candidate?.evidenceKey ? { evidenceKey: candidate.evidenceKey } : {}) },
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
        if (updated[question.id] && !updated[question.id].evidenceKey) explicitInputs[question.variable] = updated[question.id]
      }
      const response = await fetch(`${API_BASE}/api/erce/estimate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...selectedEvidenceContext(item, updated),
          route_key: item.routeKey, bill_no: erce.billNo, years: 5, start_year: explicitInputs.start_year?.value ?? item.startYear,
          explicit_inputs: explicitInputs, cutoff_date: item.evidenceCutoff || item.proposeDate || '',
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
      setInputError(userMessage(error))
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
  const candidates = current ? referenceCandidates(current.item, current.variable, candidateFor(current.item, current.variable)) : []
  const focusManualInput = () => {
    inputFormRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    inputFormRef.current?.querySelector('input, textarea')?.focus({ preventScroll: true })
  }
  const acceptCitation = (item, candidate) => {
    setRecoveredItems(previous => ({ ...previous, [item.itemIndex]: {
      ...item, name: `${candidate.articleRef} · 양육비 선지급`, triggerRef: candidate.articleRef,
      reviewedSourceQuote: candidate.sourceQuote,
      engineContext: candidate.engineContext, calculation: candidate.calculation,
      startYear: candidate.startYear, assumptionConfirmationRequired: true,
      assumptionNotice: candidate.engineContext.reference_notice,
    } }))
    setConfirmedAssumptions(previous => ({ ...previous, [item.itemIndex]: false }))
    setDraftRequested(false)
  }

  return (
    <div className={`chat-layout${current ? ' has-candidates' : ''}`}>
    <section className="chat-shell" aria-label="비용추계 대화">
      <div className="chat-progress"><span>비용추계 초안</span><span>{reviewBlocked ? '원문 확인 필요' : allComputed ? '추계 완료' : questions.length ? `${finished} / ${questions.length}개 진행` : '근거 확인'}</span></div>
      <div className="chat-bubble assistant">
        <span className="chat-eyebrow">PDF 분석 완료</span>
        <strong>{result.billName || '의안'}을 확인했어요.</strong>
        <p>{items.length ? `우선 추계할 항목 ${items.length}개를 찾았어요. 문서에서 확인한 값은 다시 묻지 않을게요.` : '바로 계산할 항목은 찾지 못했어요. 조문 검토가 필요합니다.'}</p>
      </div>

      {items.filter(item => item.assumptionConfirmationRequired && !confirmedAssumptions[item.itemIndex]).map(item =>
        <div className="chat-assumption" key={item.itemIndex}>
          <span className="chat-eyebrow">계산 전 확인</span>
          <strong>이 기준으로 계산할게요</strong>
          {item.engineContext?.child_support_model === 'child_support_advance_expense' ? <>
            <div className="assumption-key-values">
              {['advance_monthly_amount', 'advance_months'].map(key => {
                const row = item.calculation?.evidenceVariables?.[key]
                return row && <div key={key}><span>{key === 'advance_monthly_amount' ? '월 지원금' : '연간 지원 기간'}</span><strong>{displayValue(row.value, row.unit)}</strong></div>
              })}
              <div><span>추계기간</span><strong>{item.startYear}~{item.startYear + 4}년</strong></div>
            </div>
            <p>지원 대상 전원이 신청한다고 가정해요. 대상자 수는 통계로 추정하고, 기존 사업 예산은 빼서 계산해요.</p>
            <small className="assumption-disclaimer">유사 사례를 참고한 가정이에요. 실제 지급 기준과 시행연도는 달라질 수 있어요.</small>
          </> : <p>{item.assumptionNotice}</p>}
          <details><summary>근거와 적용 이유 보기</summary>
            <p>{item.assumptionNotice}</p>
            <p>{Object.values(item.engineContext?.evidence_selection_reasons || {})[0]}</p>
            <p>{displaySources(item.calculation?.sourceRefs || [])}</p>
            <p>자료 조회 기준: {item.evidenceCutoff} · 자기 의안의 정답 제외</p>
          </details>
          <button className="assumption-continue" type="button" onClick={() => setConfirmedAssumptions(previous => ({ ...previous, [item.itemIndex]: true }))}>확인하고 계속하기 <span aria-hidden="true">→</span></button>
        </div>)}
      {items.filter(item => item.calculation?.status === 'needs_review').map(item =>
        <div className="chat-citation-review" key={item.itemIndex}>
          <span className="chat-eyebrow">근거 조문 확인</span>
          <strong>계산에 사용할 조문을 다시 확인해 주세요</strong>
          <p>{item.calculation.reason}</p>
          {(item.citationRecoveryCandidates || []).map(candidate => <div className="chat-citation-option" key={`${candidate.sourcePage}:${candidate.articleRef}`}>
            <strong>{candidate.articleRef} · 의안 PDF {candidate.sourcePage}쪽</strong>
            <p>업로드한 원문에서 찾은 선지급 신청 조문이에요. 이 조문이 계산하려는 내용인지 확인해 주세요.</p>
            <details><summary>원문 보기</summary><blockquote>{candidate.sourceQuote.replace(/\s+/g, ' ')}</blockquote></details>
            <button className="chat-variable-select" type="button" onClick={() => acceptCitation(item, candidate)}>이 조문으로 이어가기</button>
          </div>)}
          {onRetryAnalysis && <button className="chat-manual-choice" type="button" onClick={onRetryAnalysis}>PDF 다시 분석하기</button>}
        </div>)}

      {computed.length > 0 && <div className="chat-result-list">
        {computed.map(item => {
          const output = calculations[item.itemIndex] || item.calculation
          return <div className="chat-result" key={item.itemIndex}>
            <span className="chat-check">✓</span>
            <div><strong>{item.name || '비용 항목'} 계산 초안</strong><p className="chat-result-total">{output.annualAmountsThousand.length}년 합계 {displayValue(output.annualAmountsThousand.reduce((sum, value) => sum + value, 0) * 1000, 'KRW')}</p>
              <details><summary>연도별 금액과 근거 보기</summary><p>{formatAnnual(output.annualAmountsThousand)}</p><p>{item.formula}</p><p>{displaySources(output.sourceRefs || []) || '입력된 값과 의안 원문을 사용했습니다.'}</p></details>
            </div>
          </div>
        })}
      </div>}

      {current && <>
        <div className="chat-section-divider"><span>추계를 위해 확인할 내용</span></div>
        <div className="chat-bubble assistant question">
          <span className="chat-eyebrow">{current.item.name || '비용 항목'} · {finished + 1}번째 확인</span>
          <strong>{LABELS[current.variable] || current.variable}을 알 수 있을까요?</strong>
          <p>의안에서 확정할 수 없어 비워뒀어요. 모르면 건너뛰어도 됩니다. 임의의 숫자는 넣지 않을게요.</p>
        </div>
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
        <form ref={inputFormRef} className="chat-compose" onSubmit={submit}>
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

      {!current && !allComputed && !items.some(item => item.assumptionConfirmationRequired && !confirmedAssumptions[item.itemIndex]) && <div className="chat-bubble assistant question">
        <strong>{reviewBlocked ? '원문을 확인하면 이어서 계산할 수 있어요.' : '지금 확인할 질문은 여기까지예요.'}</strong>
        <p>{reviewBlocked ? '아직 금액을 계산하지 않았어요. 위에서 근거 조문을 선택하거나 PDF를 다시 분석해 주세요.' : questions.some(question => skipped[question.id])
          ? '모르는 값은 비워뒀어요. 해당 항목의 금액은 확정하지 않았습니다.'
          : '계산된 금액은 검토용 초안입니다. 적용 범위와 근거를 확인해 주세요.'}</p>
      </div>}
      {(erce.unmappedArticles || []).length > 0 && <div className="chat-note">산식을 확정하지 못한 조문 {erce.unmappedArticles.length}개는 계산에서 제외했어요.</div>}
      {(erce.deferredItems || []).length > 0 && <details className="chat-context-note">
        <summary>추계와 함께 참고할 내용이 있어요</summary>
        <p>아래 내용은 별도 금액으로 더하지 않았어요. 기존 비용과의 관계나 추가 확인이 필요한 이유를 살펴볼 수 있어요.</p>
        {erce.deferredItems.map((row, index) => <div className="chat-context-item" key={`${row.itemIndex ?? index}:${row.name}`}>
          <strong>{row.name || '참고 내용'}</strong>
          <span>{({ no_incremental_cost: '추가 비용 없음으로 판단한 내용', needs_review: '계산 방법을 확인할 내용',
            defer: '적용 조건을 더 확인할 내용', not_estimated: '금액을 추계하지 않은 내용',
            out_of_scope: '추계 범위에 포함하지 않은 내용' })[row.decision] || '계산 시 참고할 내용'}</span>
          <p>{row.reason || '이 내용의 비용 발생 여부와 계산 조건은 추가 확인이 필요해요.'}</p>
        </div>)}
      </details>}
      {(erce.deferredItems || []).some(row => row.decision === 'needs_review') && <p className="chat-note">계산 방법을 확인해야 하는 내용도 있어요. 위 참고사항에서 이유를 확인해 주세요.</p>}
      {(erce.reviewCandidates || []).length > 0 && <div className="chat-note">추가 비용 가능성 {(erce.reviewCandidates || []).length}건은 아직 금액에 포함하지 않았어요.</div>}
      {additionalQuestionCount > 0 && <div className="chat-note">다른 확인값 {additionalQuestionCount}개는 우선 질문에서 제외했어요. 필요한 경우 이어서 검토할 수 있어요.</div>}
      {additionalQuestionCount > 0 && !current && <button className="chat-revisit" type="button" onClick={() => setShowAdditional(true)}>나머지 항목도 검토하기</button>}
      {Object.keys(skipped).length > 0 && <button className="chat-revisit" type="button" onClick={() => setSkipped({})}>건너뛴 질문 다시 보기</button>}
      {items.length > 0 && <div className="chat-bubble assistant">
        <strong>{allComputed ? '추계가 끝났어요.' : '비용추계서 만들기'}</strong>
        <p>{allComputed ? '확인한 값과 근거를 비용추계서로 정리할 수 있어요.'
          : reviewBlocked ? '먼저 위에서 계산에 사용할 근거 조문을 확인해 주세요.'
          : '위에서 필요한 값과 계산 기준을 확인하면 생성 버튼이 활성화돼요.'}</p>
        {allComputed && <label>추계 시작연도 <input className="chat-report-year" aria-label="초안 추계 시작연도"
          type="number" min="1900" max="2200" value={reportStartYear || (chosenStartYear || '')}
          onChange={event => { setReportStartYear(event.target.value); setDraftRequested(false) }} placeholder="예: 2026" /></label>}
        <button className="chat-generate" type="button" disabled={!allComputed || draftRunning || !Number.isInteger(chosenStartYear) || chosenStartYear < 1900 || chosenStartYear > 2200}
          onClick={() => { setDraftRequested(true); setDraftRetry(value => value + 1) }}>{draftRunning ? '비용추계서를 정리하고 있어요…' : draft ? '비용추계서 다시 생성하기' : '비용추계서 생성하기'}</button>
        {draft && <button className="chat-manual-choice" type="button" disabled={pdfDownloading} onClick={downloadPdf}>{pdfDownloading ? 'PDF를 만들고 있어요…' : 'PDF 내려받기'}</button>}
        {draftRunning && <p role="status">확인한 값으로 다시 계산하고 초안을 정리하고 있어요.</p>}
        {draftError && <><p className="chat-error" role="alert">{draftError}</p><button className="chat-revisit" type="button" onClick={() => setDraftRetry(value => value + 1)}>다시 만들기</button></>}
      </div>}
      {draft && <article className="chat-draft" aria-label="비용추계서 초안">
        <span className="chat-eyebrow">검토용 · 공식 비용추계서가 아닙니다</span>
        <h3>{draft.title}</h3><p className="chat-report-subtitle">비용추계서</p>
        <div className="chat-report-meta"><span>의안번호 {erce.billNo || '확인 필요'}</span><span>{draft.startYear}~{draft.startYear + draft.years - 1}년</span></div>
        <h4>Ⅰ. 비용추계 결과</h4><p>{draft.summary}</p>
        <small>단위: 백만원 · 반올림으로 합계에 차이가 있을 수 있습니다</small>
        <div className="chat-draft-table"><table><thead><tr><th>항목</th>
          {Array.from({ length: draft.years }, (_, i) => <th key={i}>{draft.startYear + i}</th>)}<th>합계</th><th>연평균</th>
        </tr></thead><tbody>
          {draft.items.map((item, index) => <tr key={index}><th>{item.name}</th>
            {item.annualAmountsThousand.map((value, i) => <td key={i}>{Math.round(value / 1000).toLocaleString()}</td>)}
            <td>{Math.round(item.annualAmountsThousand.reduce((sum, value) => sum + value, 0) / 1000).toLocaleString()}</td>
            <td>{Math.round(item.annualAmountsThousand.reduce((sum, value) => sum + value, 0) / draft.years / 1000).toLocaleString()}</td></tr>)}
          <tr><th>합계</th>{draft.annualAmountsThousand.map((value, i) => <td key={i}>{Math.round(value / 1000).toLocaleString()}</td>)}<td>{Math.round(draft.totalAmountThousand / 1000).toLocaleString()}</td><td>{Math.round(draft.totalAmountThousand / draft.years / 1000).toLocaleString()}</td></tr>
        </tbody></table></div>
        <h4>Ⅱ. 재정수반요인</h4>
        {draft.items.map((item, index) => <p key={index}>{item.triggerRef || '조문 확인 필요'} · {item.name}</p>)}
        <h4>Ⅲ. 추계의 전제와 상세내역</h4>
        {draft.items.map((item, index) => <section className="report-cost-section" key={index}><strong>{item.name}</strong>
          <p className="report-formula">{item.derivationTrace?.some(step => step.advance_cases != null)
            ? '추정 지원 건수 × 월 지원금 × 지원 개월 − 기존 사업 예산'
            : item.derivationTrace?.[0]?.expression || item.formula}</p>
          {item.documentAssumptions?.length ? item.documentAssumptions.map((note, noteIndex) => <p className="report-assumption-note" key={noteIndex}>{note}</p>) : item.referenceNotice && <p className="report-assumption-note">유사 자료를 참고한 가정입니다. 실제 지급 기준·대상·시행연도는 별도 확인이 필요합니다.</p>}
          {item.derivationTrace?.some(step => step.advance_cases != null) && <div className="chat-draft-table"><small>금액: 백만원 · 선지급 건수: 건</small><table>
            <thead><tr><th>연도</th><th>추정 선지급 건수</th><th>급여 지출</th><th>기존 예산 차감</th><th>추가 소요</th></tr></thead>
            <tbody>{item.derivationTrace.map(step => <tr key={step.year}><th>{step.year}</th><td>{step.advance_cases.toLocaleString()}</td>
              <td>{Math.round(step.gross_expense / 1000000).toLocaleString()}</td><td>{Math.round(step.legacy_budget / 1000000).toLocaleString()}</td>
              <td>{Math.round(step.additional_expense / 1000000).toLocaleString()}</td></tr>)}</tbody></table></div>}
          <ErceEvidence item={item} startYear={draft.startYear} labels={LABELS} />
        </section>)}
        <h4>Ⅳ. 부대의견 및 검토사항</h4>
        <p>사용자 입력과 선례 가정의 적용 조건, 중복 지원 및 비용 항목의 누락 여부를 검토해 주세요. 입력하지 않은 선택 변수에는 산식 기본값이 적용됩니다.</p>
        {draft.exclusions.map((text, index) => <p className="chat-note" key={index}>미산출·검토 보류: {text}</p>)}
        <div className="chat-report-actions"><button className="chat-generate" type="button" disabled={pdfDownloading} onClick={downloadPdf}>{pdfDownloading ? 'PDF를 만들고 있어요…' : 'PDF 내려받기'}</button>
          <button className="chat-revisit" type="button" onClick={downloadDraft}>초안 내려받기 (.md)</button></div>
        {pdfError && <p className="chat-error" role="alert">{pdfError}</p>}
      </article>}
    </section>
    {current && <aside className="chat-variable-panel" aria-label="변수 참고 후보">
      <span className="chat-eyebrow">지금 확인하는 값</span>
      <h3>{LABELS[current.variable] || '필요한 변수'}</h3>
      <p className="chat-panel-description">같은 변수의 참고 후보예요. 대상과 규모가 맞는지 확인하고 선택해 주세요.</p>
      {candidates.length ? candidates.map(candidate => <div className="chat-variable-card" key={candidate.id}>
        <span className="chat-variable-kind">{candidate.sourceClass === 'official_standard' ? '공식 기준' : '유사 사례 · 가정 후보'}</span>
        <strong>{formatReferenceValue(candidate)}</strong>
        {candidate.availableAt && <small>자료 공개·확보일 {candidate.availableAt}</small>}
        {candidate.scope && <p>{candidate.scope}</p>}
        {candidate.note && <p>{candidate.note}</p>}
        <details><summary>근거 확인</summary><p>{displaySources(candidate.source) || '근거를 추가로 확인해 주세요.'}</p>
          {typeof candidate.value === 'object' && <pre>{JSON.stringify(candidate.value, null, 2)}</pre>}</details>
        <button className="chat-variable-select" type="button" disabled={running}
          onClick={() => saveAnswer(candidate.value, candidate.source, candidate)}>이 값 선택하기</button>
      </div>) : <div className="chat-variable-empty">현재 적용할 만한 후보를 찾지 못했어요. 직접 입력하거나 건너뛸 수 있어요.</div>}
      <button className="chat-manual-choice" type="button" disabled={running} onClick={focusManualInput}>직접 입력하기</button>
      <small className="chat-panel-footer">선택한 값은 근거와 함께 초안에 남겨요. 후보값이 정답이라는 뜻은 아니에요.</small>
    </aside>}
    </div>
  )
}
