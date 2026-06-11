"""Step 1 — universo asset Hyperliquid filtrato per liquidità.

Legge da MAINNET (volumi/OI reali — testnet ha liquidità finta), include:
- perps validator-operated (dex "")
- perps HIP-3 builder-deployed (es. xyz stock perps)
- spot

Output: stampa top N per volume 24h + salva data/universe.csv
"""

import sys
from datetime import datetime, timezone

import pandas as pd
import requests

INFO_URL = "https://api.hyperliquid.xyz/info"
TOP_N = 20
MIN_DAY_VOLUME_USD = 1_000_000  # sotto questo, troppo illiquido per noi


def info(payload: dict) -> dict | list:
    r = requests.post(INFO_URL, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_perps(dex: str = "") -> list[dict]:
    """Perps di un dex (dex="" = validator-operated, altrimenti HIP-3)."""
    meta, ctxs = info({"type": "metaAndAssetCtxs", "dex": dex})
    rows = []
    for asset, ctx in zip(meta["universe"], ctxs):
        if asset.get("isDelisted"):
            continue
        mark = float(ctx["markPx"]) if ctx["markPx"] else 0.0
        rows.append({
            "symbol": asset["name"],
            "dex": dex or "core",
            "kind": "perp",
            "max_leverage": asset["maxLeverage"],
            "mark_px": mark,
            "day_volume_usd": float(ctx["dayNtlVlm"]),
            "open_interest_usd": float(ctx["openInterest"]) * mark,
            "funding_hourly": float(ctx["funding"]),
        })
    return rows


def fetch_spot() -> list[dict]:
    meta, ctxs = info({"type": "spotMetaAndAssetCtxs"})
    tokens = {t["index"]: t["name"] for t in meta["tokens"]}
    rows = []
    for pair, ctx in zip(meta["universe"], ctxs):
        base, quote = pair["tokens"]
        rows.append({
            "symbol": f"{tokens[base]}/{tokens[quote]}",
            "dex": "spot",
            "kind": "spot",
            "max_leverage": 1,
            "mark_px": float(ctx["markPx"]) if ctx["markPx"] else 0.0,
            "day_volume_usd": float(ctx["dayNtlVlm"]),
            "open_interest_usd": 0.0,
            "funding_hourly": 0.0,
        })
    return rows


def main() -> None:
    rows = fetch_perps("")

    perp_dexs = info({"type": "perpDexs"})
    hip3 = [d["name"] for d in perp_dexs if d and d.get("name")]
    print(f"HIP-3 dexs trovati: {hip3}", file=sys.stderr)
    for dex in hip3:
        try:
            rows += fetch_perps(dex)
        except Exception as e:  # dex possono sparire/cambiare, non bloccare
            print(f"  dex {dex}: errore {e}", file=sys.stderr)

    rows += fetch_spot()

    df = pd.DataFrame(rows)
    df["fetched_at"] = datetime.now(timezone.utc).isoformat()
    df = df.sort_values("day_volume_usd", ascending=False)

    liquid = df[df.day_volume_usd >= MIN_DAY_VOLUME_USD]
    out = "data/universe.csv"
    df.to_csv(out, index=False)

    print(f"\nAsset totali: {len(df)} | liquidi (>{MIN_DAY_VOLUME_USD/1e6:.0f}M$/24h): {len(liquid)}")
    print(f"Salvato: {out}\n\nTop {TOP_N} per volume 24h:")
    cols = ["symbol", "dex", "kind", "day_volume_usd", "open_interest_usd", "max_leverage", "funding_hourly"]
    with pd.option_context("display.float_format", lambda v: f"{v:,.2f}"):
        print(liquid.head(TOP_N)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
