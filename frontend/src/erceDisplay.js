export const EVIDENCE_LABELS = {
  household_forecast: '가구 수 전망', minor_single_parent_share: '미성년 자녀 한부모 비율',
  divorced_unmarried_share: '이혼·미혼 비율', claim_holder_share: '양육비 채권 보유 비율',
  unpaid_claim_share: '양육비 미지급 비율', children_per_claim: '평균 자녀 수',
  advance_monthly_amount: '월 지원금', advance_months: '연간 지원 기간',
  legacy_support_budget: '기존 사업 예산', annual_amount: '연간 비용',
}

export function displayValue(value, unit = '') {
  if (value == null) return '확인 필요'
  if (typeof value !== 'number') return String(value)
  if (unit.startsWith('ratio')) return `${Number((value * 100).toFixed(4)).toLocaleString('ko-KR')}%`
  if (unit.startsWith('KRW')) {
    const absolute = Math.abs(value)
    const sign = value < 0 ? '−' : ''
    if (absolute >= 100000000 && absolute % 10000 === 0) {
      const billions = Math.floor(absolute / 100000000)
      const remainder = (absolute % 100000000) / 10000
      return `${sign}${billions.toLocaleString('ko-KR')}억${remainder ? ` ${remainder.toLocaleString('ko-KR')}만` : ''}원`
    }
    if (absolute >= 10000 && absolute % 10000 === 0) return `${sign}${(absolute / 10000).toLocaleString('ko-KR')}만원`
    return `${value.toLocaleString('ko-KR')}원`
  }
  const suffix = ({ household: '가구', person: '명', 'person/household': '명',
    'month/year': '개월', month: '개월', year: '년', count: '건' })[unit] || ''
  return `${value.toLocaleString('ko-KR')}${suffix}`
}

export function evidenceRows(item) {
  return Object.entries({ ...item.resolvedVariables, ...item.evidenceVariables })
    .filter(([key]) => !(key === 'annual_amount' && item.derivationTrace?.some(step => step.additional_expense != null)))
}

export function evidenceSources(item) {
  const sources = [...new Set([
    ...evidenceRows(item).map(([, row]) => row.source_ref),
    ...(item.selectedMethods || []).map(method => method.source_ref),
  ].filter(Boolean))]
  return sources.filter(source => !sources.some(other => other !== source && other.includes(source)))
}

export function displaySources(values) {
  const sources = Array.isArray(values) ? values : [values]
  const labels = sources.filter(Boolean).flatMap(source => {
    const bills = [...new Set(String(source).match(/22\d{5}/g) || [])]
    return bills.length ? bills.map(number => `의안 ${number}`) : [String(source)]
  })
  return [...new Set(labels)].join(' · ')
}
