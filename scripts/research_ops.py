"""State machine locale per Daily Maker e Hourly Checker L1.

Le sole mutazioni consentite sono STATE.json e RUN_LOG.jsonl sotto l'ops root
esplicito. Pack, Maker e Checker devono gia esistere sotto runs/<pack_id>/ e
superare i contratti content-addressed di research_pack.py.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.live import atomic_write_text
from scripts.research_pack import (_parse_ts, content_hash, validate_checker,
                                   validate_maker, verify_pack)


SCHEMA_VERSION = 1
ROME = ZoneInfo("Europe/Rome")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def initial_state(*, started_at: datetime | None = None, status: str = "paused") -> dict:
    if status not in ("active", "paused"):
        raise ValueError("status iniziale non valido")
    started = ((started_at or _now()).astimezone(timezone.utc).isoformat()
               if status == "active" else None)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "kill_switch": False,
        "observation": {
            "started_at": started, "target_days": 14,
            "clean_streak_days": 0, "clean_dates": [],
            "last_reset_at": None,
            "status": "observing" if status == "active" else "pending_activation",
        },
        "latest": {
            "maker_pack_id": None, "pack_path": None, "maker_path": None,
            "maker_sha256": None, "maker_run_id": None, "maker_local_date": None,
            "checked_pack_id": None, "checker_path": None,
            "checker_verdict": None, "checker_run_id": None,
        },
        "counters": {
            "maker_runs": 0, "checker_runs": 0, "candidate": 0,
            "no_candidate": 0, "rejected": 0,
        },
    }


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: atteso oggetto JSON")
    return value


def _load_state(root: Path) -> dict:
    state = _load_json(root / "STATE.json")
    if (state.get("schema_version") != SCHEMA_VERSION
            or state.get("status") not in ("active", "paused")
            or type(state.get("kill_switch")) is not bool
            or not isinstance(state.get("latest"), dict)
            or not isinstance(state.get("counters"), dict)
            or not isinstance(state.get("observation"), dict)):
        raise ValueError("STATE.json non valido")
    return state


def _write_state(root: Path, state: dict) -> None:
    atomic_write_text(root / "STATE.json", json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def _append_event(root: Path, event: dict) -> None:
    path = root / "RUN_LOG.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush(); os.fsync(handle.fileno())


@contextmanager
def _locked(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _artifact(path: str | Path, root: Path) -> Path:
    artifact = Path(path).expanduser().resolve()
    runs = (root / "runs").resolve()
    if not artifact.is_file() or not artifact.is_relative_to(runs):
        raise ValueError(f"artefatto fuori da {runs} o assente: {artifact}")
    return artifact


def status(root: str | Path) -> dict:
    state = _load_state(Path(root).expanduser().resolve())
    latest = state["latest"]
    return {
        "status": state["status"], "kill_switch": state["kill_switch"],
        "work_pending": bool(latest["maker_pack_id"]
                             and latest["maker_pack_id"] != latest["checked_pack_id"]),
        "latest": latest, "observation": state["observation"],
        "counters": state["counters"],
    }


def record_maker(root: str | Path, pack_path: str | Path, maker_path: str | Path) -> dict:
    root = Path(root).expanduser().resolve()
    with _locked(root):
        state = _load_state(root)
        if state["status"] != "active" or state["kill_switch"]:
            raise ValueError("Research OS paused: kill switch attivo")
        latest = state["latest"]
        if latest["maker_pack_id"] and latest["maker_pack_id"] != latest["checked_pack_id"]:
            raise ValueError("backpressure: il pack precedente non e' ancora verificato")
        pack_file, maker_file = _artifact(pack_path, root), _artifact(maker_path, root)
        pack, maker = _load_json(pack_file), _load_json(maker_file)
        verify_pack(pack)
        result = validate_maker(pack, maker, now=_now())
        maker_local_date = _parse_ts(maker["created_at"], "maker.created_at").astimezone(ROME).date().isoformat()
        if latest.get("maker_local_date") == maker_local_date:
            raise ValueError(f"budget: esiste gia un Maker utile per {maker_local_date} Europe/Rome")
        if pack_file.parent != maker_file.parent or pack_file.parent.name != pack["pack_id"]:
            raise ValueError("pack e maker devono stare in runs/<pack_id>/")
        latest.update({
            "maker_pack_id": pack["pack_id"], "pack_path": str(pack_file),
            "maker_path": str(maker_file), "maker_sha256": result["maker_sha256"],
            "maker_run_id": maker["maker_run_id"], "maker_local_date": maker_local_date,
            "checked_pack_id": None,
            "checker_path": None, "checker_verdict": None, "checker_run_id": None,
        })
        state["counters"]["maker_runs"] += 1
        key = "candidate" if maker["outcome"] == "CANDIDATE" else "no_candidate"
        state["counters"][key] += 1
        _write_state(root, state)
        _append_event(root, {
            "ts": _now().isoformat(), "event": "maker_recorded",
            "pack_id": pack["pack_id"], "maker_run_id": maker["maker_run_id"],
            "maker_sha256": result["maker_sha256"], "outcome": maker["outcome"],
        })
        pack_file.chmod(0o444); maker_file.chmod(0o444)
        return {"recorded": True, "pack_id": pack["pack_id"], **result}


def _advance_observation(state: dict, verdict: str, checked_at: datetime) -> None:
    observation = state["observation"]
    if verdict == "REJECT":
        observation.update({"clean_streak_days": 0, "clean_dates": [],
                            "last_reset_at": checked_at.isoformat(), "status": "observing"})
        return
    local_day = checked_at.astimezone(ROME).date()
    dates = [date.fromisoformat(value) for value in observation["clean_dates"]]
    if dates and local_day == dates[-1]:
        return
    if dates and local_day != dates[-1] + timedelta(days=1):
        dates = []
        observation["last_reset_at"] = checked_at.isoformat()
    dates.append(local_day)
    observation["clean_dates"] = [value.isoformat() for value in dates]
    observation["clean_streak_days"] = len(dates)
    observation["status"] = ("complete" if len(dates) >= observation["target_days"]
                             else "observing")


def record_checker(root: str | Path, pack_path: str | Path, maker_path: str | Path,
                   checker_path: str | Path) -> dict:
    root = Path(root).expanduser().resolve()
    with _locked(root):
        state = _load_state(root); latest = state["latest"]
        if state["status"] != "active" or state["kill_switch"]:
            raise ValueError("Research OS paused: kill switch attivo")
        pack_file, maker_file = _artifact(pack_path, root), _artifact(maker_path, root)
        checker_file = _artifact(checker_path, root)
        pack, maker, checker = _load_json(pack_file), _load_json(maker_file), _load_json(checker_file)
        result = validate_checker(pack, maker, checker, now=_now())
        if (pack_file.parent != maker_file.parent or pack_file.parent != checker_file.parent
                or latest["maker_pack_id"] != pack["pack_id"]
                or latest["checked_pack_id"] == pack["pack_id"]
                or Path(latest["pack_path"]).resolve() != pack_file
                or Path(latest["maker_path"]).resolve() != maker_file
                or latest["maker_sha256"] != content_hash(maker)):
            raise ValueError("checker non corrisponde all'unico pack pendente")
        latest.update({
            "checked_pack_id": pack["pack_id"], "checker_path": str(checker_file),
            "checker_verdict": checker["verdict"], "checker_run_id": checker["checker_run_id"],
        })
        state["counters"]["checker_runs"] += 1
        if checker["verdict"] == "REJECT":
            state["counters"]["rejected"] += 1
        checked_at = _parse_ts(checker["checked_at"], "checker.checked_at")
        _advance_observation(state, checker["verdict"], checked_at)
        _write_state(root, state)
        _append_event(root, {
            "ts": _now().isoformat(), "event": "checker_recorded",
            "pack_id": pack["pack_id"], "checker_run_id": checker["checker_run_id"],
            "verdict": checker["verdict"], "clean_streak_days": state["observation"]["clean_streak_days"],
        })
        checker_file.chmod(0o444)
        return {"recorded": True, "pack_id": pack["pack_id"], **result,
                "clean_streak_days": state["observation"]["clean_streak_days"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, help="ops root esplicito")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    maker = commands.add_parser("record-maker")
    maker.add_argument("--pack", required=True); maker.add_argument("--maker", required=True)
    checker = commands.add_parser("record-checker")
    checker.add_argument("--pack", required=True); checker.add_argument("--maker", required=True)
    checker.add_argument("--checker", required=True)
    args = parser.parse_args()
    if args.command == "status":
        result = status(args.root)
    elif args.command == "record-maker":
        result = record_maker(args.root, args.pack, args.maker)
    else:
        result = record_checker(args.root, args.pack, args.maker, args.checker)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
