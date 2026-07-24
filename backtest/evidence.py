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
import subprocess
from pathlib import Path

from scripts.propr_contract import TRUSTED_PATHS


SCHEMA_VERSION = 1
MIN_DSR = 0.95
APPROVE_VERDICT = "APPROVE_EVIDENCE_READY"
APPROVE_PROPR_PAPER_VERDICT = "APPROVE_PROPR_PAPER_EXECUTION"
PROPR_PAPER_SCOPE = "propr-free-trial-paper"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


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


def _implementation_matches(root: Path, commit: str) -> bool:
    try:
        ancestor = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"],
            check=False,
            capture_output=True,
        )
        unchanged = subprocess.run(
            ["git", "-C", str(root), "diff", "--quiet", commit, "--", *TRUSTED_PATHS],
            check=False,
            capture_output=True,
        )
    except OSError:
        return False
    return ancestor.returncode == 0 and unchanged.returncode == 0


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


def verify_propr_paper_evidence(
    spec: dict,
    root: str | Path,
    *,
    account_id: str,
    execution_contract: dict,
) -> dict:
    """Verify the separate, paper-only Propr execution receipt."""
    root = Path(root)
    sid = spec.get("id")
    reasons: list[str] = []
    result = {
        "verified": False,
        "status": "blocked",
        "scope": PROPR_PAPER_SCOPE,
        "reasons": reasons,
        "implementation_commit": None,
        "maker_run_id": None,
        "checker_run_id": None,
    }
    if not isinstance(sid, str) or not _ID_RE.fullmatch(sid):
        reasons.append("strategy_id_invalid")
        return result

    manifest_path = root / "evidence" / "propr" / "manifests" / f"{sid}.json"
    checker_path = root / "evidence" / "propr" / "checker" / f"{sid}.json"
    manifest = _read_json(manifest_path, "paper_manifest", reasons)
    checker = _read_json(checker_path, "paper_checker", reasons)
    if manifest is None or checker is None:
        return result

    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != SCHEMA_VERSION:
        reasons.append("paper_manifest_schema_version_invalid")
    if manifest.get("scope") != PROPR_PAPER_SCOPE:
        reasons.append("paper_scope_invalid")
    if manifest.get("strategy_id") != sid:
        reasons.append("paper_manifest_strategy_mismatch")
    if manifest.get("strategy_logic_sha256") != strategy_logic_sha256(spec):
        reasons.append("paper_strategy_logic_hash_mismatch")
    if spec.get("status") != "champion":
        reasons.append("paper_strategy_status_invalid")
    if spec.get("engine") != "portfolio":
        reasons.append("paper_strategy_engine_invalid")
    if manifest.get("paper_only") is not True:
        reasons.append("paper_only_not_enforced")
    if not isinstance(account_id, str) or not account_id or manifest.get("account_id") != account_id:
        reasons.append("paper_account_id_mismatch")
    if manifest.get("challenge_slug") != "free-trial":
        reasons.append("paper_challenge_invalid")
    initial_balance = manifest.get("initial_balance")
    if isinstance(initial_balance, bool) or initial_balance != 5000:
        reasons.append("paper_initial_balance_invalid")
    if manifest.get("execution_contract") != execution_contract:
        reasons.append("paper_execution_contract_mismatch")

    implementation_commit = manifest.get("implementation_commit")
    if not isinstance(implementation_commit, str) or not _COMMIT_RE.fullmatch(implementation_commit):
        reasons.append("paper_implementation_commit_invalid")
    else:
        result["implementation_commit"] = implementation_commit
        if not _implementation_matches(root, implementation_commit):
            reasons.append("paper_implementation_commit_mismatch")

    artifacts = manifest.get("trusted_artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(TRUSTED_PATHS):
        reasons.append("paper_trusted_artifacts_invalid")
        artifacts = {}
    for index, expected_path in enumerate(TRUSTED_PATHS):
        artifact_path = _artifact(
            root,
            artifacts.get(expected_path),
            f"paper_trusted_{index}",
            reasons,
        )
        if artifact_path is None:
            continue
        try:
            artifact_rel = artifact_path.relative_to(root.resolve()).as_posix()
        except ValueError:
            artifact_rel = ""
        if artifact_rel != expected_path:
            reasons.append(f"paper_trusted_{index}_path_invalid")

    maker_run_id = manifest.get("maker_run_id")
    if not isinstance(maker_run_id, str) or not _RUN_ID_RE.fullmatch(maker_run_id):
        reasons.append("paper_maker_run_id_invalid")
        maker_run_id = None
    result["maker_run_id"] = maker_run_id

    if type(checker.get("schema_version")) is not int or checker["schema_version"] != SCHEMA_VERSION:
        reasons.append("paper_checker_schema_version_invalid")
    if checker.get("scope") != PROPR_PAPER_SCOPE:
        reasons.append("paper_checker_scope_invalid")
    if checker.get("strategy_id") != sid:
        reasons.append("paper_checker_strategy_mismatch")
    checker_run_id = checker.get("checker_run_id")
    if not isinstance(checker_run_id, str) or not _RUN_ID_RE.fullmatch(checker_run_id):
        reasons.append("paper_checker_run_id_invalid")
        checker_run_id = None
    result["checker_run_id"] = checker_run_id
    if maker_run_id and checker.get("maker_run_id") != maker_run_id:
        reasons.append("paper_checker_maker_run_mismatch")
    if maker_run_id and checker_run_id and checker_run_id == maker_run_id:
        reasons.append("paper_checker_not_independent")
    try:
        manifest_sha = _sha256_bytes(manifest_path.read_bytes())
    except OSError:
        manifest_sha = None
    if checker.get("manifest_sha256") != manifest_sha:
        reasons.append("paper_checker_manifest_hash_mismatch")
    if checker.get("verdict") != APPROVE_PROPR_PAPER_VERDICT:
        reasons.append("paper_checker_not_approved")

    if not reasons:
        result.update(verified=True, status="verified")
    return result
