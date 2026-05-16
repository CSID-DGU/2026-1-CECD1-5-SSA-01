"""run_pipeline.py

비용추계 DB 구축 전체 파이프라인을 순서대로 실행한다.

단계:
  1. 국회 의안 수집 + 청킹          (build_assembly_rag_seed)
  2. RAG 데이터 Supabase 업로드     (upload_assembly_seed_to_supabase)
  3. 임베딩 생성 + Supabase 업데이트 (embed_chunks)
  4. TAG 구조화 추출                (extract_tag_structures)
  5. TAG 데이터 Supabase 업로드     (upload_tag_structures_to_supabase)

사용법:
    # 전체 실행 (50건)
    python -m backend.scripts.run_pipeline --max-bills 50

    # 수집 건너뛰고 기존 데이터로 나머지만
    python -m backend.scripts.run_pipeline --skip-collect

    # TAG만 10건 테스트
    python -m backend.scripts.run_pipeline --skip-collect --skip-embed --tag-limit 10
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import GENERATED_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="비용추계 DB 구축 전체 파이프라인")
    parser.add_argument("--age",          default="21",  help="국회 대수 (기본: 21)")
    parser.add_argument("--max-bills",    type=int, default=50, help="수집할 의안 수")
    parser.add_argument("--concurrency",  type=int, default=8,  help="병렬 다운로드 수")
    parser.add_argument("--seed-dir",     type=Path, default=GENERATED_DIR / "assembly_rag_seed")
    parser.add_argument("--tag-limit",    type=int, default=0, help="TAG 추출 의안 수 (0=전체)")
    parser.add_argument("--skip-collect", action="store_true", help="1단계 수집 건너뜀")
    parser.add_argument("--skip-upload",  action="store_true", help="2단계 RAG 업로드 건너뜀")
    parser.add_argument("--skip-embed",   action="store_true", help="3단계 임베딩 건너뜀")
    parser.add_argument("--skip-tag",     action="store_true", help="4·5단계 TAG 건너뜀")
    parser.add_argument("--skip-existing", action="store_true",
                        help="기존 bills.jsonl에 있는 bill_id 스킵 (재시작용)")
    return parser.parse_args()


def run_step(label: str, cmd: list[str]) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {label}")
    print(f"{'─' * 55}")
    t0 = time.time()
    result = subprocess.run(cmd, check=False)
    elapsed = time.time() - t0
    if result.returncode != 0:
        raise SystemExit(f"\n[실패] {label}  (exit {result.returncode})")
    print(f"  ✓ 완료  {elapsed:.1f}s")


def main() -> None:
    args = parse_args()
    py = sys.executable
    d  = str(args.seed_dir)

    print(f"\n{'=' * 55}")
    print("  비용추계 DB 구축 파이프라인")
    print(f"  대수={args.age}  최대={args.max_bills}건  경로={d}")
    print(f"{'=' * 55}")

    # 1. 수집 + 청킹 (ZIP 병렬 다운 + PyMuPDF 추출, fast 버전)
    if not args.skip_collect:
        cmd = [
            py, "-m", "backend.scripts.build_assembly_rag_seed_fast",
            "--age",         args.age,
            "--max-bills",   str(args.max_bills),
            "--concurrency", str(args.concurrency),
            "--output-dir",  d,
        ]
        if args.skip_existing:
            cmd.append("--skip-existing")
        run_step("1/5  국회 의안 수집 + 청킹 (ZIP 병렬)", cmd)

    # 2. RAG → Supabase (bills / documents / chunks / kosis)
    if not args.skip_upload:
        run_step("2/5  RAG 데이터 Supabase 업로드", [
            py, "-m", "backend.scripts.upload_assembly_seed_to_supabase",
            "--seed-dir", d,
            "--skip-files",   # Storage 파일 업로드는 별도 실행
        ])

    # 3. Azure 임베딩 생성 → assembly_chunks.embedding 업데이트
    if not args.skip_embed:
        run_step("3/5  임베딩 생성 + Supabase 업데이트", [
            py, "-m", "backend.scripts.embed_chunks",
            "--seed-dir", d,
        ])

    # 4. TAG 구조화 추출 (Gemini)
    if not args.skip_tag:
        tag_cmd = [
            py, "-m", "backend.scripts.extract_tag_structures",
            "--seed-dir", d,
        ]
        if args.tag_limit:
            tag_cmd += ["--limit", str(args.tag_limit)]
        run_step("4/5  TAG 구조화 추출 (Gemini)", tag_cmd)

        # 5. TAG → Supabase
        run_step("5/5  TAG 데이터 Supabase 업로드", [
            py, "-m", "backend.scripts.upload_tag_structures_to_supabase",
            "--seed-dir", d,
        ])

    print(f"\n{'=' * 55}")
    print("  파이프라인 완료")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    main()
