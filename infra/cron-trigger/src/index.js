// Cron Worker per il paper trading di GitHub Actions (lo scheduler nativo GitHub
// salta/ritarda le run su repo privato; questo Worker è il clock affidabile).
//
// Compiti principali:
//  1) HOURLY (cron "10 * * * *") → dispatch del paper-run completo (segnali, LLM, dashboard)
//  2) MONITOR (cron "*/3 * * * *") → legge le posizioni aperte, controlla i mid HL e,
//     SOLO se uno stop/target è sfiorato, dispatcha paper-exits.yml → uscite ~real-time
//     con minuti Actions quasi nulli (GitHub gira solo sui breach reali).
//  3) RESEARCH OS L1 → Maker alle 07:15 Europe/Rome e Checker ogni ora.
//
// Secret richiesto: GH_PAT — PAT fine-grained con permesso Actions: write sul repo.

const REPO = "LorenzoGiordani/alphazerolabs"; // nome attuale (ex lux-ai / defi-ai-vault)
const HOURLY_CRON = "10 * * * *";
const KRONOS_CRON = "30 5 * * *"; // 1x/giorno: rigenera la cache forecast Kronos (lux-0.1-beta)
const GDELT_CRON = "45 */6 * * *"; // 4x/giorno: rinfresca la cache eventi GDELT (desk geopolitics-v1)

export function isRomeMakerTime(scheduledTime) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Rome",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(scheduledTime));
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return value.hour === "07" && value.minute === "15";
}

export function workflowsForCron(cron, scheduledTime) {
  if (cron === HOURLY_CRON) return ["paper-run.yml", "hl-snapshot.yml", "research-checker.yml"];
  if (cron === KRONOS_CRON) return ["kronos-precompute.yml"];
  if (cron === GDELT_CRON) return ["gdelt-precompute.yml", "coinalyze-1h.yml"];
  return null;
}

async function dispatch(env, workflow) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_PAT}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "lux-paper-cron",
      },
      body: JSON.stringify({ ref: "main" }),
    },
  );
  const ok = res.status === 204; // 204 No Content = dispatch riuscito
  if (!ok) console.log(`dispatch ${workflow} failed`, res.status, await res.text());
  return ok;
}

// legge lo stato paper e i mid HL; se una posizione ha sfiorato stop/target
// lancia paper-exits. Crypto via allMids (batch, real-time); commodity (xyz:/cash:)
// via candleSnapshot (ultima candela 1h) — allMids non le include.
async function monitor(env) {
  const sres = await fetch(
    `https://api.github.com/repos/${REPO}/contents/paper/state.json?ref=main`,
    {
      headers: {
        Authorization: `Bearer ${env.GH_PAT}`,
        Accept: "application/vnd.github.raw",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "lux-paper-cron",
      },
    },
  );
  if (!sres.ok) { console.log("state fetch failed", sres.status); return false; }
  const state = await sres.json();

  const pos = [];
  for (const sid in state) {
    const ps = (state[sid] && state[sid].positions) || {};
    for (const sym in ps) {
      const p = ps[sym];
      if (p.stop_px == null) continue; // gamba book: la gestisce il rebalance
      pos.push({ sym, dir: p.direction, stop: p.stop_px, tgt: p.target_px });
    }
  }
  if (!pos.length) return false;

  const mres = await fetch("https://api.hyperliquid.xyz/info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "allMids" }),
  });
  const mids = mres.ok ? await mres.json() : {};

  // crypto: check via allMids (real-time mid)
  const hit = pos.filter((p) => {
    const m = parseFloat(mids[p.sym]);
    if (!isFinite(m)) return false;
    return p.dir === "long" ? (m <= p.stop || m >= p.tgt) : (m >= p.stop || m <= p.tgt);
  });

  // commodity + HIP-3 perp non in allMids: check via candleSnapshot (ultime 2 candele 1h).
  // allMids non include xyz:/cash: → fetch puntuale su high/low dell'ultima candela.
  const missing = pos.filter((p) => !hit.includes(p) && !isFinite(parseFloat(mids[p.sym])));
  if (missing.length) {
    const now = Date.now();
    const start = now - 3 * 3600_000; // 3h di lookback → almeno 2 candele chiuse
    const checks = await Promise.all(missing.map(async (p) => {
      try {
        const r = await fetch("https://api.hyperliquid.xyz/info", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ type: "candleSnapshot", req: { coin: p.sym, interval: "1h", startTime: start, endTime: now } }),
        });
        if (!r.ok) return null;
        const kl = await r.json();
        if (!Array.isArray(kl) || !kl.length) return null;
        const last = kl[kl.length - 1];
        const hi = parseFloat(last.h), lo = parseFloat(last.l);
        const breached = p.dir === "long" ? (lo <= p.stop || hi >= p.tgt) : (hi >= p.stop || lo <= p.tgt);
        return breached ? p : null;
      } catch { return null; }
    }));
    for (const c of checks) if (c) hit.push(c);
  }

  if (!hit.length) return false;
  console.log("breach:", hit.map((h) => h.sym).join(","), "→ dispatch paper-exits");
  return dispatch(env, "paper-exits.yml");
}

// Nessun handler fetch: il vecchio endpoint HTTP pubblico poteva provocare dispatch
// non autenticati. Le run manuali restano disponibili via workflow_dispatch GitHub.
const worker = {
  async scheduled(event, env, ctx) {
    // hl-snapshot e coinalyze-1h raccolgono dati forward-only non rigenerabili:
    // lo scheduler nativo GitHub li throttlava a ~3.5h invece che orari → buchi
    // negli storici. Piggyback sui cron già attivi (il clock affidabile è questo).
    const workflows = workflowsForCron(event.cron, event.scheduledTime);
    if (workflows !== null) {
      ctx.waitUntil(Promise.all(workflows.map((workflow) => dispatch(env, workflow))));
      return;
    }
    const tasks = [monitor(env)];
    if (isRomeMakerTime(event.scheduledTime)) tasks.push(dispatch(env, "research-maker.yml"));
    ctx.waitUntil(Promise.all(tasks));
  },
};

export default worker;
