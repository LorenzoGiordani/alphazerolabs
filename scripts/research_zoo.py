"""F2 piano integrazioni: sweep dei 456 fattori Alpha Zoo (Vibe-Trading, MIT)
sul basket crypto, con gate pre-registrato PRIMA di guardare i risultati.

Protocollo (Obsidian: "AlphaZero Labs — Piano test integrazioni esterne"):
  1. panel daily (resample da candele 1h locali), fwd return 1g e 7g
  2. per fattore: IC + random-control (permutation, alpha_t) su entrambi gli
     orizzonti — soglia 3.5 (Harvey-Liu-Zhu: 456 prove = multiple testing)
  3. sopravvissuti: alpha_t >= 3.5 (o <= -3.5 = candidato INVERSIONE)
     su almeno un orizzonte, E |overlap| <= 0.4 vs xsmom e highvol
     (overlap = rank-corr cross-section media col segnale live)
  4. aspettativa dichiarata: 0-2 sopravvissuti; zero = risultato valido

Output: paper/zoo_sweep.json (leaderboard completo) + stampa top/sopravvissuti.
Uso: uv run scripts/research_zoo.py [--months 12] [--shuffles 50]
"""
import argparse
import importlib
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backtest.stats import ic_random_control, rank_ic_series  # noqa: E402

CRYPTO = "BTC,ETH,SOL,XRP,SUI,NEAR,WLD,ZEC,CRV"
ALPHA_T = 3.5          # Harvey-Liu-Zhu, pre-registrato
MAX_OVERLAP = 0.4      # vs segnali live, pre-registrato


def daily_panel(symbols: list[str], months: int) -> dict[str, pd.DataFrame]:
    """OHLCV daily wide da candele 1h locali. amount = close*volume (proxy
    turnover quote), vwap daily = sum(close*vol)/sum(vol)."""
    frames: dict[str, dict] = {k: {} for k in
                               ("open", "high", "low", "close", "volume", "vwap", "amount")}
    for s in symbols:
        p = ROOT / f"data/candles/{s}.parquet"
        if not p.exists():
            continue
        c = pd.read_parquet(p).tail(months * 30 * 24).set_index("ts").sort_index()
        c = c[~c.index.duplicated()]
        d = pd.DataFrame({
            "open": c["open"].resample("1D").first(),
            "high": c["high"].resample("1D").max(),
            "low": c["low"].resample("1D").min(),
            "close": c["close"].resample("1D").last(),
            "volume": c["volume"].resample("1D").sum(min_count=1),
        })
        pv = (c["close"] * c["volume"]).resample("1D").sum(min_count=1)
        d["vwap"] = pv / d["volume"]
        d["amount"] = d["close"] * d["volume"]
        for k in frames:
            frames[k][s] = d[k]
    return {k: pd.DataFrame(v).dropna(how="all") for k, v in frames.items()}


def zoo_modules() -> list:
    mods = sorted((ROOT / "vendor/vibe_zoo/zoo").rglob("*.py"))
    return [m for m in mods if m.stem != "__init__" and not m.stem.startswith("_")]


def overlap(a: pd.DataFrame, b: pd.DataFrame) -> float:
    """Rank-corr cross-section media tra due panel segnale (overlap informativo)."""
    ic = rank_ic_series(a, b)
    return float(ic.mean()) if len(ic) else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=CRYPTO)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--shuffles", type=int, default=50)
    a = ap.parse_args()
    warnings.filterwarnings("ignore")

    panel = daily_panel(a.symbols.split(","), a.months)
    close = panel["close"]
    print(f"panel daily {close.shape[0]} giorni x {close.shape[1]} asset "
          f"({close.index.min():%Y-%m-%d} → {close.index.max():%Y-%m-%d})")
    fwd = {hz: close.pct_change(hz).shift(-hz) for hz in (1, 7)}
    # proxy dei segnali live per il gate di ortogonalita
    xsmom_sig = close.pct_change(7)
    highvol_sig = close.pct_change().rolling(30).std()

    rows, errors = [], 0
    for i, m in enumerate(zoo_modules(), 1):
        name = str(m.relative_to(ROOT)).replace("/", ".")[:-3]
        try:
            mod = importlib.import_module(name)
            meta = getattr(mod, "__alpha_meta__", {})
            if meta.get("requires_sector"):
                continue
            sig = mod.compute(panel)
            sig = sig.replace([np.inf, -np.inf], np.nan)
            if sig.notna().sum().sum() < 100:
                continue
            row = {"id": meta.get("id", m.stem), "zoo": m.parent.name,
                   "theme": ",".join(meta.get("theme", [])),
                   "ov_xsmom": round(overlap(sig, xsmom_sig), 3),
                   "ov_highvol": round(overlap(sig, highvol_sig), 3)}
            for hz in (1, 7):
                rc = ic_random_control(sig, fwd[hz], n_shuffles=a.shuffles, seed=hz)
                row[f"alpha_t_{hz}d"] = rc["alpha_t"]
                row[f"ic_{hz}d"] = rc["ic_mean"]
                row[f"cat_{hz}d"] = rc["category"]
            rows.append(row)
        except Exception:
            errors += 1
        if i % 50 == 0:
            print(f"  {i} moduli processati…", flush=True)

    df = pd.DataFrame(rows)
    df["best_abs_t"] = df[["alpha_t_1d", "alpha_t_7d"]].abs().max(axis=1)
    df = df.sort_values("best_abs_t", ascending=False)
    strong = df[(df[["alpha_t_1d", "alpha_t_7d"]].abs() >= ALPHA_T).any(axis=1)]
    ortho = strong[(strong["ov_xsmom"].abs() <= MAX_OVERLAP)
                   & (strong["ov_highvol"].abs() <= MAX_OVERLAP)]

    out = {"asof": datetime.now(timezone.utc).isoformat(),
           "protocol": {"alpha_t": ALPHA_T, "max_overlap": MAX_OVERLAP,
                        "n_shuffles": a.shuffles, "n_trials": len(df),
                        "months": a.months, "symbols": a.symbols},
           "source": "vendor/vibe_zoo (HKUDS/Vibe-Trading, MIT)",
           "counts": {"tested": len(df), "errors": errors,
                      "strong": len(strong), "survivors_ortho": len(ortho)},
           "survivors": ortho.to_dict("records"),
           "leaderboard_top50": df.head(50).to_dict("records")}
    (ROOT / "paper/zoo_sweep.json").write_text(json.dumps(out, indent=1))

    print(f"\ntestati {len(df)} fattori ({errors} errori) su {a.months}m")
    print(f"|alpha_t| >= {ALPHA_T}: {len(strong)}  →  ortogonali (|ov|<= {MAX_OVERLAP}): {len(ortho)}")
    cols = ["id", "zoo", "alpha_t_1d", "alpha_t_7d", "ic_7d", "ov_xsmom", "ov_highvol"]
    if len(ortho):
        print("\nSOPRAVVISSUTI (candidati sleeve / inversione):")
        print(ortho[cols].to_string(index=False))
    print("\nTOP 10 per |alpha_t| (anche non ortogonali):")
    print(df.head(10)[cols].to_string(index=False))
    print("\n→ paper/zoo_sweep.json")


if __name__ == "__main__":
    main()
