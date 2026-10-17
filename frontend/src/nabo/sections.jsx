import { useMemo } from 'react'
import { GradeBadge, ResultBars, Timeline, ValueView } from './parts.jsx'
import { GRADE, pct, plainValue, won } from './util.js'

function useSources(data) {
  return useMemo(() => Object.fromEntries((data?.sources ?? []).map((s) => [s.id, s])), [data])
}

export function Formula({ data, onPick }) {
  const byId = useSources(data)
  const counts = {}
  for (const s of data.sources) counts[s.grade_key] = (counts[s.grade_key] ?? 0) + 1
  return (
    <>
      <div className="nb-formula">
        {data.formula.tokens.map((t, i) => (t.op
          ? <span key={i} className="nb-op">{t.op}</span>
          : (
            <button key={i} className={`nb-chip ${t.source ? `g-${byId[t.source]?.grade_key}` : 'g-plain'}`}
              disabled={!t.source} onClick={() => onPick(byId[t.source])}>
              <small>{t.label}</small>
              {t.source && <b>{plainValue(t.abs && typeof byId[t.source]?.value === 'number' ? Math.abs(byId[t.source].value) : byId[t.source]?.value, byId[t.source]?.unit) ?? '연도별 ▸'}</b>}
            </button>
          )))}
      </div>
      <div className="nb-legend">
        {Object.entries(GRADE).filter(([k]) => counts[k]).map(([k, g]) => (
          <span key={k}><GradeBadge gradeKey={k} /> {counts[k]}개 · {g.desc}</span>
        ))}
      </div>
    </>
  )
}

export function EvidenceTable({ data, pdf, onPick }) {
  const pageOf = (quote) => data.clauses.find((c) => c.quote === quote)?.page
  return (
    <div className="nb-evi-wrap">
      <table className="nb-evi">
        <thead>
          <tr><th>항목</th><th>값</th><th>근거 종류</th><th>어디서</th><th>공개일</th><th>원문</th></tr>
        </thead>
        <tbody>
          {data.sources.map((s) => {
            const page = s.grade_key === 'bill' && s.quote ? pageOf(s.quote) : null
            return (
              <tr key={s.id} className={`g-${s.grade_key}`} onClick={() => onPick(s)}>
                <td><b>{s.name}</b></td>
                <td className="nb-evi-val"><ValueView value={s.value} unit={s.unit} /></td>
                <td><GradeBadge gradeKey={s.grade_key}>{s.grade}</GradeBadge></td>
                <td className="nb-evi-origin">{s.where ?? s.origin}{s.as_of_ko && <small>{s.as_of_ko} 기준</small>}</td>
                <td className="nb-evi-date">
                  {s.published_at ?? '—'}
                  {s.before_cutoff === true && <small className="nb-ok">✓ 발의일 이전</small>}
                  {s.before_cutoff === false && <small className="nb-warn">⚠ 발의일 이후</small>}
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  {page && pdf && <a className="nb-link" href={`${pdf}#page=${page}`} target="_blank" rel="noreferrer">의안 {page}쪽 ↗</a>}
                  {s.url && <a className="nb-link" href={s.url} target="_blank" rel="noreferrer">원자료 ↗</a>}
                  {!page && !s.url && <button className="nb-link-btn" onClick={() => onPick(s)}>상세 ▸</button>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function Dates({ data, onPick }) {
  return (
    <>
      <p className="nb-lead">각 값이 공개된 날이에요. 발의일({data.cutoff}) 이후 공개된 자료는 사용하지 않아요.</p>
      <Timeline sources={data.sources} cutoff={data.cutoff} onPick={onPick} />
    </>
  )
}

export function Clauses({ data, pdf }) {
  return (
    <>
      <ul className="nb-clauses">
        {data.clauses.map((c) => (
          <li key={c.id}>
            <span className="nb-clause-id">{c.id}{c.role && <small>{c.role}</small>}</span>
            <span className="nb-clause-q">{c.quote}</span>
            <span className="nb-ok">✓ 원문 확인
              {pdf && c.page && <a className="nb-page-link" href={`${pdf}#page=${c.page}`} target="_blank" rel="noreferrer">PDF {c.page}쪽 ↗</a>}
            </span>
          </li>
        ))}
      </ul>
      {data.not_estimated.length > 0 && (
        <>
          <h3 className="sv-h3">추계하지 않은 항목</h3>
          <ul className="sv-plain">
            {data.not_estimated.map((e) => (<li key={e.item}><b>{e.item}</b> — {e.reason}</li>))}
          </ul>
        </>
      )}
    </>
  )
}

export function YearTable({ data }) {
  const scen = Object.entries(data.scenarios)
  const years = Object.keys(scen[0][1].by_year).sort()
  const main = scen[0][1]
  const ratio = main.total ? main.national / main.total : 1
  return (
    <div className="nb-evi-wrap">
      <table className="sv-years">
        <thead><tr><th>구분</th>{years.map((y) => <th key={y}>{y}년</th>)}{years.length > 1 && <th>합계</th>}</tr></thead>
        <tbody>
          {scen.map(([name, s]) => (
            <tr key={name}>
              <th>{scen.length > 1 ? `추가재정소요(${name})` : '추가재정소요'}</th>
              {years.map((y) => <td key={y}>{won(s.by_year[y] ?? 0)}</td>)}
              {years.length > 1 && <td><b>{won(s.total)}</b></td>}
            </tr>
          ))}
          {main.local > 0 && [['국비', ratio], ['지방비', 1 - ratio]].map(([label, r]) => (
            <tr key={label} className="sv-sub">
              <th>{label} ({Math.round(r * 100)}%)</th>
              {years.map((y) => <td key={y}>{won((main.by_year[y] ?? 0) * r)}</td>)}
              {years.length > 1 && <td>{won(main.total * r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {scen.filter(([, s]) => s.assumption).map(([name, s]) => (
        <p key={name} className="nb-muted">{name}: {s.assumption}</p>
      ))}
    </div>
  )
}

export function Compare({ data }) {
  const a = data.answer
  const main = Object.entries(data.scenarios)[0][1]
  const nabo = Object.entries(a.scenarios)[0]
  return (
    <>
      <p className="nb-lead">국회예산정책처가 이후에 회답한 추계서와 비교한 결과예요. 이 값은 추계 과정에 쓰이지 않았어요.</p>
      <ResultBars rows={[
        { label: '이 시스템', value: main.total, cls: 'ours', err: pct(a.error_pct) },
        { label: `국회예산정책처 (${nabo[0]})`, value: nabo[1], cls: 'nabo', err: '공식 추계' },
      ]} />
      <div className="nb-answer-grid">
        {a.formula && (<div><h3>국회예산정책처 산식</h3><p>{a.formula}</p>{a.split && <p className="nb-muted">재원분담: {a.split}</p>}</div>)}
        {a.quote && (<div><h3>추계서 결론</h3><blockquote className="nb-quote">“{a.quote}”</blockquote><p className="nb-muted">추계번호 {a.no}{a.reply && ` · 회답 ${a.reply}`}</p></div>)}
      </div>
    </>
  )
}
