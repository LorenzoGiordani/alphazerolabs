#!/bin/sh
# Run periodico della piattaforma (cron ogni 4h).
# Ordine: challenger signal-based → executor decisioni già registrate → dashboard.
# Le nuove operazioni LLM avvengono in task Codex/GPT-5.6, non in questo cron.
set -u
ROOT="/Users/lorenzogiordani/PROGETTI/defi-ai-vault"
UV="/opt/homebrew/bin/uv"
export LLM_RUNTIME_DISABLED=1
RUNTIME_RUN_ID="local-$(date -u '+%Y%m%dT%H%M%S')"
export RUNTIME_RUN_ID
cd "$ROOT" || exit 1
rm -rf "$ROOT/paper/coverage"
mkdir -p "$ROOT/paper/coverage"

# log persistente nel progetto, auto-trim a 10k righe (Mac con poco disco)
LOG="$ROOT/logs/cron.log"
mkdir -p "$ROOT/logs"
[ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 10000 ] && tail -n 5000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exec >> "$LOG" 2>&1
echo "=== cron run $(date -u '+%Y-%m-%d %H:%M') UTC ==="

stage() { echo "--- $1 [$(date -u '+%H:%M:%S')]"; }

stage "paper trading strategie attive"
paper_all=success
"$UV" run scripts/paper_all.py || paper_all=failure
stage "executor agenti"
agents_primary=success
"$UV" run scripts/agents_paper.py --manage-only || agents_primary=failure
agents_rr2=success
"$UV" run scripts/agents_paper.py --manage-only --account agents-rr2-v1 --source agents-v1 --target-r 2.0 || agents_rr2=failure
# strategie engine:portfolio (xsmom-port, xsmom-multihorizon, highvol-port, combo, voltarget):
# runner dedicato via active_specs — niente più glob pattern (zombie multihorizon fixato).
portfolio_all=success
"$UV" run scripts/portfolio_all.py || portfolio_all=failure

stage "promotion evidence gate"
promote=success
if [ "$paper_all" = success ] && [ "$portfolio_all" = success ]; then
  "$UV" run scripts/promote.py || promote=failure
else
  promote=skipped
fi

stage "exit-check"
exits=success
"$UV" run scripts/paper_exits.py || exits=failure

stage "brain"
brain=success
"$UV" run scripts/brain_gen.py || brain=failure        # rigenera wiki markdown dai dati paper/

stage "backtest"
report=success
"$UV" run scripts/backtest_report.py || report=failure    # basket multi-asset (sezione dashboard)

stage "runtime health"
"$UV" run scripts/runtime_health.py record \
  --run-id "$RUNTIME_RUN_ID" --commit "$(git rev-parse HEAD)" \
  --require-coverage "paper-all" --require-coverage "agents-v1" \
  --require-coverage "portfolio-all" --require-coverage "exit-check" \
  --critical "paper_all=$paper_all" --critical "agents_primary=$agents_primary" \
  --critical "portfolio_all=$portfolio_all" --critical "promote=$promote" \
  --critical "exits=$exits" --optional "agents_rr2=$agents_rr2" \
  --optional "brain=$brain" --optional "report=$report" || exit 1

stage "dashboard"
"$UV" run scripts/dashboard.py

# auto-pubblica journal, brain e dashboard su GitHub (repo privata)
git add paper/ brain/ dashboard/*.html dashboard/data.js dashboard/health.json 2>/dev/null
if ! git diff --cached --quiet; then
    git commit -q -m "chore: paper run $(date -u '+%Y-%m-%d %H:%M') UTC [auto]"
    git push -q origin main
fi
