from pathlib import Path

from backend.scripts.build_committee50_manifest import build_manifest


def test_real_committee50_manifest_is_complete() -> None:
    manifest = build_manifest()
    summary = manifest["summary"]

    assert summary["case_count"] == 50
    assert summary["source_pdf_count"] == 50
    assert summary["answer_pdf_count"] == 50
    assert summary["prior_diagnosis_count"] == 50
    assert summary["structured_label_count"] == 40
    assert len(summary["needs_structured_label"]) == 10

    assert all(case["answer_pdf"]["access_policy"] == "evaluator_only" for case in manifest["cases"])
    assert all(case["source_pdf"]["sha256"] for case in manifest["cases"])
    assert all(case["answer_pdf"]["sha256"] for case in manifest["cases"])


def test_manifest_uses_readme_order() -> None:
    manifest = build_manifest()
    indices = [case["index"] for case in manifest["cases"]]
    assert indices == list(range(1, 51))
    assert manifest["cases"][0]["bill_no"] == "2124118"
    assert manifest["cases"][-1]["bill_no"] == "2217718"
