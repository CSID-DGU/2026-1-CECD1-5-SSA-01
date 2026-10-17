"""Local sidecar index for evidence buried inside precedent narratives.

TAG stores final cost items well, but an official estimate often cites a
budget, historical series or unit cost only inside its explanatory prose or a
table.  This module turns those passages into smaller searchable atoms without
changing the existing DB schema.

Retrieval is hybrid by design:

1. deterministic cost-scope and time holdout gates,
2. character n-gram recall only to keep embedding cost bounded,
3. embedding similarity for the final ranking.

Lexical overlap is never the final selector.
"""
from __future__ import annotations

import glob
import json
import math
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..analyzer_v2 import OPENAI_EMBED_MODEL, embed_batch
from ..estimator import tag_db
from .cache import get_or_create_json, stable_hash
EVIDENCE_INDEX_VERSION = "narrative-evidence-atoms-v2"
_GENERATED = Path("backend/generated")

_TABLE_UNIT_PATTERN = re.compile(
    r"단위\s*:\s*(백만원|억원|만원|천원|원)"
)
_MONEY_PATTERN = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>백만원|억원|만원|천원|원)"
    r"(?![가-힣])"
)
_MIXED_MONEY_PATTERN = re.compile(
    r"(?P<eok>\d[\d,]*(?:\.\d+)?)\s*억\s*"
    r"(?P<man>\d[\d,]*(?:\.\d+)?)\s*만원"
)
_YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_BUDGET_PATTERN = re.compile(
    r"예산|예산액|집행액|결산|운영비|운영경비|기관운영|기본경비|인건비|"
    r"사업비|수당|단가|재정소요|비용"
)
_ENTITY_PATTERN = re.compile(
    r"(?<![0-9A-Za-z가-힣])"
    r"([0-9A-Za-z가-힣·ㆍ]{2,30}?"
    r"(?:위원회|심의회|협의회|사무국|사무처|지원단|공단|공사|"
    r"연구원|진흥원|법원|검찰청|행정기관))"
)
_GENERIC_ENTITIES = {
    "위원회",
    "전문위원회",
    "소위원회",
    "운영위원회",
    "자문위원회",
    "심의위원회",
    "협의회",
    "사무국",
    "사무처",
    "지원단",
}
_NON_TRANSFERABLE_AMOUNT_PATTERN = re.compile(
    r"추가\s*재정\s*소요.{0,40}(?:없|발생하지\s*않)|"
    r"별도.{0,30}(?:소요|비용).{0,30}(?:없|발생하지\s*않)|"
    r"추계\s*(?:대상에서)?\s*제외|흡수\s*가능|기존\s*예산.{0,30}충당",
    re.DOTALL,
)
_EVIDENCE_CUE_PATTERNS = (
    ("historical", re.compile(r"최근\s*\d+\s*년|연평균|평균\s*수준|평균액|추이")),
    ("analogy", re.compile(r"유사\s*사례|유사사례|준용|참고하여|참고로")),
    ("table", re.compile(r"\[(?:표|참고)[^\]]*\]|\(\s*단위\s*:\s*(?:백만원|억원|만원|천원|원)\s*\)")),
    ("budget", re.compile(r"(?:예산|집행액|운영비|기본경비|인건비|사업비).{0,100}(?:백만원|억원|만원|천원|원)", re.DOTALL)),
)
_SCOPE_RULES = (
    (
        "support_office",
        re.compile(r"사무처|사무국|지원단|실무지원단|전담조직"),
    ),
    (
        "organization_operation",
        re.compile(r"기관운영|조직운영|운영예산|기본경비|전문성강화"),
    ),
    (
        "committee_operation",
        re.compile(r"위원회|심의회|협의회|위원단|자문단|회의수당|참석수당"),
    ),
    (
        "personnel",
        re.compile(r"인건비|보수|봉급|급여|정원|인력|직원|공무원|증원"),
    ),
    (
        "research_plan",
        re.compile(r"연구용역|정책연구|실태조사|기본계획|종합계획|조사[·ㆍ]?연구"),
    ),
    (
        "facility_system",
        re.compile(r"시설|설비|구축|전산|시스템|장비|건립|정보망"),
    ),
    (
        "subsidy",
        re.compile(r"지원금|보조금|출연금|급여지급|장려금"),
    ),
    (
        "tax_revenue",
        re.compile(r"세수|조세지출|감면액|면제액|비과세"),
    ),
)


