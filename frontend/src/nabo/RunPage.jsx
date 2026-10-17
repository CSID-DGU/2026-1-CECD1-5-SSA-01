import { useEffect, useState } from 'react'
import { Pipeline } from './Pipeline.jsx'
import { Clauses, Compare, Dates, EvidenceTable, Formula, YearTable } from './sections.jsx'
import { API, pct, won } from './util.js'

function NeedsInput({ needs, onSubmit, busy }) {
  const [vals, setVals] = useState({})
  if (!needs?.length) return null
  const set = (name, key, v) => setVals({ ...vals, [name]: { ...vals[name], [key]: v } })
  return (
    <div className="sv-card sv-needs">
      <h3>근거를 찾지 못한 값 {needs.length}개</h3>
      <p className="nb-muted">값과 출처를 넣으면 다시 계산해요. AI를 다시 호출하지 않고, 출처에는 “사용자 입력”으로 남아요.</p>
      {needs.map((n) => (
        <div key={n.name} className="ai-need">
          <div><b>{n.name}</b><p className="nb-muted">{n.who}</p><p className="nb-note">{n.reason}</p></div>
          <input type="number" placeholder="인원(명)" value={vals[n.name]?.value ?? ''} onChange={(e) => set(n.name, 'value', e.target.value)} />
          <input placeholder="출처 (기관 · 자료명 · 기준시점)" value={vals[n.name]?.source ?? ''} onChange={(e) => set(n.name, 'source', e.target.value)} />
        </div>
      ))}
      <button className="sv-btn primary" disabled={busy} onClick={() => onSubmit(vals)}>{busy ? '계산 중…' : '이 값으로 다시 계산'}</button>
    </div>
  )
}

function Review({ data }) {
  const items = [
    ...data.ai.checks.filter((c) => !c.ok).map((c) => `${c.item}: ${c.text}`),
    ...data.sources.filter((s) => ['assumption', 'missing'].includes(s.grade_key)).map((s) => `${s.name}: ‘${s.grade}’ 근거 — 원 통계로 대체 검토`),
  ]
  return (
    <div className="sv-card">
      <h3>검토 필요 사항</h3>
      {items.length ? <ul className="sv-plain">{items.map((t) => <li key={t}>{t}</li>)}</ul>
        : <p className="nb-ok">자동 검증에서 확인이 필요한 항목이 없어요.</p>}
    </div>
  )
}

const TABS = [
  ['summary', '요약'],
  ['evidence', '산식 · 근거'],
  ['clauses', '조문'],
  ['process', '처리 과정'],
  ['compare', '공식 추계 대조'],
]

