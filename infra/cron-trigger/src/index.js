// Control plane disattivato intenzionalmente: lo scheduler GitHub nativo possiede
// gli unici job di raccolta ancora ammessi. Nessun dispatch paper, Propr, ricerca,
// Evolution o provider parte da questo Worker.
const worker = {
  async scheduled(_event, _env, ctx) {
    ctx.waitUntil(Promise.resolve());
  },
};

export default worker;
