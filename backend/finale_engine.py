"""finale_engine — 조문별로 DB에서 가장 유사한 산식만 제시하는 최소 엔진.

오늘 하루의 결론: LLM은 "이 조문이 비용 관련이다"라는 인식은 잘하지만,
"이게 신규냐 현행유지냐, 어떤 메커니즘이냐"라는 판단은 계속 틀렸다(모델
버전을 바꿔도 동일). 그래서 이 엔진은 인식만 LLM에 맡기고 판단은 아예
시키지 않는다.

파이프라인:
  1. 조문 분리(기존 analyzer_v2, 안정적)
  2. LLM에게 "비용 관련 조문이냐 + 한 줄 설명"만 묻는다(단일 목적, 단순
     스키마 — event_type/additionality/cost_mechanism 등 판단 필드 없음)
  3. 비용 관련으로 인식된 조문마다, family로 좁히지 않고 TAG DB 전체에서
     임베딩 검색
  4. 최유사 항목의 산식·변수명을 그대로 보여주고, 값이 비면 "확인 필요"로
     표시한다. 숫자를 확정하지 않는다.

estimator_v2/committee_estimator_v* 어느 것도 건드리지 않는 완전히 독립된
모듈이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.analyzer_v2 import (
    _call_llm_raw_json,
    _extract_bill_name,
    _extract_current_bill_no,
    _extract_pdf_text_from_bytes,
    split_articles,
    strip_appendices,
    try_embed,
)
from backend.committee_search import search_committee
from backend.committee_size_extract import extract_committee_size
from backend.estimator import tag_db
from backend.estimator_v2.retrieval import target_metadata

FINALE_ENGINE_VERSION = "finale-engine-v2"

_MIN_SIMILARITY = 0.45

_FORMULA_OPERATOR = re.compile(r"[×xX*+\-÷/]|Σ|합계|비율")
# 연구계획·일부 지원금(같은 제도를 국회예산정책처 모형/유사사례로 준용하는
# 경우)은 곱셈 기호 없이 서술형으로 산식을 표현한다(실측: 2213320, 2216470
# 둘 다 "모형/유사사례 활용 추계" 형태). 이것도 진짜 산식으로 인정한다 —
# 총액 숫자 하나만 있는 것과는 다르다(방법론이 명시돼 있음).
_REFERENCE_METHODOLOGY = re.compile(r"참고|준용|활용|모형|유사사례|추계함|추정")


# 외부위촉형(사례금 지급 대상) 위원회 신호. 있으면 바로 허용.
_COMMITTEE_STIPEND_SIGNAL = re.compile(r"위촉|수당|사례금|여비|참석비|외부.{0,4}위원|민간위원")
# 내부겸임형(별도 수당 없이 기존 소속 인력이 겸임) 명시 신호. 있으면 차단.
# 실측(2215954 교원인사위/학사위): "전임교원 중에서...임명한다"처럼 위원
# 구성을 소속 내부 인력으로 못박은 경우에만 내부겸임형으로 확신할 수 있다.
# 실측(2214559): 수당을 "대통령령으로 정한다"고 위임해 조문에 위촉/수당
# 단어가 아예 없는 진짜 외부위촉형도 있어, "신호 있어야 허용"이 아니라
# "내부겸임 신호가 없으면 기본 허용"으로 뒤집어야 이 케이스를 안 죽인다.
_COMMITTEE_INTERNAL_ONLY_SIGNAL = re.compile(
    r"(?:전임교원|소속\s*직원|소속\s*공무원|기존\s*인력)\s*(?:중에서|가운데서|중)"
)


def _committee_gate_eligible(article_text: str) -> bool:
    """조문이 외부위촉형(사례금 지급 대상) 위원회로 볼 만한지 판단한다.

    내부겸임 신호(전임교원 중에서 등)가 있으면 차단, 없으면 기본 허용—
    위촉/수당 신호는 있으면 더 확실하지만 필수는 아니다(수당을 대통령령에
    위임해 조문에 안 나오는 경우가 실제로 있었다).
    """
    if _COMMITTEE_INTERNAL_ONLY_SIGNAL.search(article_text):
        return False
    return True


def _is_decomposed_formula(formula: str) -> bool:
    """산식이 진짜 계산식/방법론인지, 그냥 총액 숫자 하나인지 구분한다.

    실측(2214559): "85.6 백만원"처럼 연산자·방법론 설명 없이 숫자만 있는
    것이 산식으로 표시돼 실제 정답(인원×횟수×단가)과 형태가 달랐다.
    연산자형(위원회류)이든 방법론 서술형(연구계획·모형준용형 지원금)이든
    하나라도 있으면 "산식"으로 인정하고, 둘 다 없는 순수 총액만 제외한다.
    """
    text = formula or ""
    return bool(_FORMULA_OPERATOR.search(text) or _REFERENCE_METHODOLOGY.search(text))
# 표시 임계값은 검색 임계값보다 높다. 실측(2125736): 절차 조문(위원회간사·
# 임기·심의절차 등)이 0.49~0.57 사이의 약한 매치로 "비용항목"처럼 표시되는
# 노이즈를 만들었다. 0.6 미만은 검색은 하되 최종 제안에서는 뺀다.
_PRESENT_MIN_SIMILARITY = 0.80
# committee family는 지원금과 달리 산식 모양(A×B×C)이 토픽에 상관없이
# 거의 항상 동일하다(실측: 탈석탄위원회·재생에너지위원회·친환경위원회 등
# 전혀 다른 도메인끼리도 전부 위원수×회의횟수×사례금단가). 그래서 토픽
# 유사도가 낮아도(0.6대) 산식 자체는 재사용해도 되는 위험이 지원금보다
# 훨씬 낮다 — 전용 낮은 임계값을 둔다.
_PRESENT_MIN_SIMILARITY_COMMITTEE = 0.60

_RECOGNIZE_PROMPT = """다음은 "{bill_title}"의 조문 하나다. "이 조문이
실행되면 국가·지방자치단체가 돈을 쓰게 되는가(설치·운영·지급·지원·채용·
구축 등)"만 판단하라. **신규인지 현행유지인지는 판단하지 마라** — 그건
묻지 않는다. 비용 발생 여지가 조금이라도 있으면 cost_relevant=true로
표시하라(과잉표시가 누락보다 낫다).

