# Research OS L1 — contratti

La validazione eseguibile è in `scripts/research_pack.py`; questo documento è
solo la forma leggibile dei due output LLM. Non aggiungere chiavi.

## Daily Maker

```json
{
  "kind": "daily-research-maker.v1",
  "pack_id": "sha256 copiato dal pack",
  "created_at": "ISO-8601 con timezone, entro expires_at",
  "maker_run_id": "identità univoca di questa task",
  "model": "gpt-5.6-sol oppure zai:<modello effettivo>",
  "outcome": "NO_CANDIDATE oppure CANDIDATE",
  "inventory": {
    "note_path": "wiki/Registry Segnali.md",
    "checked_at": "ISO-8601 con timezone",
    "consumed_strategy_ids": ["id realmente confrontati"],
    "novelty_summary": "confronto sintetico e verificabile"
  },
  "research_families": [
    {
      "family_id": "slug-univoco",
      "title": "nome",
      "hypothesis": "ipotesi falsificabile",
      "mechanism": "meccanismo causale o strutturale",
      "data_requirements": ["campi e clock point-in-time"],
      "source_urls": ["https://fonte-primaria"],
      "novelty_status": "novel oppure material_variant oppure consumed",
      "data_feasibility": "feasible oppure blocked",
      "blockers": []
    }
  ],
  "candidate": null,
  "guardrails": {
    "report_only": true,
    "no_trade": true,
    "no_backtest": true,
    "no_holdout": true,
    "no_strategy_activation": true,
    "no_repo_or_vault_write": true
  }
}
```

Nel runtime cloud, `inventory.note_path` identifica lo snapshot versionato in
`brain/` e `strategies/`; Obsidian resta canonico ma non viene copiato né scritto
da GitHub Actions.

Servono 5–8 famiglie con meccanismi distinti. Se `outcome` è `CANDIDATE`,
`candidate` è un solo oggetto con le chiavi seguenti:

```json
{
  "family_id": "una famiglia feasible e non consumed",
  "thesis": "tesi falsificabile",
  "prereg_scope": "scope congelabile",
  "data_contract": ["fonti, campi, clock e availability point-in-time"],
  "falsification": "regola di stop pre-P&L",
  "next_gate": "PREREG_REVIEW_ONLY"
}
```

## Hourly Checker

```json
{
  "kind": "hourly-independent-checker.v1",
  "pack_id": "sha256 copiato dal pack",
  "maker_sha256": "sha256 canonico esatto del maker",
  "maker_run_id": "id copiato dal maker",
  "checked_at": "ISO-8601 con timezone",
  "checker_run_id": "identità diversa dal maker",
  "verdict": "APPROVE_NO_CANDIDATE oppure APPROVE_PREREG_ONLY oppure REJECT",
  "blockers": [],
  "notes": "motivazione sintetica",
  "checks": {
    "pack_integrity": true,
    "maker_schema": true,
    "identity_separation": true,
    "inventory_novelty": true,
    "source_quality": true,
    "data_feasibility": true,
    "scope_report_only": true,
    "checker_no_forbidden_writes": true
  }
}
```

Un’approvazione richiede tutti i check `true` e zero blocker. `REJECT` richiede
almeno un blocker e può avere check `false`. Nessun verdetto autorizza P&L,
holdout, creazione di una strategy spec, paper/live, ordine o capitale.