@dataclass(frozen=True)
class EvidenceAtom:
    atom_id: str
    bill_no: str
    bill_name: str
    propose_date: str
    chunk_index: int
    cue: str
    entities: tuple[str, ...]
    scopes: tuple[str, ...]
    years: tuple[int, ...]
    units: tuple[str, ...]
    amount_mentions: tuple[tuple[float, str], ...]
    source_text: str
    source_hash: str
    amount_evidence: tuple[dict[str, Any], ...] = ()

    def embedding_text(self) -> str:
        header = (
            f"출처기관: {', '.join(self.entities) or '미상'}\n"
            f"비용범위: {', '.join(self.scopes)}\n"
            f"기준연도: {', '.join(map(str, self.years))}\n"
        )
        # Korean tables can consume several tokens per visible character.
        # Stay well below the embedding model's per-input token ceiling so one
        # oversized atom cannot force a 160-item batch into individual retries.
        return f"{header}{self.source_text}"[:1_200]


@dataclass(frozen=True)
class EvidenceSearchHit:
    atom: EvidenceAtom
    semantic_similarity: float
    recall_score: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self.atom)
        payload["semantic_similarity"] = self.semantic_similarity
        payload["recall_score"] = self.recall_score
        return payload


@lru_cache(maxsize=1)
def _cost_chunks() -> tuple[dict[str, Any], ...]:
    """Deduplicate generated copies and retain the richest text per chunk."""
    best: dict[tuple[str, int], dict[str, Any]] = {}
    for path in glob.glob(str(_GENERATED / "**/chunks.jsonl"), recursive=True):
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("documentType") or row.get("document_type") or "") != "cost_estimate":
                continue
            bill_no = str(row.get("billNo") or row.get("bill_no") or "")
            text = str(row.get("text") or row.get("content") or "").strip()
            if not bill_no or not text:
                continue
            try:
                chunk_index = int(row.get("chunkIndex") or row.get("chunk_index") or 0)
            except (TypeError, ValueError):
                chunk_index = 0
            key = (bill_no, chunk_index)
            current = best.get(key)
            if current and len(str(current["text"])) >= len(text):
                continue
            best[key] = {
                "bill_no": bill_no,
                "bill_name": str(row.get("billName") or row.get("bill_name") or ""),
                "propose_date": str(row.get("proposeDate") or row.get("propose_date") or ""),
                "chunk_index": chunk_index,
                "text": text,
            }
    return tuple(
        best[key]
        for key in sorted(best, key=lambda value: (value[0], value[1]))
    )


def _scope_tags(text: str) -> tuple[str, ...]:
    compact = re.sub(r"\s+", "", text)
    return tuple(
        scope
        for scope, pattern in _SCOPE_RULES
        if pattern.search(compact)
    )


def _candidate_windows(text: str) -> list[tuple[str, str]]:
    """Cut evidence-sized windows around general provenance/budget cues."""
    candidates: list[tuple[str, str]] = []
    for cue, pattern in _EVIDENCE_CUE_PATTERNS:
        last_position = -10_000
        kept_for_cue = 0
        for match in pattern.finditer(text):
            if match.start() - last_position < 450:
                continue
            before = 350 if cue != "table" else 950
            after = 1_250 if cue in {"historical", "analogy"} else 550
            start = max(0, match.start() - before)
            end = min(len(text), match.end() + after)
            value = text[start:end].strip()
            if len(value) < 100 or not _BUDGET_PATTERN.search(value):
                continue
            # A valid atom must retain an explicit unit or a table-level unit.
            if not (
                _TABLE_UNIT_PATTERN.search(value)
                or _MONEY_PATTERN.search(value)
            ):
                continue
            candidates.append((cue, value))
            last_position = match.start()
            kept_for_cue += 1
            if kept_for_cue >= 2:
                break
    # Different cue windows can be byte-identical; keep one deterministic atom.
    unique: dict[str, tuple[str, str]] = {}
    for cue, value in candidates:
        signature = stable_hash(re.sub(r"\s+", " ", value))
        unique.setdefault(signature, (cue, value))
    return list(unique.values())[:8]


