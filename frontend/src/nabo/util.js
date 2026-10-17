// Read-only export (no server): pages read pre-exported files next to nabo.html.
export const STATIC = import.meta.env.VITE_NABO_STATIC === '1'
export const paths = {
  runs: () => (STATIC ? './data/runs.json' : `${API}/api/nabo/ai/runs`),
  run: (id) => (STATIC ? `./data/run/${id}.json` : `${API}/api/nabo/ai/run/${id}`),
  pdf: (id) => (STATIC ? `./data/pdf/${id}.pdf` : `${API}/api/nabo/ai/pdf/${id}`),
  report: (id) => (STATIC ? `./data/report/${id}.html` : `${API}/api/nabo/ai/report/${id}`),
}

export const API = (import.meta.env.VITE_NABO_API_URL ?? 'http://127.0.0.1:8010').replace(/\/$/, '')

export const GRADE = {
  bill: { label: '법안 명시', desc: '의안 조문에 적힌 값' },
  official: { label: '공식 통계', desc: '정부·통계청 공표 자료' },
  nabo: { label: 'NABO 인용', desc: '먼저 공개된 다른 추계서의 값' },
  precedent: { label: '선례 준용', desc: '같은 종류 사업의 기준을 가져옴' },
  assumption: { label: '가정', desc: '자료가 없어 명시한 가정' },
  missing: { label: '근거 없음', desc: '반영하지 않음' },
}

export function won(value) {
  if (value === null || value === undefined) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? '−' : ''
  if (abs >= 1e12) {
    const jo = Math.floor(abs / 1e12)
    const eok = Math.round((abs % 1e12) / 1e8)
    return `${sign}${jo.toLocaleString()}조${eok ? ` ${eok.toLocaleString()}억` : ''}원`
  }
  if (abs >= 1e8) return `${sign}${Math.round(abs / 1e8).toLocaleString()}억원`
  return `${sign}${Math.round(abs).toLocaleString()}원`
}

export function pct(v) {
  if (v === null || v === undefined) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

export function plainValue(value, unit) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    if (unit === 'ratio' || (Math.abs(value) < 1 && value !== 0)) return `${+(value * 100).toFixed(2)}%`
    return `${value.toLocaleString()}${unit && unit !== 'ratio' ? ` ${unit}` : ''}`
  }
  if (Array.isArray(value)) return value.map((v) => plainValue(v, unit)).join(value.length === 2 ? ' ~ ' : ', ')
  if (typeof value === 'object') {
    if ('national' in value) return `국가 ${Math.round(value.national * 100)}% · 지자체 ${Math.round(value.local * 100)}%`
    return null
  }
  return `${value}${unit && unit !== '-' ? ` ${unit}` : ''}`
}
