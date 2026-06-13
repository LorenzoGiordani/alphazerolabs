"""Carica un artefatto strategia YAML e lo compila in callback per l'engine.

Entry rule: composizione booleana di nomi segnale, "A AND B" / "A OR B"
(OR ha precedenza più bassa). Un segnale è "attivo" se != 0.

Direction: signal_vote (segno della somma dei segnali attivi) ·
with_breakout / follow:<sig> (segno di quel segnale) ·
contrarian_funding / contrarian:<sig> (segno opposto).

Sizing: exposure = min(max_leverage, risk_per_trade_pct / stop_pct).
Lo stato posizione (time stop) vive nella closure; se l'engine esce prima
per stop/target e il segnale è ancora attivo, la strategia rientra — accettato.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from backtest.signals import SIGNALS


def load(path: str | Path) -> dict:
    spec = yaml.safe_load(Path(path).read_text())
    for s in spec["signals"]:
        if s["name"] not in SIGNALS:
            raise ValueError(f"segnale sconosciuto: {s['name']} (registry: {list(SIGNALS)})")
    return spec


def compile_strategy(spec: dict, data: dict):
    """Ritorna (callback per Backtest.run, df segnali) — segnali precomputati vettoriali."""
    sigs = pd.DataFrame({
        s["name"]: SIGNALS[s["name"]](data, **s.get("params", {}))
        for s in spec["signals"]})

    active = _eval_rule(spec["entry"]["rule"], sigs)
    direction = _direction(spec["entry"]["direction"], sigs)
    # veto: segnali-gate che bloccano NUOVE entrate quando attivi (!=0).
    # Es. news_event come filtro di volatilità — non sposta la direzione, sospende.
    veto = spec["entry"].get("veto")
    if veto:
        names = [v.strip() for v in (veto if isinstance(veto, list) else veto.split(","))]
        blocked = np.logical_or.reduce([(sigs[n] != 0).to_numpy() for n in names])
        active = active & ~pd.Series(blocked, index=sigs.index)
    fire = (active & (direction != 0)).to_numpy()
    dir_arr = direction.to_numpy()

    stop_pct = float(spec["exit"]["stop_pct"])
    risk = spec["risk"]
    exposure = min(float(risk["max_leverage"]), float(risk["risk_per_trade_pct"]) / stop_pct)
    time_stop = int(spec["exit"].get("time_stop_h", 10**9))
    state = {"dir": 0.0, "opened_i": None}

    def strat(history: pd.DataFrame):
        i = len(history) - 1
        if state["dir"] != 0.0 and i - state["opened_i"] >= time_stop:
            state.update(dir=0.0, opened_i=None)
        if state["dir"] == 0.0 and fire[i]:
            state.update(dir=float(dir_arr[i]), opened_i=i)
        return {"exposure": state["dir"] * exposure,
                "stop_pct": stop_pct,
                "target_r": float(spec["exit"].get("target_r", 0)) or None}

    return strat, sigs


def _eval_rule(rule: str, sigs: pd.DataFrame) -> pd.Series:
    def term(name: str) -> pd.Series:
        return sigs[name.strip()] != 0
    or_parts = []
    for part in rule.split(" OR "):
        ands = [term(t) for t in part.split(" AND ")]
        or_parts.append(np.logical_and.reduce(ands))
    return pd.Series(np.logical_or.reduce(or_parts), index=sigs.index)


def _direction(spec_dir: str, sigs: pd.DataFrame) -> pd.Series:
    aliases = {"with_breakout": "follow:range_breakout", "contrarian_funding": "contrarian:funding_percentile"}
    d = aliases.get(spec_dir, spec_dir)
    if d == "signal_vote":
        return np.sign(sigs.sum(axis=1))
    mode, name = d.split(":")
    base = sigs[name]
    return base if mode == "follow" else -base