def _money_matches(text: str) -> list[tuple[int, int, float, str]]:
    values: list[tuple[int, int, float, str]] = []
    occupied: list[tuple[int, int]] = []
    for match in _MIXED_MONEY_PATTERN.finditer(text):
        eok = float(match.group("eok").replace(",", ""))
        man = float(match.group("man").replace(",", ""))
        # Store mixed Korean notation in one canonical unit.
        values.append((match.start(), match.end(), eok * 100 + man / 100, "백만원"))
        occupied.append((match.start(), match.end()))
    for match in _MONEY_PATTERN.finditer(text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        try:
            value = float(match.group("value").replace(",", ""))
        except ValueError:
            continue
        values.append((match.start(), match.end(), value, match.group("unit")))
    return sorted(values, key=lambda row: (row[0], row[1]))


def _amount_mentions(text: str) -> tuple[tuple[float, str], ...]:
    values = [
        (value, unit)
        for _, _, value, unit in _money_matches(text)
    ]
    return tuple(values)


def _local_evidence_block(text: str, start: int, end: int) -> str:
    left_candidates = [
        text.rfind(marker, max(0, start - 500), start)
        for marker in ("\n❑", "\n◦", "\n－", "\n-", "\n")
    ]
    left = max(left_candidates)
    left = max(0, left + (1 if left >= 0 else 0))
    right_candidates = [
        position
        for marker in ("\n❑", "\n◦", "\n－", "\n-")
        if (position := text.find(marker, end, min(len(text), end + 600))) >= 0
    ]
    right = min(right_candidates) if right_candidates else min(len(text), end + 450)
    return text[left:right].strip()


def _amount_evidence(text: str) -> tuple[dict[str, Any], ...]:
    evidence: list[dict[str, Any]] = []
    for start, end, value, unit in _money_matches(text):
        context = _local_evidence_block(text, start, end)
        scopes = _scope_tags(context)
        primary_scope = scopes[0] if scopes else ""
        evidence.append(
            {
                "value": value,
                "unit": unit,
                "scopes": scopes,
                "primary_scope": primary_scope,
                "transferable": not bool(
                    _NON_TRANSFERABLE_AMOUNT_PATTERN.search(context)
                ),
                "context": context[:700],
            }
        )
    return tuple(evidence)


def _entities(text: str) -> tuple[str, ...]:
    values = {
        match.group(1)
        for match in _ENTITY_PATTERN.finditer(text)
        if match.group(1) not in _GENERIC_ENTITIES
        and len(match.group(1)) >= 5
    }
    return tuple(sorted(values, key=lambda value: (-len(value), value))[:8])


@lru_cache(maxsize=1)
def evidence_atoms() -> tuple[EvidenceAtom, ...]:
    atoms: list[EvidenceAtom] = []
    seen: set[tuple[str, str]] = set()
    for chunk in _cost_chunks():
        for window_index, (cue, source_text) in enumerate(
            _candidate_windows(str(chunk["text"])),
            start=1,
        ):
            source_hash = stable_hash(re.sub(r"\s+", " ", source_text))
            signature = (str(chunk["bill_no"]), source_hash)
            if signature in seen:
                continue
            seen.add(signature)
            scopes = _scope_tags(source_text)
            if not scopes:
                continue
            entities = _entities(source_text)
            years = tuple(
                sorted({int(value) for value in _YEAR_PATTERN.findall(source_text)})
            )
            units = tuple(
                sorted(
                    {
                        *_TABLE_UNIT_PATTERN.findall(source_text),
                        *(match.group("unit") for match in _MONEY_PATTERN.finditer(source_text)),
                    }
                )
            )
            atom_id = (
                f"EVA:{chunk['bill_no']}:{chunk['chunk_index']}:"
                f"{window_index}:{source_hash[:10]}"
            )
            atoms.append(
                EvidenceAtom(
                    atom_id=atom_id,
                    bill_no=str(chunk["bill_no"]),
                    bill_name=str(chunk["bill_name"]),
                    propose_date=str(chunk["propose_date"]),
                    chunk_index=int(chunk["chunk_index"]),
                    cue=cue,
                    entities=entities,
                    scopes=scopes,
                    years=years,
                    units=units,
                    amount_mentions=_amount_mentions(source_text),
                    source_text=source_text,
                    source_hash=source_hash,
                    amount_evidence=_amount_evidence(source_text),
                )
            )
    return tuple(
        sorted(atoms, key=lambda atom: (atom.bill_no, atom.chunk_index, atom.atom_id))
    )


def evidence_dataset_fingerprint() -> str:
    return stable_hash(
        {
            "version": EVIDENCE_INDEX_VERSION,
            "atoms": [
                (atom.atom_id, atom.source_hash, atom.propose_date)
                for atom in evidence_atoms()
            ],
        }
    )[:16]


def _char_ngrams(value: str, n: int = 3) -> set[str]:
    compact = re.sub(r"[^0-9A-Za-z가-힣]", "", value.lower())
    if len(compact) < n:
        return {compact} if compact else set()
    return {compact[index:index + n] for index in range(len(compact) - n + 1)}


def _recall_score(query: str, atom: EvidenceAtom) -> float:
    query_grams = _char_ngrams(query)
    atom_grams = _char_ngrams(atom.embedding_text())
    if not query_grams or not atom_grams:
        return 0.0
    overlap = len(query_grams & atom_grams)
    return overlap / math.sqrt(len(query_grams) * len(atom_grams))


def _query_embedding(query: str, *, refresh: bool) -> list[float] | None:
    value, _ = get_or_create_json(
        "evidence_atom_query_embeddings",
        {
            "version": EVIDENCE_INDEX_VERSION,
            "model": OPENAI_EMBED_MODEL,
            "query": query,
        },
        lambda: (embed_batch([query[:4_000]]) or [None])[0],
        refresh=refresh,
    )
    return value if isinstance(value, list) else None


def _candidate_embeddings(
    atoms: list[EvidenceAtom],
    *,
    refresh: bool,
) -> dict[str, list[float]]:
    payload = {
        "version": EVIDENCE_INDEX_VERSION,
        "model": OPENAI_EMBED_MODEL,
        "atoms": [(atom.atom_id, atom.source_hash) for atom in atoms],
    }

    def producer() -> dict[str, list[float]] | None:
        result: dict[str, list[float]] = {}
        # Keep the aggregate request below provider token ceilings.  Korean
        # prose often tokenises more densely than its character count.
        for start in range(0, len(atoms), 40):
            batch = atoms[start:start + 40]
            vectors = embed_batch([atom.embedding_text() for atom in batch])
            result.update(
                {
                    atom.atom_id: vector
                    for atom, vector in zip(batch, vectors)
                    if isinstance(vector, list) and vector
                }
            )
        return result or None

    value, _ = get_or_create_json(
        "evidence_atom_candidate_embeddings",
        payload,
        producer,
        refresh=refresh,
    )
    return value if isinstance(value, dict) else {}


def search_evidence_atoms(
    query: str,
    *,
    allowed_scopes: set[str],
    exclude_bill_nos: set[str],
    cutoff_date: str | None,
    k: int = 10,
    recall_k: int = 160,
    refresh: bool = False,
) -> list[EvidenceSearchHit]:
    """Search validated narrative atoms; final ordering is semantic-only."""
    excluded = {str(value) for value in exclude_bill_nos if value}
    eligible = [
        atom
        for atom in evidence_atoms()
        if atom.bill_no not in excluded
        and bool(set(atom.scopes) & allowed_scopes)
        and not (
            cutoff_date
            and (
                not atom.propose_date
                or atom.propose_date > cutoff_date
            )
        )
    ]
    recalled = sorted(
        (
            (_recall_score(query, atom), atom)
            for atom in eligible
        ),
        key=lambda pair: (-pair[0], pair[1].bill_no, pair[1].atom_id),
    )[:recall_k]
    recalled = [pair for pair in recalled if pair[0] > 0]
    if not recalled:
        return []
    query_vector = _query_embedding(query, refresh=refresh)
    candidates = [atom for _, atom in recalled]
    embeddings = _candidate_embeddings(candidates, refresh=refresh)
    if not query_vector or not embeddings:
        return []
    hits: list[EvidenceSearchHit] = []
    for recall_score, atom in recalled:
        vector = embeddings.get(atom.atom_id)
        if not vector:
            continue
        hits.append(
            EvidenceSearchHit(
                atom=atom,
                semantic_similarity=round(
                    tag_db._cosine(query_vector, vector),
                    4,
                ),
                recall_score=round(recall_score, 4),
            )
        )
    return sorted(
        hits,
        key=lambda hit: (
            -hit.semantic_similarity,
            hit.atom.bill_no,
            hit.atom.atom_id,
        ),
    )[:k]
