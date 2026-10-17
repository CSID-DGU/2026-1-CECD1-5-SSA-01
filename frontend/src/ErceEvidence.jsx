import { displayValue, displaySources, EVIDENCE_LABELS, evidenceRows, evidenceSources } from './erceDisplay'

const MAIN_INPUTS = new Set(['advance_monthly_amount', 'advance_months', 'legacy_support_budget'])

export default function ErceEvidence({ item, startYear, labels }) {
  const rows = evidenceRows(item)
  const primary = rows.filter(([key, row]) => MAIN_INPUTS.has(key) && typeof row.value === 'number')
  const detail = rows.filter(([key]) => !primary.some(([primaryKey]) => primaryKey === key))
  const name = key => EVIDENCE_LABELS[key] || labels[key] || '참고 항목'
  const sources = evidenceSources(item)
  const renderRow = ([key, row]) => {
    if (row.value !== null && typeof row.value === 'object') {
      const entries = Array.isArray(row.value)
        ? row.value.map((value, index) => [startYear ? `${startYear + index}년` : `${index + 1}년차`, value])
        : Object.entries(row.value).map(([key, value], index) => [/^\d{4}$/.test(key) ? `${key}년` : labels[key] || `항목 ${index + 1}`, value])
      return <div className="evidence-series" key={key}><strong>{name(key)}</strong>
        <div className="chat-draft-table"><table><thead><tr><th>구분</th><th>값</th></tr></thead>
          <tbody>{entries.map(([label, value]) => <tr key={label}><th>{label}</th><td>{typeof value === 'object' ? '상세 구성 확인 필요' : displayValue(value, row.unit)}</td></tr>)}</tbody></table></div>
      </div>
    }
    return <div className="evidence-value-row" key={key}><dt>{name(key)}</dt><dd>{displayValue(row.value, row.unit)}</dd></div>
  }
  return <div className="evidence-summary">
    {primary.length > 0 && <dl className="evidence-main-values">{primary.map(renderRow)}</dl>}
    {detail.length > 0 && <details className="evidence-more"><summary>대상자 산정과 세부값 보기</summary>
      <p className="evidence-helper">비율과 전망값을 조합해 대상자를 추정했어요.</p>
      <dl>{detail.filter(([, row]) => row.value === null || typeof row.value !== 'object').map(renderRow)}</dl>
      {detail.filter(([, row]) => row.value !== null && typeof row.value === 'object').map(renderRow)}
    </details>}
    {sources.length > 0 && <details className="evidence-more"><summary>근거 자료 보기</summary>
      <p className="evidence-source">{displaySources(sources)}</p>
      {item.referenceNotice && <p className="evidence-source">{item.referenceNotice}</p>}
      {(item.selectedMethods || []).map(method => <p className="evidence-source" key={method.method_key}>{method.applicability_reason}</p>)}
    </details>}
  </div>
}
