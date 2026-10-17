export function userMessage(error) {
  const text = String(error?.message || error || '')
  if (/Failed to fetch|NetworkError|Load failed|fetch failed/i.test(text)) {
    return '서버에 연결하지 못했어요. 연결 상태를 확인한 뒤 다시 시도해 주세요.'
  }
  if (/abort|timeout/i.test(text)) return '처리 시간이 길어졌어요. 잠시 후 다시 시도해 주세요.'
  if (/[가-힣]/.test(text) && !/[A-Za-z]{4,}/.test(text)) return text
  return '처리를 완료하지 못했어요. 입력값과 근거를 확인한 뒤 다시 시도해 주세요.'
}
