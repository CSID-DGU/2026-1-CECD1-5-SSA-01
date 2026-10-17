import { useEffect, useRef, useState } from 'react'
import { Pipeline, Progress } from './Pipeline.jsx'
import { API } from './util.js'

export default function NewEstimate() {
  const [bills, setBills] = useState([])
  const [billNo, setBillNo] = useState('')
  const [events, setEvents] = useState([])
  const [running, setRunning] = useState(false)
  const [label, setLabel] = useState('')
  const [error, setError] = useState('')
  const [drag, setDrag] = useState(false)
  const timer = useRef(null)

  useEffect(() => {
    fetch(`${API}/api/nabo/ai/samples`).then((r) => r.json()).then((d) => setBills(d.samples ?? [])).catch(() => {})
    return () => clearTimeout(timer.current)
  }, [])

  const poll = (job) => {
    fetch(`${API}/api/nabo/ai/job/${job}`).then((r) => r.json()).then((j) => {
      setEvents(j.events ?? [])
      if (j.status === 'running') {
        timer.current = setTimeout(() => poll(job), 1200)
      } else if (j.run_id) {
        window.location.hash = `#/runs/${j.run_id}`
      } else {
        setRunning(false)
        setError(j.error || '추계를 완료하지 못했어요.')
      }
    }).catch(() => { timer.current = setTimeout(() => poll(job), 2500) })
  }

  const start = async (payload, name) => {
    setError('')
    setEvents([])
    setLabel(name)
    setRunning(true)
    try {
      const res = await fetch(`${API}/api/nabo/ai/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const j = await res.json()
      if (j.error) throw new Error(j.error)
      poll(j.job)
    } catch (e) {
      setRunning(false)
      setError(String(e.message || e))
    }
  }

  const upload = (file) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) { setError('PDF 파일만 올릴 수 있어요.'); return }
    const reader = new FileReader()
    reader.onload = () => start({ pdf_b64: reader.result, filename: file.name }, file.name)
    reader.readAsDataURL(file)
  }

  const byNumber = (e) => {
    e.preventDefault()
    const no = billNo.trim()
    if (no) start({ bill_no: no }, bills.find((b) => b.bill_no === no)?.title ?? `의안 ${no}`)
  }

  return (
    <div className="sv-page">
      <div className="sv-head">
        <div>
          <h1>새 비용추계</h1>
          <p className="nb-muted">의안 원문을 올리면 조문 분석 → 근거 수집 → 계산 → 비용추계서 초안까지 자동으로 만들어요. 현재 현금 지원금(수당·지원금·기본소득) 법안을 지원해요.</p>
        </div>
      </div>

      {!running && (
        <div className="sv-grid">
          <div className="sv-card wide">
            <div
              className={`ai-drop ${drag ? 'on' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]) }}
            >
              <b>의안 원문 PDF를 끌어다 놓으세요</b>
              <span>의안정보시스템의 의안 원문(제안이유 및 주요내용 + 조문) PDF</span>
              <label className="ai-file">파일 선택<input type="file" accept="application/pdf" onChange={(e) => upload(e.target.files[0])} /></label>
            </div>
            <form className="sv-billno" onSubmit={byNumber}>
              <span>또는 의안번호로</span>
              <input list="sv-bills" value={billNo} onChange={(e) => setBillNo(e.target.value)} placeholder="예: 2200563" />
              <datalist id="sv-bills">{bills.map((b) => <option key={b.bill_no} value={b.bill_no}>{b.title}</option>)}</datalist>
              <button className="sv-btn primary" disabled={!billNo.trim()}>추계 시작</button>
            </form>
          </div>
          <div className="sv-card wide sv-how">
            <div><b>1. 조문 분석</b><span>AI가 지급대상·지급액·기간을 정하고, 코드가 인용문과 금액을 원문과 글자 단위로 대조해요.</span></div>
            <div><b>2. 근거 수집</b><span>발의일 이전에 공개된 통계만 기준정보 원장과 웹에서 찾고, 웹 자료는 코드가 원문을 직접 열어 확인해요.</span></div>
            <div><b>3. 계산</b><span>계산은 코드가 해요. 모든 숫자에 기관·문서·기준시점·공개일이 붙어요.</span></div>
            <div><b>4. 초안</b><span>국회예산정책처 회답서 체계의 비용추계서 초안을 PDF·Word로 받을 수 있어요.</span></div>
          </div>
        </div>
      )}

      {error && <p className="nb-error">{error}</p>}

      {running && (
        <div className="sv-card">
          <Progress events={events} label={label} />
          <Pipeline events={events} running />
        </div>
      )}
    </div>
  )
}
