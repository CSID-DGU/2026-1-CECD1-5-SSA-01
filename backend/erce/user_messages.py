"""Keep technical diagnostics in logs, with actionable Korean at the UI boundary."""
import re


def user_error(error):
    message = str(error)
    if re.search(r"[가-힣]", message) and not re.search(r"[A-Za-z]{4,}", message):
        return message
    text = message.lower()
    if "year" in text or "horizon" in text or "future" in text:
        return "자료의 적용 연도와 추계기간이 맞지 않아요. 시작연도와 근거의 기준연도를 확인해 주세요."
    if "mismatch" in text or "scope" in text or "route" in text:
        return "선택한 산식과 근거의 적용 대상이 맞지 않아요. 비용 유형과 대상 범위를 확인해 주세요."
    if "confirmation" in text or "scenario" in text or "review" in text:
        return "이 근거를 사용하려면 가정 확인이 필요해요. 적용 조건을 확인하고 다시 시도해 주세요."
    if "missing" in text or "required" in text or "needs" in text:
        return "계산에 필요한 정보가 부족해요. 확인이 필요한 값과 근거를 채워 주세요."
    return "처리를 완료하지 못했어요. 입력값과 근거를 확인한 뒤 다시 시도해 주세요."
