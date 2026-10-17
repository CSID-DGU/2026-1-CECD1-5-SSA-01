import { useEffect, useState } from 'react'
import { API, GRADE, plainValue, won } from './util.js'

export function ValueView({ value, unit }) {
  const flat = plainValue(value, unit)
  if (flat !== null) return <span className="nb-value">{flat}</span>
  return (
    <table className="nb-mini-table">
      <tbody>
        {Object.entries(value).map(([k, v]) => (
          <tr key={k}>
            <th>{k}</th>
            <td>{typeof v === 'number' ? (Math.abs(v) < 1 && v !== 0 ? `${+(v * 100).toFixed(2)}%` : v.toLocaleString()) : String(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function CountUp({ value }) {
  const [shown, setShown] = useState(0)
  useEffect(() => {
    let frame
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / 1100)
      setShown(value * (1 - Math.pow(1 - t, 3)))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    const done = setTimeout(() => setShown(value), 1300)
    return () => { cancelAnimationFrame(frame); clearTimeout(done) }
  }, [value])
  return <>{won(shown)}</>
}

export function GradeBadge({ gradeKey, children }) {
  return <span className={`nb-badge g-${gradeKey}`}>{children ?? GRADE[gradeKey]?.label}</span>
}

export function SourceDrawer({ source, cutoff, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  if (!source) return null
  return (
    <div className="nb-drawer-backdrop" onClick={onClose}>
      <aside className="nb-drawer" onClick={(e) => e.stopPropagation()} aria-label="출처 상세">
        <button className="nb-close" onClick={onClose} aria-label="닫기">×</button>
        <GradeBadge gradeKey={source.grade_key}>{source.grade}</GradeBadge>
        <h3>{source.name}</h3>
        <div className="nb-drawer-value"><ValueView value={source.value} unit={source.unit} /></div>
        <dl className="nb-facts">
          <dt>어디서</dt>
          <dd>{source.origin}</dd>
          {source.as_of && (<><dt>기준시점</dt><dd>{String(source.as_of)}</dd></>)}
          <dt>공개일</dt>
          <dd>
            {source.published_at || source.published_label || '확인 필요'}
            {source.before_cutoff === true && <span className="nb-ok"> ✓ 발의일({cutoff}) 이전 공개</span>}
            {source.before_cutoff === false && <span className="nb-warn"> ⚠ 발의일 이후 자료</span>}
          </dd>
        </dl>
        {source.quote && (
          <blockquote className="nb-quote">“{source.quote}”</blockquote>
        )}
        {source.why && (<p className="nb-why"><b>왜 이 값인가</b> {source.why}</p>)}
        {source.note && (<p className="nb-note">⚠ {source.note}</p>)}
        {source.url && (
          <a className="nb-link" href={source.url} target="_blank" rel="noreferrer">원자료 열기 ↗</a>
        )}
      </aside>
    </div>
  )
}

export function Timeline({ sources, cutoff, onPick }) {
  const dated = sources.filter((s) => s.published_at && s.grade_key !== 'bill')
  if (!dated.length) return null
  const times = dated.map((s) => Date.parse(s.published_at)).concat(Date.parse(cutoff))
  const min = Math.min(...times)
  const span = Math.max(1, Math.max(...times) - min)
  const x = (d) => 3 + ((Date.parse(d) - min) / span) * 72
  const sorted = [...dated].sort((a, b) => a.published_at.localeCompare(b.published_at))
  return (
    <div className="nb-timeline">
      <div className="nb-tl-axis" />
      <div className="nb-tl-cutoff" style={{ left: `${x(cutoff)}%` }}>
        <span>발의일 {cutoff}</span>
      </div>
      {sorted.map((s, i) => (
        <button
          key={s.id}
          className={`nb-tl-dot g-${s.grade_key}`}
          style={{ left: `${x(s.published_at)}%`, top: `${10 + (i % 4) * 26}px` }}
          onClick={() => onPick(s)}
          title={`${s.name} · 공개 ${s.published_at}`}
        >
          <i />
          <span>{s.name.replace(' 대상자 수', '')} <em>{s.published_at.slice(0, 7)}</em></span>
        </button>
      ))}
      <div className="nb-tl-zone" style={{ left: `${x(cutoff)}%` }}>이후 자료 사용 금지</div>
    </div>
  )
}

export function ResultBars({ rows }) {
  const max = Math.max(...rows.map((r) => r.value || 0))
  return (
    <div className="nb-bars">
      {rows.map((r) => (
        <div className={`nb-bar-row ${r.cls}`} key={r.label}>
          <div className="nb-bar-label">{r.label}</div>
          <div className="nb-bar-track">
            <div className="nb-bar-fill" style={{ width: r.value ? `${(r.value / max) * 100}%` : '0%' }} />
            <span className="nb-bar-text">{r.value ? won(r.value) : r.empty}</span>
          </div>
          <div className="nb-bar-err">{r.err}</div>
        </div>
      ))}
    </div>
  )
}

function WebHits({ hits, searches, onAdd, added }) {
  return (
    <div className="lg-web">
      <h4>웹에서 찾은 자료 {hits.length}건 <small>코드가 원문 페이지를 직접 열어 숫자를 확인했어요</small></h4>
      {searches?.length > 0 && <p className="nb-muted">AI 검색어: {searches.map((q) => <span key={q} className="ai-q">{q}</span>)}</p>}
      {hits.length === 0 && <p>웹에서도 조건에 맞는 공식 자료를 찾지 못했어요.</p>}
      {hits.map((h) => (
        <div key={h.url + h.name} className={`lg-row ${h.verified ? (h.official ? 'g-official' : 'g-precedent') : 'g-missing'}`}>
          <div className="lg-main">
            <b>{h.name}</b>
            <span className="lg-val">{h.value.toLocaleString()} {h.unit}</span>
          </div>
          <p className="lg-src">
            <span className={`nb-badge ${h.official ? 'g-official' : 'g-precedent'}`}>{h.official ? '공식 기관' : '언론·기타'}</span>
            {[`${h.publisher} 「${h.document}」`, h.as_of && `${h.as_of} 기준`, `공개 ${h.published_at}`].filter(Boolean).join(' · ')}
          </p>
          <blockquote className="nb-quote">“{h.quote}”</blockquote>
          <p className={h.verified ? 'nb-ok' : 'nb-warn'}>{h.verified ? '✓' : '⚠'} {h.verify_note}</p>
          <div className="lg-actions">
            <a className="nb-link" href={h.url} target="_blank" rel="noreferrer">원문 열기 ↗</a>
            {added[h.url + h.name]
              ? <span className="nb-ok">✓ 원장에 추가됨</span>
              : <button className="sv-btn primary" disabled={!h.verified} title={h.verified ? '' : '원문에서 숫자가 확인된 자료만 추가할 수 있어요'} onClick={() => onAdd(h)}>원장에 추가</button>}
          </div>
        </div>
      ))}
    </div>
  )
}

export function LedgerSearch({ cutoff }) {
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [web, setWeb] = useState(null)
  const [busy, setBusy] = useState('')
  const [open, setOpen] = useState(null)
  const [added, setAdded] = useState({})
  const [error, setError] = useState('')
  const post = (path, body) => fetch(`${API}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((r) => r.json())

  const webSearch = async () => {
    setBusy('web')
    try {
      const d = await post('/api/nabo/ledger/web', { q, cutoff })
      if (d.error) throw new Error(d.error)
      setWeb(d)
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setBusy('')
    }
  }

  const go = async (mode) => {
    setError('')
    setWeb(null)
    setBusy(mode)
    try {
      let d = mode === 'ai' ? await post('/api/nabo/ledger/ai', { q, cutoff })
        : await fetch(`${API}/api/nabo/ledger?q=${encodeURIComponent(q)}&cutoff=${cutoff}`).then((r) => r.json())
      if (d.error) throw new Error(d.error)
      let used = mode
      if (mode === 'basic' && d.rows.length === 0) {
        setBusy('ai')
        d = await post('/api/nabo/ledger/ai', { q, cutoff })
        used = 'ai'
      }
      setData({ ...d, mode: used })
      setBusy('')
      if (d.rows.length === 0) await webSearch()
    } catch (e) {
      setError(String(e.message || e))
      setBusy('')
    }
  }

  const add = async (h) => {
    try {
      const d = await post('/api/nabo/ledger/add', { hit: h })
      if (d.error) throw new Error(d.error)
      setAdded({ ...added, [h.url + h.name]: true })
      setData((cur) => ({ ...(cur ?? { total: 0, how: null, mode: 'basic' }), rows: [d.row, ...(cur?.rows ?? [])] }))
    } catch (e) {
      setError(String(e.message || e))
    }
  }

  const how = data?.how
  const label = { basic: '찾는 중…', ai: 'AI가 검색어를 바꿔 찾는 중…', web: 'AI가 웹에서 찾고, 코드가 원문을 확인하는 중… (30초~1분)' }[busy]
  return (
    <section className="nb-section">
      <form className="nb-search" onSubmit={(e) => { e.preventDefault(); go('basic') }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="평소 말로 검색하세요 — 예: 우리나라 인구, 노인 인구, 최저시급, 청년 농업인 수" />
        <button disabled={!!busy || !q.trim()}>검색</button>
      </form>
      <p className="nb-muted">{cutoff} 이전에 공개된 자료만 보여줘요. 원장에 없으면 AI가 검색어를 바꿔 다시 찾고, 그래도 없으면 웹에서 찾아요.</p>
      {data && data.rows.length > 0 && !web && !busy && (
        <p className="lg-more-link">찾는 자료가 아닌가요? <button type="button" onClick={webSearch}>웹에서 더 찾기</button></p>
      )}
      {busy && <p className="lg-busy"><span className="ai-spinner small" />{label}</p>}
      {error && <p className="nb-error">{error}</p>}
      {data && (
        <div className="nb-ledger">
          {how && (how.core?.length || how.extra?.length) ? (
            <p className="lg-how">
              {data.mode === 'ai' ? 'AI가 이렇게 바꿔 찾았어요: ' : '이렇게 찾았어요: '}
              {[...(how.core ?? []), ...(how.extra ?? [])].map((w) => <span key={w} className="ai-q">{w}</span>)}
              {how.why && <small>{how.why}</small>}
            </p>
          ) : null}
          <p className="nb-muted">원장 전체 {data.total.toLocaleString()}행 중 {data.rows.length}건</p>
          {data.rows.map((r) => (
            <div className={`lg-row g-${r.grade_key}`} key={r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>
              <div className="lg-main">
                <b>{r.name}</b>
                <span className="lg-val"><ValueView value={r.value} unit={r.unit} /></span>
              </div>
              <p className="lg-src">
                <GradeBadge gradeKey={r.grade_key}>{r.grade}</GradeBadge>
                {[r.where, r.as_of_ko && `${r.as_of_ko} 기준`, `공개 ${r.published_at}`].filter(Boolean).join(' · ')}
              </p>
              {open === r.id && (
                <div className="lg-more">
                  <p>{r.provenance}</p>
                  {r.quote && <blockquote className="nb-quote">“{r.quote}”</blockquote>}
                  {r.note && <p className="nb-note">⚠ {r.note}</p>}
                  {r.url && <a className="nb-link" href={r.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>원자료 열기 ↗</a>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {web && <WebHits hits={web.hits} searches={web.how?.searches} onAdd={add} added={added} />}
    </section>
  )
}
