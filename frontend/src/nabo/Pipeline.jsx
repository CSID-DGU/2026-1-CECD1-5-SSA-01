import { useEffect, useState } from 'react'
import { ValueView } from './parts.jsx'

const STEPS = [
  { key: 'read', title: '문서 읽기', who: '코드', desc: 'PDF 텍스트 · 의안번호 · 발의일(= 자료 사용 기준일)' },
  { key: 'clauses', title: '조문 분석', who: 'AI', desc: '지급대상 · 지급액 · 지급연도 설계 → 코드가 인용·금액을 원문 대조' },
  { key: 'search', title: '기준정보 원장 검색', who: '코드', desc: '발의일 이전 공개 · 이 의안 자신의 정답 제외' },
  { key: 'pick', title: '근거 선택', who: 'AI', desc: '후보 중 조문 범위·기준시점이 맞는 행 선택' },
  { key: 'web', title: '웹 검색 · 원문 확인', who: 'AI + 코드', desc: '원장에 없는 값만 · 코드가 원문을 직접 열어 숫자 확인' },
  { key: 'calc', title: '검증 · 계산', who: '코드', desc: '공개일 · 단위 · 합계 점검 후 산식 계산' },
]

function stepState(events, key) {
  const mine = events.filter((e) => e.step === key)
  if (!mine.length) return { status: 'wait', events: [] }
  return { status: mine[mine.length - 1].status, events: mine, last: mine[mine.length - 1] }
}

function dataOf(state, step) {
  return state.events.findLast((e) => e.step === step && e.data)?.data
}

