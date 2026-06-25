"""Test: robustezza del layer LLM (fail-fast su errori quota/auth).

`_ask_opencode` non deve restare appeso quando opencode-go/glm-5.2 restituisce
un errore non transiente (limite quota, auth). Questi errori si riconoscono dai
pattern OPENCODE_QUOTA_ERRORS (derivati da messaggi reali visti in produzione).
Il test verifica che i pattern catturino gli errori noti SENZA chiamare il
modello (no rete, no lentezza).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.decide import OPENCODE_QUOTA_ERRORS


def _hits(log_line: str) -> bool:
    return any(p in log_line.lower() for p in OPENCODE_QUOTA_ERRORS)


def test_weekly_usage_limit_caught():
    # messaggio reale visto in produzione (opencode-go, 25/06)
    line = ('timestamp=2026-06-25T17:38:36.614Z level=ERROR message="stream error" '
            'error.error="AI_APICallError: Weekly usage limit reached. '
            'Resets in 3 days. To continue using this model now, enable usage '
            'from your available balance"')
    assert _hits(line), "il pattern 'usage limit reached' non ha matchato il log reale"


def test_retry_error_caught():
    line = ('error.error="AI_RetryError: Failed after 3 attempts. Last error: '
            'Weekly usage limit reached."')
    assert _hits(line)


def test_insufficient_balance_caught():
    assert _hits("error: insufficient balance on account")
    assert _hits("insufficient_quota: you exceeded your current quota")


def test_unauthorized_caught():
    assert _hits("401 Unauthorized: invalid api key")
    assert _hits("authentication failed for provider")


def test_rate_limit_caught():
    assert _hits("rate_limit_error: too many requests")


def test_legit_output_not_false_positive():
    # un output LLM legittimo di trading NON deve matchare (no falsi positivi)
    legit = ("La tesi e' un breakout di trend su BTC con funding neutro. "
             "Direzione long, stop 3%. Il mercato ha fatto massimo storico.")
    assert not _hits(legit), "falso positivo su prosa di trading legittima"


def test_patterns_are_specific_enough():
    # i pattern sono applicati SOLO a stderr (log di sistema di opencode), MAI al
    # prompt o all'output del modello: quindi anche termini tecnici single-word
    # (unauthorized) sono sicuri. Verifichiamo solo che non siano substring banali
    # di prosa di trading (es. niente "limit", "rate", "key" da sole).
    too_generic = []
    for p in OPENCODE_QUOTA_ERRORS:
        # parola singola non tecnica (presente in prosa comune) = rischio
        if " " not in p and "_" not in p and p not in ("unauthorized",):
            too_generic.append(p)
    assert not too_generic, f"pattern troppo generici (falso positivo risk): {too_generic}"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception:
            fails += 1; print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{len(fns)-fails}/{len(fns)} passed")
    sys.exit(1 if fails else 0)
