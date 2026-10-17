import test from 'node:test'
import assert from 'node:assert/strict'
import { referenceCandidates, formatReferenceValue, selectedEvidenceContext } from './erceCandidates.js'

test('같은 변수 후보만 보여주며 공식 기준과 최신 자료를 먼저 표시한다', () => {
  const item = { calculation: { referenceCandidates: [
    { evidenceKey: 'a', variableKey: 'unit_cost', value: 10, availableAt: '2025-01-01' },
    { evidenceKey: 'b', variableKey: 'unit_cost', value: 20, sourceClass: 'official_standard' },
    { evidenceKey: 'c', variableKey: 'quantity', value: 30 },
    { evidenceKey: 'd', variableKey: 'unit_cost', value: 40, availableAt: '2026-01-01' },
  ] } }
  assert.deepEqual(referenceCandidates(item, 'unit_cost').map(row => row.id), ['b', 'd', 'a'])
})

test('후보의 실제 단위를 그대로 읽기 쉽게 표시한다', () => {
  assert.equal(formatReferenceValue({ value: .15, unit: 'ratio' }), '15 %')
  assert.equal(formatReferenceValue({ value: 200000, unit: 'KRW/person/month' }), '200,000 원/명·월')
})

test('선택한 근거 ID와 적용 이유가 문서 생성까지 유지된다', () => {
  const context = selectedEvidenceContext({ itemIndex: 2, engineContext: { selected_evidence_keys: ['previous'] } }, {
    '2:unit_cost': { evidenceKey: 'selected', value: 5, source_ref: '공식 자료' },
    '1:unit_cost': { evidenceKey: 'other-item' },
    '2:quantity': { value: 10, source_ref: '사용자 입력' },
  })
  assert.deepEqual(context.selected_evidence_keys, ['previous', 'selected'])
  assert.match(context.evidence_selection_reasons.selected, /공식 자료/)
})

test('없는 후보를 임의로 생성하지 않는다', () => {
  assert.deepEqual(referenceCandidates({}, 'quantity'), [])
})