function StepDetail({ stepKey, state, all }) {
  const d = dataOf(state, stepKey)
  const problems = state.events.find((e) => e.data?.problems)?.data.problems
  if (stepKey === 'clauses' && d?.design) {
    const g = d.design
    return (
      <div className="ai-detail">
        <p>{g.summary}</p>
        {problems?.length > 0 && (
          <div className="ai-retry">
            <b>코드 검증에서 되돌린 답 {problems.length}건</b>
            <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>
          </div>
        )}
        <table className="ai-table">
          <thead><tr><th>대상 그룹</th><th>지급액</th><th>근거 조문</th><th>원장 검색어</th></tr></thead>
          <tbody>
            {g.groups.map((x) => (
              <tr key={x.name}>
                <td><b className={x.sign < 0 ? 'neg' : 'pos'}>{x.sign < 0 ? '− ' : '+ '}{x.name}</b><small>{x.who}</small></td>
                <td>{x.amount_min_won.toLocaleString()}{x.amount_max_won !== x.amount_min_won && ` ~ ${x.amount_max_won.toLocaleString()}`}원{x.times_per_year > 1 && ` × 연 ${x.times_per_year}회`}</td>
                <td>{x.amount_clause_id}</td>
                <td>{x.search_queries.map((q) => <span key={q} className="ai-q">{q}</span>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="nb-muted">지급연도 {g.payment_years.join(', ')} — {g.payment_years_why}</p>
      </div>
    )
  }
  if (stepKey === 'search' && d?.found) {
    const picks = dataOf(stepState(all, 'pick'), 'pick')?.picks?.groups ?? []
    return (
      <div className="ai-detail ai-cands">
        {Object.entries(d.found).map(([name, f]) => {
          const chosen = picks.find((p) => p.name === name)?.ledger_id
          return (
            <div key={name}>
              <h4>{name} <span className="nb-muted">후보 {f.people.length}개</span></h4>
              {f.people.length === 0 && <p className="nb-muted">원장에 이 집단의 자료가 없어요.</p>}
              <ul>
                {f.people.slice(0, 6).map((r) => (
                  <li key={r.id} className={r.id === chosen ? 'chosen' : ''}>
                    {r.id === chosen && <span className="ai-pick">AI 선택</span>}
                    <b>{r.label ?? r.name.replace(/^[a-z0-9_:.]+\s*—\s*/, '')}</b>
                    <span className="ai-cand-val"><ValueView value={r.value} unit={r.unit_ko ?? (r.unit === 'person' ? '명' : r.unit)} /></span>
                    <small>{[r.publisher || r.source.split(' ')[0], r.as_of_ko && `${r.as_of_ko} 기준`, `공개 ${r.published_at}`].filter(Boolean).join(' · ')}</small>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>
    )
  }
  if (stepKey === 'pick' && d?.picks) {
    return (
      <div className="ai-detail">
        <ul className="ai-picks">
          {d.picks.groups.map((p) => (
            <li key={p.name} className={p.ledger_id ? 'ok' : 'empty'}>
              <b>{p.name}</b>
              <code>{p.ledger_id || '선택 안 함 → 웹 검색으로'}</code>
              <p>{p.why}</p>
              {p.caveat && <p className="nb-note">⚠ {p.caveat}</p>}
            </li>
          ))}
          {d.picks.split?.ledger_id && (
            <li className="ok"><b>국가·지자체 분담</b><code>{d.picks.split.ledger_id}</code><p>{d.picks.split.why}</p></li>
          )}
        </ul>
      </div>
    )
  }
  if (stepKey === 'web' && d?.hits) {
    return (
      <div className="ai-detail">
        {problems?.length > 0 && (
          <div className="ai-retry"><b>코드 검증에서 되돌린 답</b><ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul></div>
        )}
        {d.searches?.length > 0 && <p className="nb-muted">AI 검색어: {d.searches.filter(Boolean).map((q) => <span key={q} className="ai-q">{q}</span>)}</p>}
        <ul className="ai-picks">
          {Object.values(d.hits).map((h) => (
            <li key={h.name} className={h.verified ? 'ok' : 'warn'}>
              <b>{h.name}</b>
              <span className="ai-num">{h.value.toLocaleString()} {h.unit}</span>
              <p>{h.publisher} 「{h.document}」 · 기준 {h.as_of} · 공개 {h.published_at}</p>
              {h.quote && <blockquote className="nb-quote">“{h.quote}”</blockquote>}
              <p className={h.verified ? 'nb-ok' : 'nb-warn'}>{h.verified ? '✓ ' : '⚠ '}코드 검증: {h.verify_note}</p>
              <a className="nb-link" href={h.url} target="_blank" rel="noreferrer">원문 열기 ↗</a>
            </li>
          ))}
        </ul>
      </div>
    )
  }
  if (stepKey === 'calc' && d?.checks) {
    return (
      <div className="ai-detail">
        <ul className="nb-checks">
          {d.checks.map((c) => (
            <li key={c.item} className={c.ok ? 'yes' : 'no'}><span>{c.ok ? '✓' : '✗'}</span><b>{c.item}</b>&nbsp;{c.text}</li>
          ))}
        </ul>
      </div>
    )
  }
  return null
}

export function Pipeline({ events, running }) {
  const [elapsed, setElapsed] = useState(0)
  const [open, setOpen] = useState({})
  useEffect(() => {
    if (!running) return undefined
    const t = setInterval(() => setElapsed((v) => v + 1), 1000)
    return () => clearInterval(t)
  }, [running])
  return (
    <ol className="ai-steps">
      {STEPS.map((s, i) => {
        const st = stepState(events, s.key)
        const skipped = s.key === 'web' && st.status === 'wait' && events.some((e) => e.step === 'calc')
        const isOpen = open[s.key] ?? (st.status === 'done' && ['clauses', 'search', 'web', 'calc'].includes(s.key))
        return (
          <li key={s.key} className={`ai-step ${skipped ? 'skip' : st.status}`}>
            <div className="ai-step-head" onClick={() => setOpen({ ...open, [s.key]: !isOpen })}>
              <span className="ai-dot">{st.status === 'done' ? '✓' : st.status === 'error' ? '!' : st.status === 'running' ? '' : skipped ? '–' : i + 1}</span>
              <div>
                <b>{s.title}</b> <span className={`ai-who ${s.who.startsWith('AI') ? 'gpt' : 'code'}`}>{s.who}</span>
                <p>{skipped ? '원장에서 모든 값을 찾아 웹 검색을 건너뜀' : st.last?.text ?? s.desc}</p>
              </div>
              <span className="ai-time">
                {st.status === 'running' && running ? `${elapsed}초` : st.last ? `${st.last.t}s` : ''}
              </span>
            </div>
            {isOpen && st.status !== 'wait' && <StepDetail stepKey={s.key} state={st} all={events} />}
          </li>
        )
      })}
    </ol>
  )
}

const TIPS = [
  'AI는 판단만 해요. 숫자는 법안 원문·원장·코드가 직접 연 웹 원문에서만 와요.',
  '발의일 이후에 공개된 자료는 코드가 자동으로 막아요.',
  'AI가 쓴 인용문이 원문에 글자 그대로 없으면 되돌려 보내 다시 쓰게 해요.',
  '이 의안 자신의 국회예산정책처 추계서 값은 검색 대상에서 빠져요.',
  '웹에서 찾은 숫자는 코드가 그 페이지를 직접 열어 숫자가 있는지 확인해요.',
]

export function Progress({ events, label }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setElapsed((v) => v + 1), 1000)
    return () => clearInterval(t)
  }, [])
  const calcStarted = events.some((e) => e.step === 'calc')
  let score = 0
  let current = STEPS[0]
  for (const s of STEPS) {
    const st = stepState(events, s.key)
    if (st.status === 'done' || (s.key === 'web' && st.status === 'wait' && calcStarted)) score += 1
    else if (st.status === 'running') { score += 0.4; current = s }
  }
  const pctDone = Math.min(99, Math.round((score / STEPS.length) * 100))
  const last = events[events.length - 1]
  return (
    <div className="ai-progress" role="status" aria-live="polite">
      <div className="ai-progress-top">
        <span className="ai-spinner" />
        <div>
          <b>{events.length ? `${current.title} 중` : `${label} 준비 중`}<span className="ai-dots" /></b>
          <p>{last?.text ?? 'PDF를 서버로 보내는 중'}</p>
        </div>
        <span className="ai-progress-num">{pctDone}%<small>{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')} 경과 · 보통 2~4분</small></span>
      </div>
      <div className="ai-bar"><i style={{ width: `${Math.max(4, pctDone)}%` }} /></div>
      <p className="ai-tip">💡 {TIPS[Math.floor(elapsed / 8) % TIPS.length]}</p>
    </div>
  )
}
