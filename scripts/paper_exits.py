"""Exit-check real-time (TP/SL). Gira spesso, lanciato dal Worker CF SOLO quando un
livello è sfiorato → minuti Actions quasi nulli. Per ogni posizione aperta valuta
stop/target sulla candela in formazione (come un vero ordine exchange) e chiude subito.

SOLO uscite: niente segnali, niente ingressi, niente LLM. Il time-stop (basato sul
tempo, non sul prezzo) resta all'hourly run — qui non urge.

Uso: uv run scripts/paper_exits.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.live import fetch_live
from scripts.paper_trade import STATE_FILE, update_position

NO_TIME_STOP = 10_000_000  # ore: le uscite a tempo le gestisce l'hourly run, non questo check


def main() -> None:
    if not STATE_FILE.exists():
        print("nessuno stato")
        return
    state = json.loads(STATE_FILE.read_text())
    closed = 0
    for sid, st in state.items():
        for sym in list(st.get("positions", {})):
            pos = st["positions"][sym]
            try:
                data = fetch_live(sym)
            except Exception as e:
                print(f"  {sid}/{sym}: fetch fallito ({e})", file=sys.stderr)
                continue
            newpos, st["equity"] = update_position(pos, data["candles"], NO_TIME_STOP,
                                                   st["equity"], data.get("forming"))
            if newpos is None:
                del st["positions"][sym]
                closed += 1
            else:
                st["positions"][sym] = newpos  # checked_until in-memory, persistito solo se c'è una chiusura

    if closed:
        STATE_FILE.write_text(json.dumps(state, indent=1, default=str))
        print(f"exit-check: {closed} posizioni chiuse")
    else:
        print("exit-check: nessuna uscita")


if __name__ == "__main__":
    main()
