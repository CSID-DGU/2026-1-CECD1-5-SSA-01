import test from 'node:test'
import assert from 'node:assert/strict'
import { displayValue, displaySources, evidenceRows, evidenceSources } from './erceDisplay.js'

test('비율과 금액을 사람이 읽는 단위로 표시한다', () => {
  assert.equal(displayValue(.0176, 'ratio'), '1.76%')
  assert.equal(displayValue(.884, 'ratio'), '88.4%')
  assert.equal(displayValue(200000, 'KRW/person/month'), '20만원')
  assert.equal(displayValue(1601000000, 'KRW/year'), '16억 100만원')
  assert.equal(displayValue(12, 'month/year'), '12개월')
  assert.equal(displayValue(1.4, 'person/household'), '1.4명')
})

test('연도별 표에 이미 있는 연간 비용 배열은 중복 표시하지 않는다', () => {
  const rows = evidenceRows({ resolvedVariables: { annual_amount: { value: [10] } },
    evidenceVariables: { advance_months: { value: 12 } }, derivationTrace: [{ additional_expense: 10 }] })
  assert.deepEqual(rows.map(([key]) => key), ['advance_months'])
})

test('같은 출처와 그 축약본은 한 번만 남긴다', () => {
  const sources = evidenceSources({ evidenceVariables: { a: { source_ref: '선례 PDF; 원통계' }, b: { source_ref: '선례 PDF; 원통계' } },
    selectedMethods: [{ source_ref: '선례 PDF' }] })
  assert.deepEqual(sources, ['선례 PDF; 원통계'])
})

test('문서번호와 페이지 대신 의안번호만 중복 없이 표시한다', () => {
  assert.equal(displaySources(['2201707 비용추계서24C1988 PDF4~7쪽;2021한부모실태조사',
    '2201707 비용추계서24C1988 PDF4~7쪽']), '의안 2201707')
  assert.equal(displaySources('통계청 장래인구추계'), '통계청 장래인구추계')
  assert.equal(displaySources(['의안 2201707', '의안 2200703']), '의안 2201707 · 의안 2200703')
})
