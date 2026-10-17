// Candidates are references, not automatic assumptions. DB selections retain
// their IDs and units so the server rechecks applicability before calculating.
export function referenceCandidates(item, variable, preferred = null) {
  const rows = (item?.calculation?.referenceCandidates || [])
    .filter(row => row.variableKey === variable && row.value != null && row.evidenceKey)
    .map(row => ({
      id: row.evidenceKey, evidenceKey: row.evidenceKey, value: row.value,
      unit: row.unit, source: row.sourceRef, note: row.limitation,
      scope: row.scope, availableAt: row.availableAt, sourceClass: row.sourceClass,
    }))
  const seen = new Set()
  const unique = rows.filter(row => { if (seen.has(row.id)) return false; seen.add(row.id); return true })
  unique.sort((a, b) => Number(b.sourceClass === 'official_standard') - Number(a.sourceClass === 'official_standard')
    || String(b.availableAt || '').localeCompare(String(a.availableAt || '')))
  if (preferred && !unique.some(row => JSON.stringify(row.value) === JSON.stringify(preferred.value))) {
    unique.unshift({ ...preferred, id: 'derived-reference' })
  }
  return unique.slice(0, 5)
}

export function formatReferenceValue(candidate) {
  if (candidate.label) return candidate.label
  const unit = candidate.unit || ''
  const unitLabel = ({ ratio: '%', person: '명', count: '건', year: '년', month: '개월',
    'KRW': '원', 'KRW/year': '원/년', 'KRW/person/year': '원/명·년',
    'KRW/person': '원/명', 'KRW/person/day': '원/명·일', 'KRW/case': '원/건',
    'KRW/item': '원/개', 'KRW/m2': '원/㎡', 'KRW/meeting': '원/회',
    'KRW/person/month': '원/명·월', 'KRW/plan': '원/회', 'KRW/survey': '원/회' })[unit]
  const display = value => typeof value === 'number'
    ? (unit === 'ratio' ? Number((value * 100).toFixed(4)) : value).toLocaleString('ko-KR') : String(value)
  const value = Array.isArray(candidate.value) ? candidate.value.map(display).join(' · ')
    : typeof candidate.value === 'object' ? '항목별 참고값 보기' : display(candidate.value)
  return `${value}${unitLabel ? ` ${unitLabel}` : ''}`
}

export function selectedEvidenceContext(item, answers) {
  const context = item.engineContext || {}
  const chosen = Object.entries(answers)
    .filter(([id, row]) => id.startsWith(`${item.itemIndex}:`) && row.evidenceKey)
    .map(([, row]) => row)
  return {
    ...context,
    selected_evidence_keys: [...new Set([...(context.selected_evidence_keys || []), ...chosen.map(row => row.evidenceKey)])],
    evidence_selection_reasons: { ...context.evidence_selection_reasons,
      ...Object.fromEntries(chosen.map(row => [row.evidenceKey, `사용자가 적용 범위와 근거를 확인하고 선택한 참고값: ${row.source_ref}`])) },
  }
}
