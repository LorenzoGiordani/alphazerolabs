---
target: dashboard lux
total_score: 33
p0_count: 0
p1_count: 0
timestamp: 2026-06-20T15-38-25Z
slug: dashboard-index-html
---
# Critique — LUX AI dashboard (dashboard/index.html)

## Design Health: 33/40 — Good (upper band)

Strong, intentional warm-terminal design. Most issues are P2/P3 polish, not structural.

| # | Heuristic | Score |
|---|-----------|-------|
| 1 Visibility status | 4 (LIVE badge, timestamp, next-run) |
| 2 Match real world | 4 (Italian plain-language, terms explained in Strategie) |
| 3 User control | 3 (read-only; tabs + back) |
| 4 Consistency | 3 (KPI "P&L realizzato" duplicated across two stat rows) |
| 5 Error prevention | 3 (low surface) |
| 6 Recognition | 3 (mobile tab overflow lacked affordance — fixed) |
| 7 Flexibility | 3 (no keyboard tab nav for Alex) |
| 8 Aesthetic/minimal | 3 (numbered eyebrows + KPI redundancy add minor noise) |
| 9 Error recovery | 3 |
| 10 Help/docs | 4 (Strategie tab = excellent contextual help) |

## Anti-patterns verdict
- LLM: NOT obviously AI-made. Genuine voice (Iowan serif + mono, refined amber/green/red, journal feed).
- Detector: em-dash-overuse (warning), numbered-section-markers 01–08 (advisory).
- Browser caught what detector missed: 361 side-stripe borders, contrast fail, 132ch line-length.

## Priority issues (all FIXED in this pass)
- [P2] Side-stripe borders (absolute ban) — 361× across .pcard/.dcard/.invalidation → full-border tint + inset panels.
- [P2] Contrast: micro-labels --text-4 = 2.90:1 (fail AA) → 4.63:1; --text-3 4.64→6.35.
- [P2] Thesis line-length 132ch desktop → max-width 68ch (76ch effective).
- [P2] Mobile nav tabs overflow with no affordance → right-edge fade mask <=760px.

## Remaining (deliberate / optional, P3)
- Numbered section markers 01–08 (defensible as guided sequence).
- em-dash usage in UI/thesis copy (legitimate Italian punctuation; thesis text is model-generated).
- KPI "P&L realizzato" shown in both top stat rows (minor redundancy).
