"""Fail-closed evidence contract for strategy promotion and execution.

Paper lifecycle (candidate/challenger/champion) is intentionally separate from
evidence readiness.  A strategy is evidence-ready only when a content-addressed
maker manifest and an independent checker receipt both verify.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path


SCHEMA_VERSION = 1
MIN_DSR = 0.95
APPROVE_VERDICT = "APPROVE_EVIDENCE_READY"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strategy_logic_sha256(spec: dict) -> str:
    """Hash the exact strategy subject, excluding only lifecycle ``status``.

    Changing candidate/challenger/champion does not invalidate evidence; any
    other mutation, including a backtest refresh, requires a new maker/checker
    pair.  ``default=str`` makes YAML dates deterministic in canonical JSON.
    """
    subject = copy.deepcopy(spec)
    subject.pop("status", None)
    payload = json.dumps(subject, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=str).encode()
    return _sha256_bytes(payload)


def _read_json(path: Path, label: str, reasons: list[str]) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        reasons.append(f"{label}_missing")
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        reasons.append(f"{label}_invalid_json")
        return None
    if not isinstance(value, dict):
        reasons.append(f"{label}_invalid_schema")
        return None
    return value


def _artifact(root: Path, block: object, label: str, reasons: list[str]) -> Path | None:
    if not isinstance(block, dict):
        reasons.append(f"{label}_invalid_schema")
        return None
    rel, expected = block.get("artifact_path"), block.get("artifact_sha256")
    if not isinstance(rel, str) or not rel or not isinstance(expected, str) or not _SHA_RE.fullmatch(expected):
        reasons.append(f"{label}_invalid_artifact_reference")
        return None
    root = root.resolve()
    try:
        path = (root / rel).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        reasons.append(f"{label}_artifact_outside_repo")
        return None
    try:
        observed = _sha256_bytes(path.read_bytes())
    except OSError:
        reasons.append(f"{label}_artifact_missing")
        return None
    if observed != expected:
        reasons.append(f"{label}_artifact_hash_mismatch")
        return None
    return path


def verify_evidence(spec: dict, root: str | Path) -> dict:
    """Return a stable public summary; every missing/malformed field blocks."""
    root = Path(root)
    sid = spec.get("id")
    reasons: list[str] = []
    result = {"verified": False, "status": "blocked", "reasons": reasons,
              "dsr": None, "maker_run_id": None, "checker_run_id": None}
    if not isinstance(sid, str) or not _ID_RE.fullmatch(sid):
        reasons.append("strategy_id_invalid")
        return result

    manifest_path = root / "evidence" / "manifests" / f"{sid}.json"
    checker_path = root / "evidence" / "checker" / f"{sid}.json"
    manifest = _read_json(manifest_path, "manifest", reasons)
    checker = _read_json(checker_path, "checker", reasons)
    if manifest is None or checker is None:
        return result

    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != SCHEMA_VERSION:
        reasons.append("manifest_schema_version_invalid")
    if manifest.get("strategy_id") != sid:
        reasons.append("manifest_strategy_mismatch")
    expected_logic = strategy_logic_sha256(spec)
    if manifest.get("strategy_logic_sha256") != expected_logic:
        reasons.append("strategy_logic_hash_mismatch")
    maker_run_id = manifest.get("maker_run_id")
    if not isinstance(maker_run_id, str) or not _RUN_ID_RE.fullmatch(maker_run_id):
        reasons.append("maker_run_id_invalid")
        maker_run_id = None
    result["maker_run_id"] = maker_run_id

    dsr = manifest.get("dsr")
    _artifact(root, dsr, "dsr", reasons)
    dsr_value = dsr.get("value") if isinstance(dsr, dict) else None
    if isinstance(dsr_value, bool) or not isinstance(dsr_value, (int, float)) or not math.isfinite(dsr_value):
        reasons.append("dsr_value_invalid")
    else:
        result["dsr"] = float(dsr_value)
        if not 0 <= dsr_value <= 1:
            reasons.append("dsr_value_invalid")
        elif dsr_value < MIN_DSR:
            reasons.append("dsr_below_threshold")

    oos = manifest.get("oos")
    _artifact(root, oos, "oos", reasons)
    if not isinstance(oos, dict) or oos.get("verdict") != "PASS":
        reasons.append("oos_not_pass")

    if type(checker.get("schema_version")) is not int or checker["schema_version"] != SCHEMA_VERSION:
        reasons.append("checker_schema_version_invalid")
    if checker.get("strategy_id") != sid:
        reasons.append("checker_strategy_mismatch")
    checker_run_id = checker.get("checker_run_id")
    if not isinstance(checker_run_id, str) or not _RUN_ID_RE.fullmatch(checker_run_id):
        reasons.append("checker_run_id_invalid")
        checker_run_id = None
    result["checker_run_id"] = checker_run_id
    if maker_run_id and checker.get("maker_run_id") != maker_run_id:
        reasons.append("checker_maker_run_mismatch")
    if maker_run_id and checker_run_id and checker_run_id == maker_run_id:
        reasons.append("checker_not_independent")
    try:
        manifest_sha = _sha256_bytes(manifest_path.read_bytes())
    except OSError:
        manifest_sha = None
    if checker.get("manifest_sha256") != manifest_sha:
        reasons.append("checker_manifest_hash_mismatch")
    if checker.get("verdict") != APPROVE_VERDICT:
        reasons.append("checker_not_approved")

    if not reasons:
        result.update(verified=True, status="verified")
    return result
