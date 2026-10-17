import { useEffect, useState } from 'react'
import NewEstimate from './NewEstimate.jsx'
import RunList from './RunList.jsx'
import RunPage from './RunPage.jsx'
import { LedgerSearch, SourceDrawer } from './parts.jsx'
import { STATIC } from './util.js'

function route() {
  const parts = window.location.hash.replace(/^#\/?/, '').split('/')
  return { page: parts[0] || (STATIC ? 'runs' : 'new'), id: parts[1] }
}

const NAV = STATIC ? [['runs', '추계 내역']] : [['new', '새 추계'], ['runs', '추계 내역'], ['ledger', '기준정보 원장']]

function LedgerPage() {
  const [cutoff, setCutoff] = useState(new Date().toISOString().slice(0, 10))
  return (
    <div className="sv-page">
      <div className="sv-head">
        <div>
          <h1>기준정보 원장</h1>
          <p className="nb-muted">추계에 쓰는 인원·단가·비율 자료예요. 기준일을 정하면 그날까지 공개된 자료만 보여줘요.</p>
        </div>
        <label className="sv-date">기준일 <input type="date" value={cutoff} onChange={(e) => setCutoff(e.target.value || cutoff)} /></label>
      </div>
      <LedgerSearch cutoff={cutoff} key={cutoff} />
    </div>
  )
}

export default function App() {
  const [r, setR] = useState(route)
  const [picked, setPicked] = useState(null)
  useEffect(() => {
    const on = () => { setR(route()); setPicked(null); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const active = r.page === 'runs' && r.id ? 'runs' : r.page
  return (
    <div className="sv-app">
      <header className="sv-top">
        <a className="sv-brand" href={STATIC ? '#/runs' : '#/new'}><i>₩</i>법안 비용추계 <span>자동화</span></a>
        <nav>
          {NAV.map(([k, label]) => <a key={k} href={`#/${k}`} className={active === k ? 'on' : ''}>{label}</a>)}
        </nav>
      </header>
      {STATIC && <p className="sv-ro">읽기 전용 기록 보관본 — 새 추계와 재계산은 서비스에서만 할 수 있어요.</p>}
      {r.page === 'new' && !STATIC && <NewEstimate />}
      {r.page === 'runs' && !r.id && <RunList />}
      {r.page === 'runs' && r.id && <RunPage key={r.id} runId={r.id} onPick={setPicked} />}
      {r.page === 'ledger' && !STATIC && <LedgerPage />}
      <SourceDrawer source={picked} cutoff={picked?.cutoff} onClose={() => setPicked(null)} />
    </div>
  )
}