export default function RunPage({ runId, onPick }) {
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('summary')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    fetch(`${API}/api/nabo/ai/run/${runId}`).then((r) => r.json())
      .then((d) => { if (live) (d.error ? setError(d.error) : setState(d)) })
      .catch(() => live && setError('결과를 불러오지 못했어요.'))
    return () => { live = false }
  }, [runId])

  if (error) return <p className="nb-error">{error}</p>
  if (!state) return <p className="nb-loading">불러오는 중…</p>
  const data = state.case
  const pick = (s) => onPick(s && { ...s, cutoff: data.cutoff })
  const pdf = `${API}/api/nabo/ai/pdf/${runId}`
  const report = `${API}/api/nabo/ai/report/${runId}`
  const scen = Object.entries(data.scenarios)
  const main = scen[0][1]
  const years = Object.keys(main.by_year).sort()
  const upper = data.scenarios['상한']
  const needs = data.ai.needs_input?.length ?? 0
  const tabs = TABS.filter(([k]) => k !== 'compare' || data.answer)

  const recompute = async (vals) => {
    setBusy(true)
    try {
      const res = await fetch(`${API}/api/nabo/ai/recompute`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId, overrides: vals }) })
      const c = await res.json()
      if (c.error) throw new Error(c.error)
      setState({ ...state, case: c })
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sv-page">
      <div className="sv-head">
        <div>
          <p className="sv-crumb"><a href="#/runs">추계 내역</a> › {data.bill.no}</p>
          <h1>{data.bill.title}</h1>
          <p className="nb-muted">{[data.bill.proposer, `의안번호 ${data.bill.no}`, `발의 ${data.bill.propose_date}`, data.bill.committee].filter(Boolean).join(' · ')}</p>
        </div>
        <div className="sv-actions">
          <span className={`sv-status ${needs ? 'warn' : 'ok'}`}>{needs ? `입력 필요 ${needs}` : '추계 완료'}</span>
          <a className="sv-btn" href={pdf} target="_blank" rel="noreferrer">의안 원문</a>
          <a className="sv-btn" href={`${report}?format=doc`}>Word 받기</a>
          <a className="sv-btn primary" href={report} target="_blank" rel="noreferrer">비용추계서 초안</a>
        </div>
      </div>

      <div className="sv-kpis">
        <div className="sv-kpi main">
          <span>추가재정소요{scen.length > 1 ? ` (${scen[0][0]})` : ''}</span>
          <b>{won(main.total)}</b>
          {upper && <small>상한 {won(upper.total)}</small>}
        </div>
        {main.local > 0 && <div className="sv-kpi"><span>국비</span><b>{won(main.national)}</b><small>지방비 {won(main.local)}</small></div>}
        <div className="sv-kpi"><span>추계기간</span><b>{years.length === 1 ? `${years[0]}년` : `${years[0]}~${years[years.length - 1]}`}</b><small>{years.length === 1 ? '단년도' : `${years.length}년 · 연평균 ${won(main.total / years.length)}`}</small></div>
        <div className="sv-kpi"><span>근거</span><b>{data.sources.length}개</b><small>발의일 이전 공개 {data.sources.filter((s) => s.before_cutoff).length}개</small></div>
        {data.answer && <div className="sv-kpi"><span>공식 추계 대비</span><b>{pct(data.answer.error_pct)}</b><small>국회예산정책처 {won(Object.values(data.answer.scenarios)[0])}</small></div>}
      </div>

      <nav className="sv-tabs">
        {tabs.map(([k, label]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{label}</button>
        ))}
      </nav>

      {tab === 'summary' && (
        <div className="sv-grid">
          <div className="sv-card wide">
            <h3>추계 결과</h3>
            <p className="sv-lead">{data.ai.summary}</p>
            <YearTable data={data} />
          </div>
          <div className="sv-card wide">
            <h3>산식</h3>
            <Formula data={data} onPick={pick} />
            {data.ai.payment_years_why && <p className="nb-muted">추계기간 판단: {data.ai.payment_years_why}</p>}
          </div>
          <NeedsInput key={JSON.stringify(data.ai.needs_input)} needs={data.ai.needs_input} onSubmit={recompute} busy={busy} />
          <Review data={data} />
        </div>
      )}
      {tab === 'evidence' && (
        <div className="sv-grid">
          <div className="sv-card wide"><h3>산식 — 숫자를 누르면 출처</h3><Formula data={data} onPick={pick} /></div>
          <div className="sv-card wide"><h3>근거표</h3><EvidenceTable data={data} pdf={pdf} onPick={pick} /></div>
          <div className="sv-card wide"><h3>공개일</h3><Dates data={data} onPick={pick} /></div>
        </div>
      )}
      {tab === 'clauses' && <div className="sv-card"><h3>재정수반 조문 (원문 대조 완료)</h3><Clauses data={data} pdf={pdf} /></div>}
      {tab === 'process' && (
        <div className="sv-card">
          <h3>처리 과정</h3>
          <p className="nb-muted">모델 {data.ai.model} · {state.created} 실행. AI의 판단과 코드 검증 결과를 단계별로 기록해요.</p>
          <Pipeline events={state.events} running={false} />
        </div>
      )}
      {tab === 'compare' && data.answer && <div className="sv-card"><h3>국회예산정책처 추계서와 대조</h3><Compare data={data} /></div>}
    </div>
  )
}
