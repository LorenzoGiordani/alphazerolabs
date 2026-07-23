"""Client REST minimale per Propr (onchain prop firm su Hyperliquid).

Solo gli endpoint che servono a propr_paper.py: account, posizioni, ordini.
Legge PROPR_API_KEY da env. Vedi https://github.com/XBorgLabs/propr-docs.
"""
import os

import requests

BASE_URL = "https://api.propr.xyz/v1"
ACTIVE_ORDER_STATUSES = ("pending", "open", "partially_filled")
ORDER_PAGE_LIMIT = 20


class ProprError(RuntimeError):
    pass


class ProprClient:
    def __init__(self, api_key: str | None = None, *, read_only: bool = False):
        self.api_key = api_key or os.environ.get("PROPR_API_KEY")
        if not self.api_key:
            raise ProprError("PROPR_API_KEY non impostata")
        self.read_only = read_only
        self.account_id: str | None = None
        self.active_attempt: dict | None = None

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def _req(self, method: str, path: str, **kw) -> dict:
        if self.read_only and method.upper() != "GET":
            raise ProprError(f"client read-only: {method.upper()} {path} bloccato")
        r = requests.request(method, f"{BASE_URL}{path}", headers=self._headers(), timeout=20, **kw)
        if r.status_code not in (200, 201):
            raise ProprError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def setup(self, *, expected_account_id: str | None = None,
              expected_challenge_slug: str | None = None,
              expected_competition_id: str | None = None,
              expected_competition_slug: str | None = None) -> str:
        """Trova e vincola l'account attivo challenge oppure competition."""
        if expected_competition_id or expected_competition_slug:
            if not (expected_account_id and expected_competition_id
                    and expected_competition_slug):
                raise ProprError("pin competition incompleto")
            # La bot API non elenca le participation competition per API key.
            # Come l'SDK ufficiale, usa quindi il pin account diretto; questa GET
            # prova anche che la chiave possiede ed e' autorizzata sul conto.
            account = self._req("GET", f"/accounts/{expected_account_id}")
            if not isinstance(account, dict) or "balance" not in account:
                raise ProprError("account competition non accessibile")
            observed_account_id = account.get("accountId")
            allowed_account_ids = {
                expected_account_id,
                f"urn:prp-account:{expected_account_id}",
            }
            if observed_account_id not in allowed_account_ids:
                raise ProprError(f"account competition inatteso: {observed_account_id}")
            competition = self._req(
                "GET", f"/competitions/{expected_competition_slug}",
            )
            if not isinstance(competition, dict):
                raise ProprError("metadati competition non validi")
            attempt = {
                "accountId": expected_account_id,
                "competitionId": expected_competition_id,
                "status": "active",
                "competition": competition,
                "challenge": {
                    "slug": f"competition:{expected_competition_slug}",
                    "initialBalance": competition.get("initialBalance"),
                },
            }
        else:
            attempts = self._req(
                "GET", "/challenge-attempts", params={"status": "active"},
            ).get("data", [])
            if not attempts:
                raise ProprError("nessuna challenge attiva")

            if expected_challenge_slug:
                attempts = [
                    a for a in attempts
                    if a.get("challenge", {}).get("slug") == expected_challenge_slug
                ]
                if not attempts:
                    raise ProprError(
                        f"challenge attiva attesa non trovata: {expected_challenge_slug}"
                    )
            if expected_account_id:
                attempts = [
                    a for a in attempts if a.get("accountId") == expected_account_id
                ]
                if len(attempts) != 1:
                    raise ProprError(
                        f"account attivo atteso non trovato: {expected_account_id}"
                    )
            attempt = attempts[0]

        if attempt.get("status") != "active":
            raise ProprError(f"account non attivo: {attempt.get('status')}")
        self.active_attempt = attempt
        self.account_id = attempt["accountId"]
        return self.account_id

    def get_account(self) -> dict:
        return self._req("GET", f"/accounts/{self.account_id}")

    def get_positions(
        self,
        status: str | None = "open",
        *,
        position_id: str | None = None,
        include_zero: bool = False,
    ) -> list[dict]:
        """Legge una vista completa e stabile delle posizioni per uno status."""
        positions: list[dict] = []
        seen_position_ids: set[str] = set()
        offset = 0
        expected_total: int | None = None
        while True:
            params = {
                "limit": ORDER_PAGE_LIMIT,
                "offset": offset,
            }
            if status:
                params["status"] = status
            if position_id:
                params["positionId"] = position_id
            payload = self._req(
                "GET",
                f"/accounts/{self.account_id}/positions",
                params=params,
            )
            if not isinstance(payload, dict):
                raise ProprError(f"risposta posizioni non valida per status={status}")
            page = payload.get("data")
            total = payload.get("total")
            response_offset = payload.get("offset")
            if not isinstance(page, list):
                raise ProprError(f"risposta posizioni incompleta per status={status}")
            if response_offset is not None and (
                not isinstance(response_offset, int) or response_offset != offset
            ):
                raise ProprError(f"offset posizioni inatteso per status={status}")
            if total is not None and (not isinstance(total, int) or total < 0):
                raise ProprError(f"totale posizioni non valido per status={status}")
            if expected_total is None and total is not None:
                expected_total = total
            elif total is not None and total != expected_total:
                raise ProprError(f"paginazione posizioni instabile per status={status}")
            for position in page:
                observed_position_id = (
                    position.get("positionId")
                    if isinstance(position, dict)
                    else None
                )
                if (
                    not isinstance(observed_position_id, str)
                    or not observed_position_id
                    or observed_position_id in seen_position_ids
                ):
                    raise ProprError(
                        f"paginazione posizioni duplicata per status={status}"
                    )
                seen_position_ids.add(observed_position_id)
            positions.extend(page)
            offset += len(page)
            if expected_total is not None:
                if offset > expected_total:
                    raise ProprError(
                        f"paginazione posizioni eccede total per status={status}"
                    )
                if offset == expected_total:
                    break
            if len(page) < ORDER_PAGE_LIMIT:
                if expected_total is not None and offset != expected_total:
                    raise ProprError(
                        f"paginazione posizioni incompleta per status={status}"
                    )
                break
        try:
            return (
                positions
                if include_zero
                else [
                    position
                    for position in positions
                    if float(position["quantity"]) != 0
                ]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProprError("quantity posizione non valida") from exc

    def get_orders(
        self,
        status: str = "open",
        *,
        order_id: str | None = None,
    ) -> list[dict]:
        """Legge una vista completa e stabile degli ordini per uno status."""
        orders: list[dict] = []
        seen_order_ids: set[str] = set()
        offset = 0
        expected_total: int | None = None
        while True:
            params = {
                "status": status,
                "limit": ORDER_PAGE_LIMIT,
                "offset": offset,
            }
            if order_id:
                params["orderId"] = order_id
            payload = self._req(
                "GET", f"/accounts/{self.account_id}/orders",
                params=params,
            )
            if not isinstance(payload, dict):
                raise ProprError(f"risposta ordini non valida per status={status}")
            page = payload.get("data")
            total = payload.get("total")
            response_offset = payload.get("offset")
            if not isinstance(page, list):
                raise ProprError(f"risposta ordini incompleta per status={status}")
            if response_offset is not None and (not isinstance(response_offset, int)
                                                or response_offset != offset):
                raise ProprError(f"offset ordini inatteso per status={status}")
            if total is not None and (not isinstance(total, int) or total < 0):
                raise ProprError(f"totale ordini non valido per status={status}")
            if expected_total is None and total is not None:
                expected_total = total
            elif total is not None and total != expected_total:
                raise ProprError(f"paginazione ordini instabile per status={status}")
            for order in page:
                order_id = order.get("orderId") if isinstance(order, dict) else None
                if not isinstance(order_id, str) or not order_id or order_id in seen_order_ids:
                    raise ProprError(f"paginazione ordini duplicata per status={status}")
                seen_order_ids.add(order_id)
            orders.extend(page)
            offset += len(page)
            if expected_total is not None:
                if offset > expected_total:
                    raise ProprError(f"paginazione ordini eccede total per status={status}")
                if offset == expected_total:
                    return orders
            if len(page) < ORDER_PAGE_LIMIT:
                if expected_total is not None and offset != expected_total:
                    raise ProprError(f"paginazione ordini incompleta per status={status}")
                return orders

    def get_active_orders(self) -> list[dict]:
        """Unisce tutti gli status che possono ancora eseguire un ordine."""
        active: dict[str, dict] = {}
        for status in ACTIVE_ORDER_STATUSES:
            for order in self.get_orders(status=status):
                order_id = order.get("orderId")
                if not isinstance(order_id, str) or not order_id:
                    raise ProprError(f"ordine attivo senza orderId per status={status}")
                active[order_id] = order
        return list(active.values())

    def get_trades(self, *, order_id: str) -> list[dict]:
        """Legge tutte le esecuzioni associate a un ordine."""
        trades: list[dict] = []
        seen_trade_ids: set[str] = set()
        offset = 0
        expected_total: int | None = None
        while True:
            payload = self._req(
                "GET", f"/accounts/{self.account_id}/trades",
                params={
                    "orderId": order_id,
                    "limit": ORDER_PAGE_LIMIT,
                    "offset": offset,
                },
            )
            if not isinstance(payload, dict):
                raise ProprError("risposta trades non valida")
            page = payload.get("data")
            total = payload.get("total")
            response_offset = payload.get("offset")
            if not isinstance(page, list):
                raise ProprError("risposta trades incompleta")
            if response_offset is not None and (
                not isinstance(response_offset, int) or response_offset != offset
            ):
                raise ProprError("offset trades inatteso")
            if total is not None and (not isinstance(total, int) or total < 0):
                raise ProprError("totale trades non valido")
            if expected_total is None and total is not None:
                expected_total = total
            elif total is not None and total != expected_total:
                raise ProprError("paginazione trades instabile")
            for trade in page:
                trade_id = trade.get("tradeId") if isinstance(trade, dict) else None
                if (
                    not isinstance(trade_id, str)
                    or not trade_id
                    or trade_id in seen_trade_ids
                ):
                    raise ProprError("paginazione trades duplicata")
                seen_trade_ids.add(trade_id)
            trades.extend(page)
            offset += len(page)
            if expected_total is not None:
                if offset > expected_total:
                    raise ProprError("paginazione trades eccede total")
                if offset == expected_total:
                    return trades
            if len(page) < ORDER_PAGE_LIMIT:
                if expected_total is not None and offset != expected_total:
                    raise ProprError("paginazione trades incompleta")
                return trades

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
                      quantity: str, reduce_only: bool = False, close_position: bool = False,
                      intent_id: str | None = None, position_id: str | None = None,
                      trigger_price: str | None = None) -> list[dict]:
        order = {
            "accountId": self.account_id,
            "intentId": intent_id or _ulid(),
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
        if position_id is not None:
            order["positionId"] = position_id
        if trigger_price is not None:
            order["triggerPrice"] = trigger_price
        return self._req("POST", f"/accounts/{self.account_id}/orders", json={"orders": [order]}).get("data", [])

    def cancel_order(self, order_id: str) -> dict:
        return self._req("POST", f"/accounts/{self.account_id}/orders/{order_id}/cancel")


def _ulid() -> str:
    from ulid import ULID
    return str(ULID())
