from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from ..config import GENERATED_DIR


CACHE_DIR = GENERATED_DIR / "estimator_v2_cache"


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        return "missing"
    return digest.hexdigest()


def get_or_create_json(
    namespace: str,
    key_payload: Any,
    producer: Callable[[], Any],
    *,
    refresh: bool = False,
) -> tuple[Any, bool]:
    key = stable_hash(key_payload)
    target_dir = CACHE_DIR / namespace
    target = target_dir / f"{key}.json"
    if target.exists() and not refresh:
        try:
            return json.loads(target.read_text(encoding="utf-8")), True
        except (OSError, json.JSONDecodeError):
            pass

    # Regression and diagnosis should be able to replay all deterministic
    # stages against existing LLM/embedding caches without spending API
    # credits.  A cache miss is returned explicitly to the caller; it must
    # degrade to needs-evidence or fail the regression, never call the network.
    if os.getenv("ESTIMATOR_V2_OFFLINE", "").strip() == "1":
        return None, False

    value = producer()
    if value is None:
        return None, False

    target_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{key}.", suffix=".tmp", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return value, False
