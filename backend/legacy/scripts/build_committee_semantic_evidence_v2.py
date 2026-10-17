"""Build a conservative local preview of the semantic evidence v2 layer.

Only evidence whose subject and measurement scope can be recovered from the
source sentence is emitted.  Ambiguous v1 atoms remain quarantined rather than
being rewritten.  This script does not write to Supabase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.legacy.committee.committee_component_evidence_engine import _compact, _price_value


PROFILE_PATH = ROOT / "backend/generated/committee_evidence_v1/committee_profiles.jsonl"
ATOM_PATH = ROOT / "backend/generated/committee_evidence_v1/committee_evidence_atoms.jsonl"
_BODY_NAME = re.compile(r"([가-힣A-Za-z0-9ㆍ·()]{2,60}(?:위원회|심의회|협의회))")
_ANNUAL_COUNT = re.compile(r"연(?:간|평균)?\s*(\d+(?:\.\d+)?)회")
_TOTAL_COUNT = re.compile(r"총\s*(\d+(?:\.\d+)?)회\s*개최")
_GUIDELINE_YEAR = re.compile(r"(20\d{2})년도.{0,35}(?:지침|편성)")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _key(prefix: str, *values: Any) -> str:
    payload = "|".join(str(value) for value in values)
    return f"{prefix}:{hashlib.sha256(payload.encode()).hexdigest()[:32]}"


def _last_body_before(text: str, marker: str) -> str | None:
    before = text[: text.find(marker)] if marker in text else text
    names = [match.group(1) for match in _BODY_NAME.finditer(before)]
    if not names:
        return None
    # Trim a possessive institution prefix while keeping the formal body.
    value = names[-1]
    for prefix in ("한국가스공사의", "현행국립정신병원의"):
        value = value.removeprefix(prefix)
    return value


def _meeting_actual(
    atom: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    text = _compact(str(atom.get("source_text") or ""))
    derivation = str(atom.get("derivation_type") or "")
    marker = "회의개최실적" if "회의개최실적" in text else "최근"
    explicit_actual = derivation == "reported_actual" and "실적" in text
    recent_total = "최근" in text and "개최되었" in text and _TOTAL_COUNT.search(text)
    if not (explicit_actual or recent_total):
        return None
    subject_name = _last_body_before(text, marker)
    if not subject_name:
        return None
    total_match = _TOTAL_COUNT.search(text)
    annual_match = _ANNUAL_COUNT.search(text)
    if total_match:
        value = float(total_match.group(1))
    elif annual_match:
        value = float(annual_match.group(1))
    else:
        return None
    subject_key = _key("subject", "committee", subject_name)
    subject = {
        "subject_key": subject_key,
        "subject_kind": "committee",
        "subject_name": subject_name,
        "normalized_name": subject_name,
        "identity_status": "candidate",
    }
    observation = {
        "observation_key": _key(
            "observation",
            subject_key,
            "annual_meetings",
            value,
            text,
        ),
        "subject_key": subject_key,
        "source_profile_key": atom.get("profile_key"),
        "bill_id": atom.get("bill_id"),
        "source_item_key": atom.get("source_item_key"),
        "metric_role": "annual_meetings",
        "measurement_scope": "meetings_per_year",
        "normalized_value": value,
        "normalized_unit": "회/년",
        "evidence_kind": "reported_actual",
        "transfer_policy": "same_subject_only",
        "basis_year": atom.get("basis_year"),
        "source_ref": atom.get("source_ref"),
        "source_text": str(atom.get("source_text") or ""),
        "review_status": "candidate",
        "quality_flags": ["SUBJECT_EXTRACTED_FROM_SOURCE"],
        "target_profile_name": profile.get("normalized_name"),
    }
    return subject, observation


def _guideline_price(
    atom: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    text = _compact(str(atom.get("source_text") or ""))
    if "지침" not in text:
        return None
    value = _price_value(atom)
    if value is None:
        return None
    match = _GUIDELINE_YEAR.search(text)
    year = int(match.group(1)) if match else atom.get("basis_year")
    subject_name = f"정부 예산·기금 지침 {year or '연도미상'}"
    subject_key = _key("subject", "generic_guideline", subject_name)
    subject = {
        "subject_key": subject_key,
        "subject_kind": "generic_guideline",
        "subject_name": subject_name,
        "normalized_name": _compact(subject_name),
        "identity_status": "candidate",
    }
    observation = {
        "observation_key": _key(
            "observation",
            subject_key,
            "meeting_unit_price",
            value,
            text,
        ),
        "subject_key": subject_key,
        "source_profile_key": atom.get("profile_key"),
        "bill_id": atom.get("bill_id"),
        "source_item_key": atom.get("source_item_key"),
        "metric_role": "meeting_unit_price",
        "measurement_scope": "per_person_per_meeting",
        "normalized_value": value,
        "normalized_unit": "원/인·회",
        "evidence_kind": "official_guideline",
        "transfer_policy": "direct_guideline",
        "basis_year": year,
        "source_ref": atom.get("source_ref"),
        "source_text": str(atom.get("source_text") or ""),
        "review_status": "candidate",
        "quality_flags": ["PER_PERSON_SCOPE_CONFIRMED"],
    }
    return subject, observation


def build() -> dict[str, Any]:
    profiles = _jsonl(PROFILE_PATH)
    atoms = _jsonl(ATOM_PATH)
    by_profile = {str(row["profile_key"]): row for row in profiles}
    subjects: dict[str, dict[str, Any]] = {}
    observations: dict[str, dict[str, Any]] = {}
    links: dict[str, dict[str, Any]] = {}
    for atom in atoms:
        profile = by_profile.get(str(atom.get("profile_key") or ""), {})
        extracted = None
        if atom.get("evidence_role") == "annual_meetings":
            extracted = _meeting_actual(atom, profile)
        elif atom.get("evidence_role") == "meeting_unit_price":
            extracted = _guideline_price(atom)
        if not extracted:
            continue
        subject, observation = extracted
        subjects[subject["subject_key"]] = subject
        observations[observation["observation_key"]] = observation
        if (
            subject["subject_kind"] == "committee"
            and subject["normalized_name"] != profile.get("normalized_name")
        ):
            link_key = _key(
                "link",
                profile.get("profile_key"),
                subject["subject_key"],
                observation["metric_role"],
            )
            links[link_key] = {
                "link_key": link_key,
                "target_profile_key": profile.get("profile_key"),
                "evidence_subject_key": subject["subject_key"],
                "link_type": "explicit_citation",
                "evidence_role": observation["metric_role"],
                "source_quote": observation["source_text"],
                "label_status": "candidate",
            }
    return {
        "subjects": list(subjects.values()),
        "observations": list(observations.values()),
        "links": list(links.values()),
        "summary": {
            "subjects": len(subjects),
            "observations": len(observations),
            "links": len(links),
            "reported_actual_observations": sum(
                row["evidence_kind"] == "reported_actual"
                for row in observations.values()
            ),
            "guideline_observations": sum(
                row["evidence_kind"] == "official_guideline"
                for row in observations.values()
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
