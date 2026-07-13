-- AlphaZero Labs — trade journal + memoria (Supabase / Postgres + pgvector)
-- Design doc: sezione 4 (memoria e auto-miglioramento)
-- Applicazione una-tantum (vedi scripts/sync_supabase.py per il sync incrementale):
--   supabase db push   (o:  psql "$DATABASE_URL" -f db/schema.sql)

create extension if not exists vector;

-- Ogni decisione della pipeline, anche i veti (servono al Reviewer). Una posizione
-- aperta (record 'open' del journal) + la sua chiusura ('close') = una riga.
create table trades (
    id              bigint generated always as identity primary key,
    source_key      text not null unique,            -- idempotenza sync: strategy|symbol|opened_at
    strategy        text not null,
    created_at      timestamptz not null default now(),
    symbol          text not null,                  -- es. 'BTC', 'xyz:SP500'
    direction       text not null check (direction in ('long', 'short')),
    size_usd        numeric not null check (size_usd > 0),
    leverage        numeric not null check (leverage >= 0),   -- notionale/equity: frazionario (sizing per rischio)
    entry_px        numeric,
    stop_px         numeric not null,               -- stop-loss obbligatorio
    target_px       numeric,
    thesis          text not null,                  -- tesi dello Strategist
    invalidation    text,                           -- clausola falsificabile
    market_context  jsonb not null default '{}',    -- record raw del journal (segnali, regime)
    risk_decision   text not null check (risk_decision in ('approved', 'reduced', 'vetoed')),
    risk_notes      text,
    status          text not null default 'open'
                    check (status in ('open', 'closed', 'failed', 'vetoed')),
    -- esecuzione / uscita (dal record 'close')
    exit_px         numeric,
    exit_reason     text,
    pnl_usd         numeric,
    opened_at       timestamptz,
    closed_at       timestamptz,
    -- post-mortem (Reviewer)
    review          text,
    review_verdict  text check (review_verdict in ('thesis_right', 'thesis_wrong', 'execution_issue', 'luck'))
);

create index on trades (strategy, opened_at desc);
create index on trades (symbol, created_at desc);
create index on trades (status);

-- Decisioni NON tradotte in posizione (veto del Risk Manager, max concorrenti, ecc.).
-- Servono al Reviewer per studiare i non-trade (regola #6: la tesi manca, ma il
-- contesto sì). Leggera: niente NOT NULL su direction/stop/thesis.
create table decisions (
    id           bigint generated always as identity primary key,
    source_key   text not null unique,              -- strategy|symbol|logged_at
    strategy     text not null,
    created_at   timestamptz not null default now(),
    symbol       text,
    reason       text,
    logged_at    timestamptz not null,
    context      jsonb not null default '{}'
);

-- Lezioni consolidate (review.py + promote.py), recall semantico per lo Strategist.
-- embedding NULL finché un job di indicizzazione non lo popola (pgvector 1536).
create table lessons (
    id              bigint generated always as identity primary key,
    source_key      text not null unique,           -- trade_key|logged_at
    created_at      timestamptz not null default now(),
    symbol          text,
    strategy        text,
    trade_key       text,
    verdict         text,
    lesson          text not null,
    tags            text[] not null default '{}',
    pnl_usd         numeric,
    embedding       vector(1536),
    times_recalled  int not null default 0,
    logged_at       timestamptz
);

create index on lessons using gin (tags);

-- Snapshot equity per metriche live (Sharpe, drawdown). Più strategie => source_key PK.
create table equity_snapshots (
    source_key      text primary key,               -- strategy|logged_at
    strategy        text not null,
    ts              timestamptz not null,
    equity_usd      numeric not null,
    open_positions  jsonb not null default '[]'
);

create index on equity_snapshots (strategy, ts desc);