[제안이유 요약]
{proposal_reason}

description을 쓸 때 "인원증가"·"비용 발생" 같은 뭉뚱그린 표현 대신, 조문
또는 위 제안이유에 실제로 등장하는 고유명사(제도명·급여명·위원회명 등)를
그대로 옮겨 적어라. 조문 자체가 "8세를13세로한다"나 "제72조 각호 외의
부분 중 2025년을 2030년으로 한다"처럼 숫자·연도만 바꾸는 diff 형식이라
조문 안에 고유명사가 없으면, **위 제안이유에서 이 조문번호(예: 제72조)가
어떤 제도를 가리키는지 찾아 그 제도명을 description에 반드시 포함시켜라**
(예: 의안명이 "아동수당법..."이면 "아동수당 지급 대상/금액 변경"처럼,
제안이유에 "제72조 등"이 "조합법인 법인세 과세특례"를 가리킨다고 나오면
"조합법인 법인세 과세특례 적용기한 연장"처럼 써야 한다).
**절대 의안명·제안이유와 무관한 제도명을 지어내거나 다른 예시를 베끼지
마라** — description은 반드시 이 조문·의안명·제안이유에서만 나온
사실이어야 한다.

[조문 {article_ref}]
{article_text}

다음 JSON 객체 하나로만 답하라(배열 아님):
{{"cost_relevant": true 또는 false,
"description": "비용이 발생하는 대상·행위를, 조문/의안명/제안이유에 실제 등장하는 고유명사를 살려 한 문장으로(비용 무관이면 빈 문자열)"}}
"""

_PROPOSAL_REASON_MARKER = re.compile(r"제안이유\s*(?:및\s*주요내용)?")


def _extract_proposal_reason(raw_text: str) -> str:
    """PDF 앞부분의 "제안이유" 문단을 뽑는다.

    실측(2212555 조특법): diff형 조문("제72조...2025년을2030년으로")은
    조문 자체에 제도명이 없지만, 제안이유에는 "제72조 등"이 "조합법인
    법인세 과세특례"를 가리킨다고 명시돼 있다. 의안 제목만으로는 부족한
    이 케이스를 제안이유까지 넘겨서 보완한다.
    """
    match = _PROPOSAL_REASON_MARKER.search(raw_text[:3000])
    if not match:
        return ""
    start = match.end()
    chunk = raw_text[start : start + 1200]
    end_marker = re.search(r"의안\s*\n?\s*번호|법률\s*\n?\s*제\s*\n?\s*호", chunk)
    if end_marker:
        chunk = chunk[: end_marker.start()]
    return re.sub(r"\s+", "", chunk).strip()


@dataclass
class FormulaSuggestion:
    article_ref: str
    description: str
    matched_bill_no: str
    matched_item_name: str
    similarity: float
    formula: str
    matched_category: str = ""
    variables: list[dict] = field(default_factory=list)
    missing_value_names: list[str] = field(default_factory=list)
    article_stated_committee_size: dict | None = None


_Q = '["“][^"”]*["”]'  # 원문은 스마트따옴표(“”)를 쓰지만 방어적으로 ASCII도 허용

_DIFF_BOILERPLATE_PATTERNS = (
    re.compile(
        r"제\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+호)?(?:[가-힣]목)?을?를?"
        r"다음과같이(?:하고|한다|신설한다|개정한다)[.,]?"
    ),
    re.compile(
        r"같은\s*조(?:제\d+항)?(?:제\d+호)?(?:[가-힣]목)?중"
        + _Q + r"을?를?" + _Q + r"으로한다[.,]?"
    ),
    re.compile(
        r"제\d+조(?:의\d+)?제\d+항제\d+호[가-힣]목중"
        + _Q + r"을?를?" + _Q + r"으로한다[.,]?"
    ),
)


def _strip_amendment_diff_boilerplate(text: str) -> str:
    """일부개정 diff 지시문("제N조를 다음과 같이 한다" 등)을 제거하고 실질
    내용만 남긴다.

    실측(2126650): 조문 원문을 그대로 임베딩하면 diff 지시문이 실제 내용을
    희석시켜 유사도가 오히려 낮아졌다(0.64→0.48). 지시문만 정규식으로
    제거하면 실질 조항("재원은 국가가 전부를 부담한다" 등)만 남아 검색이
    안정된다.
    """
    compact = re.sub(r"\s+", "", text or "")
    for pattern in _DIFF_BOILERPLATE_PATTERNS:
        compact = pattern.sub("", compact)
    return compact.strip()


def _recognize_cost_relevant(
    articles: list[dict], *, bill_title: str = "", proposal_reason: str = ""
) -> list[dict]:
    """조문 하나씩 LLM에게 '비용 관련이냐 + 한 줄 설명'만 묻는다.

    배치(여러 조문을 한 번에 묻기)는 오늘 하루 종일 확인된 문제(모델이
    일부만 답하거나 배열 대신 단일 객체로 답함)를 그대로 재현했다. 조문당
    한 번씩, 단일 JSON 객체만 기대하도록 단순화해 그 애매함 자체를 없앤다.

    bill_title을 프롬프트에 같이 넘기는 이유: diff형 조문("8세를13세로
    한다")은 조문 자체에 제도명이 없어, 의안명을 안 주면 LLM이 예시 문구를
    베끼거나 엉뚱한 제도명을 지어낸다(실측: 아동수당법 조문에 "자립정착금"
    이라고 답한 사례). 의안명을 주면 그 제도명을 정확히 채워 넣는다.

    proposal_reason도 같이 넘기는 이유: 의안명이 "조세특례제한법
    일부개정법률안"처럼 범용적이면 bill_title만으로는 부족하다(실측:
    2212555 — "제72조...2025년을2030년으로" 조문만으론 이게 무슨 제도인지
    알 수 없었음). 제안이유에는 "제72조 등"이 "조합법인 법인세 과세특례"를
    가리킨다고 명시돼 있어, 이를 넘기면 diff형 조문도 정확히 채워진다.
    """
    results: list[dict] = []
    for article in articles:
        article_ref = str(article.get("no") or "")
        prompt = _RECOGNIZE_PROMPT.format(
            bill_title=bill_title or "(제목 미상)",
            proposal_reason=proposal_reason or "(제안이유 추출 안 됨)",
            article_ref=article_ref,
            article_text=str(article.get("text") or "")[:1200],
        )
        try:
            parsed = _call_llm_raw_json(prompt, temperature=0.0, timeout=60)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        parsed = {**parsed, "article_ref": article_ref}
        results.append(parsed)
    return results


def _value_completeness_bonus(variables: list[dict]) -> float:
    """변수에 실제 값이 채워진 비율을 보너스로 환산한다.

    실측(2213116): 임베딩 유사도 1위(2212722)는 "합산추계로 개별항목
    미제시"라 변수 값이 3/5만 채워진 껍데기였고, 진짜 재사용 가능한 선례
    (2214807, 값 2/3 + 회의횟수·단가 리터럴 일치)는 유사도에서 밀려 잘렸다.
    값이 채워진 항목일수록 실제로 계산에 갖다 쓸 수 있으므로 보너스를 준다
    — 유사도 근소차를 뒤집을 만큼만(최대 0.06) 준다.
    """
    if not variables:
        return 0.0
    filled = sum(1 for v in variables if v.get("value") is not None)
    ratio = filled / len(variables)
    return ratio * 0.06


def _search_whole_db(
    query_vector: list[float],
    *,
    exclude_bill_nos: set[str],
    cutoff_date: str | None,
    k: int = 3,
    query_text: str = "",
) -> list[dict]:
    data = tag_db._load()
    embeddings = tag_db._load_embeddings()
    formulas = tag_db._formula_by_item()
    scored: list[tuple[float, float, str]] = []
    for item_id, vector in embeddings.items():
        meta = data["items"].get(item_id, {})
        if str(meta.get("bill_no") or "") in exclude_bill_nos:
            continue
        propose_date = str(meta.get("propose_date") or "")
        if cutoff_date and propose_date and propose_date > cutoff_date:
            continue
        similarity = tag_db._cosine(query_vector, vector)
        if similarity < _MIN_SIMILARITY:
            continue
        # 값 있는 선례가 top-k 밖으로 밀려 잘려나가던 문제(실측 2213116)를
        # 막기 위해, 정렬 전에 산식필터를 적용해 빈약한 항목을 후보에서 뺀다.
        formula = formulas.get(item_id, "")
        if not formula or not _is_decomposed_formula(formula):
            continue
        bonus = _value_completeness_bonus(data["vars"].get(item_id, []))
        scored.append((similarity + bonus, similarity, item_id))
    scored.sort(key=lambda value: -value[0])
    results = []
    for _ranked, similarity, item_id in scored[:k]:
        formula = formulas.get(item_id, "")
        meta = data["items"].get(item_id, {})
        results.append(
            {
                "bill_no": meta.get("bill_no", ""),
                "item_name": meta.get("name", ""),
                "category": meta.get("category", ""),
                "family": meta.get("family", ""),
                "similarity": round(similarity, 4),
                "formula": formula,
                "variables": data["vars"].get(item_id, []),
            }
        )
    return results


def suggest_formulas(pdf_bytes: bytes, *, filename: str = "uploaded.pdf") -> list[FormulaSuggestion]:
    raw_text = _extract_pdf_text_from_bytes(pdf_bytes)
    if not raw_text:
        return []
    legal_text = strip_appendices(raw_text)
    articles, _doc_type = split_articles(legal_text)
    bill_no = _extract_current_bill_no(raw_text, filename)
    exclude_bill_nos = {bill_no} if bill_no else set()
    cutoff_date, _stored_bill_name = target_metadata(bill_no)
    bill_title = _extract_bill_name(raw_text, bill_no or filename)
    proposal_reason = _extract_proposal_reason(raw_text)

    by_ref = {str(a.get("no") or ""): a for a in articles}
    recognized = _recognize_cost_relevant(
        articles, bill_title=bill_title, proposal_reason=proposal_reason
    )
    suggestions: list[FormulaSuggestion] = []
    for row in recognized:
        if not row.get("cost_relevant"):
            continue
        description = str(row.get("description") or "").strip()
        if not description:
            continue
        article_ref = str(row.get("article_ref") or "")
        # 실측: LLM description(비결정적이지만 diff 잡음 제거)과 diff
        # 지시문만 걷어낸 조문 원문(결정적) 둘 다 각자 실패 케이스가 있었다
        # (2126650: description 0.55~0.64로 오락가락, 원문 그대로는 0.48로
        # diff에 희석됨). 두 후보를 모두 검색해 더 나은 쪽을 쓴다 — 하나를
        # 고정하는 것보다 안정적이다.
        source_article = by_ref.get(article_ref)
        cleaned_article_text = (
            _strip_amendment_diff_boilerplate(str(source_article.get("text") or ""))
            if source_article
            else ""
        )
        candidate_queries = [description[:1500]]
        if cleaned_article_text and cleaned_article_text != description:
            candidate_queries.append(cleaned_article_text[:1500])

        # 실측(2215954): "위원회"라는 단어만으로 committee_search를 부르면
        # 대학 교원인사위원회·학사위원회처럼 "전임교원이 겸임하고 별도
        # 수당이 없는 내부 위원회"까지 외부위촉형 산식(위원수×사례금×
        # 회의횟수)에 잘못 꽂힌다(존재하지도 않는 항목에 답변). 조문
        # 원문(LLM 설명이 아니라 원문 자체)에 위촉·수당 신호가 실제로
        # 있을 때만 committee_search를 허용한다 — LLM 판단이 아니라
        # 원문에 그 단어가 있는지를 기계적으로 확인.
        # 실측(2216065): PDF 줄바꿈 지점에서 "위촉"이 "위 촉"처럼 공백이
        # 끼어 들어가는 추출 artifact가 있어(2126650 diff-boilerplate 때도
        # 같은 문제) 공백을 제거하고 나서 신호를 찾는다.
        source_text_for_gate = re.sub(
            r"\s+", "", str(source_article.get("text") or "") if source_article else ""
        )
        committee_eligible = _committee_gate_eligible(source_text_for_gate)

        best = None
        for query_text in candidate_queries:
            query_vector = try_embed(query_text)
            if not query_vector:
                continue
            matches = _search_whole_db(
                query_vector,
                exclude_bill_nos=exclude_bill_nos,
                cutoff_date=cutoff_date,
                k=3,
                query_text=query_text,
            )
            if matches and (best is None or matches[0]["similarity"] > best["similarity"]):
                best = matches[0]
            # 실측(2214559): "위원회"가 언급된 조문은 전체 DB(965개 지원금
            # 포함 3,346개)에서 찾으면 0.73에 그치지만, committee family(396개)
            # 로 좁히면 0.90까지 뛴다 — 무관한 카테고리에 순위가 밀렸던 것.
            if "위원회" in query_text and committee_eligible:
                committee_matches = search_committee(
                    query_vector, exclude_bill_nos=exclude_bill_nos, k=3
                )
                if committee_matches and (
                    best is None
                    or committee_matches[0]["similarity"] > best["similarity"]
                ):
                    best = committee_matches[0]
        if best is None:
            continue
        # 실측(2215954): committee_search 호출 자체를 게이트로 막아도,
        # _search_whole_db(전체 3,346개, 무제한)가 같은 committee-family
        # 항목을 독자적으로 찾아내 낮은 임계값(0.60)을 그대로 적용받는
        # 우회가 있었다. best의 family만으로 임계값을 정하지 말고,
        # committee_eligible(조문 원문에 위촉·수당 신호가 실제로 있었는지)도
        # 같이 요구해야 한다.
        # best_from_committee를 별도 플래그로 추적하면 이후 루프에서 같은
        # 항목이 whole_db 검색에도 걸려 덮어써지며 플래그만 틀어지는 경합이
        # 있었다(실측: 2214537 제6조 — best는 정확히 committee 항목인데
        # 플래그만 False로 남음). best 자체의 family로 직접 판단해 제거.
        threshold = (
            _PRESENT_MIN_SIMILARITY_COMMITTEE
            if best.get("family") == "committee" and committee_eligible
            else _PRESENT_MIN_SIMILARITY
        )
        if best["similarity"] < threshold:
            continue
        missing = [
            v.get("name", "")
            for v in best["variables"]
            if v.get("value") is None and v.get("name")
        ]
        # 실측(2213848): 선례 위원수(11명) 대신 조문 원문의 "30명 이내"를
        # 쓰면 오차가 -52.2%→+30.4%로 준다(회의횟수·단가는 선례값이 정확
        #했음). committee 매칭일 때만 조문에서 위원정수를 뽑아 같이 보여준다
        # — 자동으로 대체 계산하지는 않는다(범위/델타형은 그대로 오차가
        # 날 수 있어 사람이 최종 판단하도록 병기만 한다).
        stated_size = (
            extract_committee_size(source_text_for_gate)
            if best.get("family") == "committee"
            else None
        )
        suggestions.append(
            FormulaSuggestion(
                article_ref=article_ref,
                description=description,
                matched_bill_no=best["bill_no"],
                matched_item_name=best["item_name"],
                similarity=best["similarity"],
                formula=best["formula"],
                matched_category=best.get("category", ""),
                variables=best["variables"],
                missing_value_names=missing,
                article_stated_committee_size=stated_size,
            )
        )
    return _dedupe_by_matched_item(suggestions)


def _dedupe_by_matched_item(
    suggestions: list[FormulaSuggestion],
) -> list[FormulaSuggestion]:
    """같은 매칭 항목(같은 위원회·같은 산식)을 가리키는 여러 조문 제안을 하나로 합친다.

    실측(2125736): 한 위원회의 설치·회의·소위·운영세칙 등 여러 조문이 전부
    같은 DB 항목(2124164)에 매칭돼 12건이 나왔는데, 실제로는 하나의 비용
    항목이었다. LLM 판단을 건드리지 않는 순수 기계적 후처리로 정리한다.
    """
    best_by_key: dict[tuple[str, str], FormulaSuggestion] = {}
    article_refs_by_key: dict[tuple[str, str], list[str]] = {}
    for suggestion in suggestions:
        key = (suggestion.matched_bill_no, suggestion.matched_item_name)
        article_refs_by_key.setdefault(key, []).append(suggestion.article_ref)
        current_best = best_by_key.get(key)
        if current_best is None or suggestion.similarity > current_best.similarity:
            best_by_key[key] = suggestion
    deduped = []
    for key, suggestion in best_by_key.items():
        merged_refs = ", ".join(dict.fromkeys(article_refs_by_key[key]))
        deduped.append(
            FormulaSuggestion(
                article_ref=merged_refs,
                description=suggestion.description,
                matched_bill_no=suggestion.matched_bill_no,
                matched_item_name=suggestion.matched_item_name,
                similarity=suggestion.similarity,
                formula=suggestion.formula,
                matched_category=suggestion.matched_category,
                variables=suggestion.variables,
                missing_value_names=suggestion.missing_value_names,
                article_stated_committee_size=suggestion.article_stated_committee_size,
            )
        )
    deduped.sort(key=lambda s: -s.similarity)
    return deduped
