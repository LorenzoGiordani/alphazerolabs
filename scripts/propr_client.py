"""Client REST minimale per Propr (onchain prop firm su Hyperliquid).

Solo gli endpoint che servono a propr_paper.py: account, posizioni, ordini.
Legge PROPR_API_KEY da env. Vedi https://github.com/XBorgLabs/propr-docs.
"""
import os

import requests

BASE_URL = "https://api.propr.xyz/v1"


class ProprError(RuntimeError):
    pass


class ProprClient:
    def __init__(self, api_key: str | None = None, *, read_only: bool = False):
        self.api_key = api_key or os.environ.get("PROPR_API_KEY")
        if not self.api_key:
            raise ProprError("PROPR_API_KEY non impostata")
        self.read_only = read_only
        self.account_id: str | None = None

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def _req(self, method: str, path: str, **kw) -> dict:
        if self.read_only and method.upper() != "GET":
            raise ProprError(f"client read-only: {method.upper()} {path} bloccato")
        r = requests.request(method, f"{BASE_URL}{path}", headers=self._headers(), timeout=20, **kw)
        if r.status_code not in (200, 201):
            raise ProprError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def setup(self) -> str:
        """Trova l'accountId dalla challenge attempt attiva."""
        attempts = self._req("GET", "/challenge-attempts", params={"status": "active"}).get("data", [])
        if not attempts:
            raise ProprError("nessuna challenge attiva")
        self.account_id = attempts[0]["accountId"]
        return self.account_id

    def get_account(self) -> dict:
        return self._req("GET", f"/accounts/{self.account_id}")

    def get_positions(self, status: str = "open") -> list[dict]:
        data = self._req("GET", f"/accounts/{self.account_id}/positions", params={"status": status}).get("data", [])
        return [p for p in data if float(p["quantity"]) != 0]

    def get_margin_config(self, asset: str) -> dict:
        return self._req("GET", f"/accounts/{self.account_id}/margin-config/{asset}")

    def update_margin_config(self, config_id: str, asset: str, leverage: int, margin_mode: str = "cross") -> dict:
        return self._req("PUT", f"/accounts/{self.account_id}/margin-config/{config_id}",
                          json={"exchange": "hyperliquid", "asset": asset,
                                "marginMode": margin_mode, "leverage": leverage})

    def get_leverage_limits(self) -> dict:
        return self._req("GET", "/leverage-limits/effective")

    def max_leverage(self, asset: str) -> int:
        limits = self.get_leverage_limits()
        return limits.get("overrides", {}).get(asset, limits.get("defaultMax", 2))

    def create_order(self, *, side: str, position_side: str, order_type: str, asset: str,
                      quantity: str, reduce_only: bool = False, close_position: bool = False) -> list[dict]:
        order = {
            "accountId": self.account_id,
            "intentId": _ulid(),
            "exchange": "hyperliquid",
            "type": order_type,
            "side": side,
            "positionSide": position_side,
            "productType": "perp",
            "timeInForce": "IOC" if order_type == "market" else "GTC",
            "asset": asset,
            "base": asset,
            "quote": "USDC",
            "quantity": quantity,
            "reduceOnly": reduce_only,
            "closePosition": close_position,
        }
        return self._req("POST", f"/accounts/{self.account_id}/orders", json={"orders": [order]}).get("data", [])


def _ulid() -> str:
    from ulid import ULID
    return str(ULID())
