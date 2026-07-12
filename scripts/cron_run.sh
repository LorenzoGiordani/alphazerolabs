#!/bin/sh
# Run periodico della piattaforma (cron ogni 4h).
# Ordine: challenger signal-based → executor decisioni già registrate → dashboard.
# Le nuove operazioni LLM avvengono in task Codex/GPT-5.6, non in questo cron.
set -u
ROOT="/Users/lorenzogiordani/PROGETTI/defi-ai-vault"
UV="/opt/homebrew/bin/uv"
export LLM_RUNTIME_DISABLED=1
cd "$ROOT" || exit 1

# log persistente nel progetto, auto-trim a 10k righe (Mac con poco disco)
LOG="$ROOT/logs/cron.log"
mkdir -p "$ROOT/logs"
[ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 10000 ] && tail -n 5000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exec >> "$LOG" 2>&1
echo "=== cron run $(date -u '+%Y-%m-%d %H:%M') UTC ==="

stage() { echo "--- $1 [$(date -u '+%H:%M:%S')]"; }

stage "paper trading strategie attive"
"$UV" run scripts/paper_all.py
stage "executor agenti"
"$UV" run scripts/agents_paper.py --manage-only || true
"$UV" run scripts/agents_paper.py --manage-only --account agents-rr2-v1 --source agents-v1 --target-r 2.0 || true
# strategie engine:portfolio (xsmom-port, xsmom-multihorizon, highvol-port, combo, voltarget):
# runner dedicato via active_specs — niente più glob pattern (zombie multihorizon fixato).
"$UV" run scripts/portfolio_all.py

stage "brain"
"$UV" run scripts/brain_gen.py || true        # rigenera wiki markdown dai dati paper/

stage "backtest"
"$UV" run scripts/backtest_report.py    # basket multi-asset (sezione dashboard)

stage "dashboard"
"$UV" run scripts/dashboard.py

# auto-pubblica journal, brain e dashboard su GitHub (repo privata)
git add paper/ brain/ dashboard/index.html 2>/dev/null
if ! git diff --cached --quiet; then
    git commit -q -m "chore: paper run $(date -u '+%Y-%m-%d %H:%M') UTC [auto]"
    git push -q origin main || true
fi
