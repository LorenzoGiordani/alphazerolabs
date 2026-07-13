"""Create and validate the fail-closed runtime health manifest."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "paper" / "health.json"
DEFAULT_COVERAGE_DIR = ROOT / "paper" / "coverage"
SCHEMA_VERSION = 1
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware_timestamp(value: object) -> bool:
    try:
        return datetime.fromisoformat(value).tzinfo is not None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp, path)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def _parse_checks(values: list[str], critical: bool) -> list[dict]:
    checks = []
    for value in values:
        name, separator, outcome = value.partition("=")
        if not separator or not _NAME_RE.fullmatch(name) or not outcome:
            raise ValueError(f"check non valido: {value!r}; atteso nome=outcome")
        checks.append({"name": name, "critical": critical, "outcome": outcome})
    return checks


def write_coverage(component: str, expected, observed, *, critical: bool = True,
                   output_dir: str | Path = DEFAULT_COVERAGE_DIR) -> dict:
    """Persist exact expected/observed ticker coverage for the current run."""
    if not _NAME_RE.fullmatch(component):
        raise ValueError(f"coverage component non valido: {component!r}")
    expected_set = {str(item) for item in expected}
    observed_set = {str(item) for item in observed}
    missing = sorted(expected_set - observed_set)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": os.getenv("RUNTIME_RUN_ID", "local"),
        "generated_at": _utcnow().isoformat(),
        "component": component,
        "critical": critical,
        "expected_count": len(expected_set),
        "observed_count": len(expected_set & observed_set),
        "missing": missing,
        "status": "fail" if missing else "pass",
    }
    if os.getenv("RUNTIME_COVERAGE_DISABLED") != "1":
        _atomic_json(Path(output_dir) / f"{component}.json", payload)
    return payload


def _coverage_valid(record: object, run_id: str | None = None) -> bool:
    return bool(
        isinstance(record, dict)
        and type(record.get("schema_version")) is int
        and record["schema_version"] == SCHEMA_VERSION
        and isinstance(record.get("run_id"), str) and bool(record["run_id"].strip())
        and (run_id is None or record.get("run_id") == run_id)
        and _aware_timestamp(record.get("generated_at"))
        and isinstance(record.get("component"), str)
        and _NAME_RE.fullmatch(record["component"])
        and type(record.get("critical")) is bool
        and record.get("status") in ("pass", "fail")
        and type(record.get("expected_count")) is int and record["expected_count"] >= 0
        and type(record.get("observed_count")) is int and record["observed_count"] >= 0
        and record["observed_count"] <= record["expected_count"]
        and isinstance(record.get("missing"), list)
        and all(isinstance(item, str) for item in record["missing"])
        and (record["status"] == "pass") == (len(record["missing"]) == 0)
        and len(record["missing"]) == record["expected_count"] - record["observed_count"]
    )


def _invalid_coverage(run_id: str, component: str) -> dict:
    safe = component if _NAME_RE.fullmatch(component) else "invalid-coverage"
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id,
            "generated_at": _utcnow().isoformat(), "component": safe,
            "critical": True, "expected_count": 1, "observed_count": 0,
            "missing": ["invalid_coverage_record"], "status": "fail"}


def load_coverage(run_id: str, directory: str | Path = DEFAULT_COVERAGE_DIR) -> list[dict]:
    records = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            records.append(_invalid_coverage(run_id, f"invalid-{path.stem}"))
            continue
        if isinstance(record, dict) and record.get("run_id") != run_id:
            continue
        if _coverage_valid(record, run_id):
            records.append(record)
        else:
            records.append(_invalid_coverage(run_id, f"invalid-{path.stem}"))
    return records


def build_manifest(critical: list[str], optional: list[str], *, run_id: str,
                   commit: str, now: datetime | None = None,
                   coverage: list[dict] | None = None,
                   required_coverage: list[str] | None = None) -> dict:
    checks = _parse_checks(critical, True) + _parse_checks(optional, False)
    coverage = coverage or []
    required_coverage = required_coverage or []
    if any(not _NAME_RE.fullmatch(name) for name in required_coverage):
        raise ValueError("nome required coverage non valido")
    if len(required_coverage) != len(set(required_coverage)):
        raise ValueError("required coverage duplicata")
    coverage = [c if _coverage_valid(c, run_id)
                else _invalid_coverage(run_id, f"invalid-{i}")
                for i, c in enumerate(coverage)]
    seen_coverage = {c["component"] for c in coverage}
    coverage.extend(_invalid_coverage(run_id, name)
                    for name in required_coverage if name not in seen_coverage)
    names = [check["name"] for check in checks]
    if len(names) != len(set(names)):
        raise ValueError("nomi check duplicati")
    failed_critical = [c["name"] for c in checks if c["critical"] and c["outcome"] != "success"]
    failed_optional = [c["name"] for c in checks
                       if not c["critical"] and c["outcome"] not in ("success", "skipped")]
    failed_coverage = [f"coverage:{c.get('component', 'unknown')}" for c in coverage
                       if c.get("critical") is True and c.get("status") != "pass"]
    warned_coverage = [f"coverage:{c.get('component', 'unknown')}" for c in coverage
                       if c.get("critical") is False and c.get("status") != "pass"]
    status = ("critical" if failed_critical or failed_coverage
              else ("degraded" if failed_optional or warned_coverage else "healthy"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (now or _utcnow()).isoformat(),
        "max_age_seconds": 7200,
        "run_id": run_id,
        "commit": commit,
        "status": status,
        "publish_allowed": not failed_critical and not failed_coverage,
        "checks": checks,
        "coverage": coverage,
        "required_coverage": required_coverage,
        "errors": failed_critical + failed_coverage,
        "warnings": failed_optional + warned_coverage,
    }


def validate_manifest(payload: object, *, max_age_seconds: int = 7200,
                      now: datetime | None = None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not isinstance(payload, dict):
        return False, ["health_invalid_schema"]
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != SCHEMA_VERSION:
        reasons.append("health_schema_version_invalid")
    if type(payload.get("max_age_seconds")) is not int or payload["max_age_seconds"] <= 0:
        reasons.append("health_max_age_invalid")
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"].strip():
        reasons.append("health_run_id_invalid")
    if not isinstance(payload.get("commit"), str) or not payload["commit"].strip():
        reasons.append("health_commit_invalid")
    try:
        generated = datetime.fromisoformat(payload["generated_at"])
        if generated.tzinfo is None:
            raise ValueError
        age = ((now or _utcnow()) - generated.astimezone(timezone.utc)).total_seconds()
        if age < -300 or age > max_age_seconds:
            reasons.append("health_stale")
    except (KeyError, TypeError, ValueError):
        reasons.append("health_timestamp_invalid")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        reasons.append("health_checks_missing")
    elif any(not isinstance(c, dict) or not isinstance(c.get("name"), str)
             or type(c.get("critical")) is not bool or not isinstance(c.get("outcome"), str)
             for c in checks):
        reasons.append("health_checks_invalid")
    elif any(c["critical"] and c["outcome"] != "success" for c in checks):
        reasons.append("health_critical_check_failed")
    coverage = payload.get("coverage")
    if not isinstance(coverage, list):
        reasons.append("health_coverage_invalid")
    elif any(not _coverage_valid(c, payload.get("run_id")) for c in coverage):
        reasons.append("health_coverage_invalid")
    elif any(c["critical"] and c["status"] != "pass" for c in coverage):
        reasons.append("health_critical_coverage_failed")
    required = payload.get("required_coverage")
    if (not isinstance(required, list)
            or any(not isinstance(name, str) or not _NAME_RE.fullmatch(name) for name in required)
            or len(required) != len(set(required))):
        reasons.append("health_required_coverage_invalid")
    elif isinstance(coverage, list):
        by_name = {c.get("component"): c for c in coverage if isinstance(c, dict)}
        if any(name not in by_name or by_name[name].get("status") != "pass" for name in required):
            reasons.append("health_required_coverage_missing")
    if payload.get("publish_allowed") is not True:
        reasons.append("health_publish_blocked")
    if payload.get("status") not in ("healthy", "degraded"):
        reasons.append("health_status_invalid")
    if payload.get("errors") != []:
        reasons.append("health_errors_present")
    if not isinstance(payload.get("warnings"), list):
        reasons.append("health_warnings_invalid")
    return not reasons, reasons


def load_health(path: str | Path, *, max_age_seconds: int = 7200,
                now: datetime | None = None) -> dict:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        payload, reasons = {}, ["health_missing"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        payload, reasons = {}, ["health_invalid_json"]
    else:
        _, reasons = validate_manifest(payload, max_age_seconds=max_age_seconds, now=now)
    if reasons:
        return {**(payload if isinstance(payload, dict) else {}), "status": "unknown",
                "publish_allowed": False, "validation_reasons": reasons}
    return {**payload, "validation_reasons": []}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record")
    record.add_argument("--critical", action="append", default=[])
    record.add_argument("--optional", action="append", default=[])
    record.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID", "local"))
    record.add_argument("--commit", default=os.getenv("GITHUB_SHA", "unknown"))
    record.add_argument("--require-coverage", action="append", default=[])
    record.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    validate = sub.add_parser("validate")
    validate.add_argument("path", type=Path)
    validate.add_argument("--max-age-seconds", type=int, default=7200)
    args = parser.parse_args()

    if args.command == "record":
        try:
            payload = build_manifest(args.critical, args.optional,
                                     run_id=args.run_id, commit=args.commit,
                                     coverage=load_coverage(args.run_id),
                                     required_coverage=args.require_coverage)
        except ValueError as exc:
            parser.error(str(exc))
        _atomic_json(args.output, payload)
        print(json.dumps(payload, indent=2))
        return 0 if payload["publish_allowed"] else 1

    health = load_health(args.path, max_age_seconds=args.max_age_seconds)
    print(json.dumps(health, indent=2))
    return 0 if health.get("publish_allowed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
