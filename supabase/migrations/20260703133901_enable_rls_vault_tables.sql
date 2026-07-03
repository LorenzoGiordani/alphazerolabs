-- Audit remediation (2026-07-03): abilita RLS sulle 4 tabelle del vault.
-- Erano in public senza RLS -> raggiungibili via Data API con la anon key.
--
-- Access model: la scrittura avviene SOLO via service_role (sync_supabase.py),
-- che bypassa RLS by-design. La dashboard pubblica e' statica (data.js
-- pre-generato), non legge Supabase client-side. Nessun consumer usa la anon key.
--
-- Effetto: nessuna policy = deny-by-default per anon/authenticated, service_role
-- invariato. Se in futuro serve lettura pubblica via API, aggiungere:
--   create policy "public read" on public.<t> for select to anon, authenticated using (true);

alter table public.trades            enable row level security;
alter table public.decisions         enable row level security;
alter table public.equity_snapshots  enable row level security;
alter table public.lessons           enable row level security;
