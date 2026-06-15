// Cron Worker: trigger affidabile per il paper-run di GitHub Actions.
// Lo scheduler nativo di GitHub salta/ritarda le run schedulate; questo Worker
// (cron Cloudflare, affidabile) chiama workflow_dispatch ogni ora.
// Secret richiesto: GH_PAT — PAT fine-grained con permesso Actions: write sul repo.

const REPO = "LorenzoGiordani/defi-ai-vault";
const WORKFLOW = "paper-run.yml";

async function dispatch(env) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
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
  const ok = res.status === 204; // GitHub risponde 204 No Content al dispatch riuscito
  if (!ok) console.log("dispatch failed", res.status, await res.text());
  return ok;
}

export default {
  // tick orario via cron trigger
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
  // GET manuale per test/health: apri l'URL del Worker per forzare un dispatch
  async fetch(request, env) {
    const ok = await dispatch(env);
    return new Response(ok ? "dispatched\n" : "dispatch failed\n", {
      status: ok ? 200 : 502,
    });
  },
};
