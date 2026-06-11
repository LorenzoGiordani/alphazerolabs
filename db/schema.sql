-- DeFi AI Vault — trade journal + memoria (Supabase / Postgres + pgvector)
-- Design doc: sezione 4 (memoria e auto-miglioramento)

create extension if not exists vector;

-- Ogni decisione della pipeline, anche i veti (servono al Reviewer)
create table trades (
    id              bigint generated always as identity primary key,
    created_at      timestamptz not null default now(),
    symbol          text not null,                  -- es. 'BTC', 'xyz:SP500'
    direction       text not null check (direction in ('long', 'short')),
    size_usd        numeric not null check (size_usd > 0),
    leverage        numeric not null check (leverage between 1 and 3),
    entry_px        numeric,
    stop_px         numeric not null,               -- stop-loss obbligatorio
    target_px       numeric,
    thesis          text not null,                  -- tesi dello Strategist
    market_context  jsonb not null,                 -- brief research + segnali analyst + esito debate
    risk_decision   text not null check (risk_decision in ('approved', 'reduced', 'vetoed')),
    risk_notes      text,
    status          text not null default 'proposed'
                    check (status in ('proposed', 'vetoed', 'open', 'closed', 'failed')),
    -- esecuzione (Executor)
    tx_info         jsonb,                          -- order id, fill price, slippage
    opened_at       timestamptz,
    closed_at       timestamptz,
    exit_px         numeric,
    pnl_usd         numeric,
    -- post-mortem (Reviewer)
    review          text,
    review_verdict  text check (review_verdict in ('thesis_right', 'thesis_wrong', 'execution_issue', 'luck'))
);

create index on trades (symbol, created_at desc);
create index on trades (status);

-- Lezioni consolidate dal Reviewer, recall semantico per lo Strategist
create table lessons (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null default now(),
    lesson      text not null,
    source_trade_ids bigint[] not null default '{}',
    embedding   vector(1536),
    times_recalled int not null default 0
);

-- Snapshot equity per metriche live (Sharpe, drawdown su testnet)
create table equity_snapshots (
    ts          timestamptz primary key default now(),
    equity_usd  numeric not null,
    open_positions jsonb not null default '[]'
);
