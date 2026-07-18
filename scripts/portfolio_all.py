"""Paper trading di TUTTE le strategie portfolio attive (engine:portfolio).

Runner dedicato per i book cross-asset dollar-neutral: ogni strategia viene
ribilanciata da scripts/portfolio_paper.py. Sostituisce i glob pattern
hard-coded nel cron/workflow — ogni futura portfolio (champion/challenger) viene
inclusa automaticamente via portfolio_active_specs(), niente più zombie per nome
file che non matcha un pattern (com'era xsmom-multihorizon-v1).

Uso: .venv/bin/python scripts/portfolio_all.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.lifecycle import portfolio_active_specs
from pipeline.live import perp_market_snapshot
from scripts.runtime_health import write_coverage

ROOT = Path(__file__).resolve().parent.parent
COVERAGE_DIR = ROOT / "paper" / "coverage"
MARK_SNAPSHOT_ENV = "PORTFOLIO_MARK_SNAPSHOT_PATH"


def required_lookback(spec: dict) -> int:
    """Barre necessarie; il child piu esigente scalda per primo la cache run."""
    pf = spec.get("portfolio", {})
    if pf.get("factor") == "liqimb":
        return 8
    values = list(pf.get("lookbacks_h") or [])
    values.extend(pf.get(name) for name in ("lookback_h", "vol_lookback_h")
                  if pf.get(name) is not None)
    return max([int(value) for value in values] or [8]) + 5


def main() -> None:
    active = sorted(portfolio_active_specs(), key=lambda item: required_lookback(item[1]),
                    reverse=True)
    if not active:
        print("nessuna strategia portfolio attiva (champion/challenger)")
        write_coverage("portfolio-all", [], [], output_dir=COVERAGE_DIR)
        return
    print(f"strategie portfolio attive: {len(active)}")
    failures = []
    successes = []
    try:
        snapshot = {"ok": True, "rows": perp_market_snapshot()}
    except Exception as exc:
        snapshot = {"ok": False, "error": str(exc)}
        print(f"snapshot mark HL condivisa fallita ({exc})", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="portfolio-marks-") as temp_dir:
        snapshot_path = Path(temp_dir) / "snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot))
        child_env = os.environ.copy()
        child_env[MARK_SNAPSHOT_ENV] = str(snapshot_path)
        for path, spec in active:
            sid = spec["id"]
            print(f"\n→ {sid} [{spec['status']}]")
            # Continua per osservare tutti i book, ma propaga il risultato aggregato:
            # la health gate deve poter bloccare un deploy parziale.
            r = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "portfolio_paper.py"), str(path)],
                env=child_env,
            )
            if r.returncode != 0:
                print(f"  ⚠ {sid} uscito con codice {r.returncode}", file=sys.stderr)
                failures.append(sid)
            else:
                successes.append(sid)
    write_coverage("portfolio-all", [spec["id"] for _, spec in active], successes,
                   output_dir=COVERAGE_DIR)
    if failures:
        raise SystemExit(f"portfolio runner falliti: {', '.join(failures)}")


if __name__ == "__main__":
    main()
