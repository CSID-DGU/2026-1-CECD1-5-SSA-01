import { useEffect, useState } from 'react'
import { API, won } from './util.js'

export default function RunList() {
  const [runs, setRuns] = useState(null)
  const [q, setQ] = useState('')
  useEffect(() => {
    fetch(`${API}/api/nabo/ai/runs`).then((r) => r.json()).then(setRuns).catch(() => setRuns([]))
  }, [])
  const shown = (runs ?? []).filter((r) => !q.trim() || `${r.title} ${r.bill_no} ${r.proposer}`.includes(q.trim()))
  return (
    <div className="sv-page">
      <div className="sv-head">
        <div>
          <h1>추계 내역</h1>
          <p className="nb-muted">지금까지 작성한 비용추계예요. 행을 누르면 결과와 근거, 초안을 볼 수 있어요.</p>
        </div>
        <div className="sv-actions">
          <input className="sv-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="의안명·의안번호 검색" />
          <a className="sv-btn primary" href="#/new">새 추계</a>
        </div>
      </div>
      <div className="sv-card">
        {runs === null && <p className="nb-loading">불러오는 중…</p>}
        {runs?.length === 0 && <p className="nb-muted">아직 추계가 없어요. <a href="#/new">새 추계</a>를 시작해 보세요.</p>}
        {shown.length > 0 && (
          <div className="nb-evi-wrap">
            <table className="sv-list">
              <thead><tr><th>의안명</th><th>의안번호</th><th>발의일</th><th>추계기간</th><th className="r">추가재정소요</th><th>상태</th><th>작성</th></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.run_id} onClick={() => { window.location.hash = `#/runs/${r.run_id}` }}>
                    <td><b>{r.title}</b><small>{r.proposer}</small></td>
                    <td>{r.bill_no}</td>
                    <td>{r.propose_date}</td>
                    <td>{r.years?.length === 1 ? `${r.years[0]}` : `${r.years?.[0]}~${r.years?.[r.years.length - 1]}`}</td>
                    <td className="r"><b>{won(r.total)}</b>{r.upper && <small>~ {won(r.upper)}</small>}</td>
                    <td><span className={`sv-status ${r.needs ? 'warn' : 'ok'}`}>{r.needs ? `입력 필요 ${r.needs}` : '완료'}</span></td>
                    <td className="nb-muted">{r.created}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
