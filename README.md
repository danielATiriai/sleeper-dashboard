# Sleeper League Dashboard

Historical trends, team/player/trade analysis, and recommendations for a
**Sleeper dynasty fantasy-football league** — blending fantasy results with
**real NFL football** (player usage, advanced analytics, age/injury, team context).

Built for *"Fell-owship of the Ring"* (league `1237889751156011008`, 8-team
**superflex**, 0.5 PPR, seasons 2024–2025), but the pipeline is league-agnostic.

## Core idea

> **Fantasy stats grade the MANAGER. Real NFL stats + projections grade the PLAYERS and TEAM.**

- **Manager quality** (how well the human plays): scoring consistency, lineup
  efficiency / points left on the bench, luck vs. skill (all-play), waiver/trade/
  draft acumen.
- **Player & team quality** (how good the roster actually is): real-football usage
  and advanced analytics + forward-looking projections — *not* past fantasy points.
  An injured star is still a star: **availability is a separate risk, not a value
  penalty.**

Offseason-only projections (team environment, forward strength-of-schedule, depth
roles) are always shown with a **"projected"** badge — never presented as fact.

## Architecture

```
Python ETL (etl/)  ──►  static JSON (web/public/data/)  ──►  React SPA (web/)
```

- **`etl/`** — re-runnable pipeline. Pulls the Sleeper API (full multi-season
  history via `previous_league_id`) + nflverse real-NFL data, joins them on the
  DynastyProcess player-id crosswalk, computes every metric/label/recommendation,
  and emits slim JSON bundles. Scores come **only** from Sleeper `matchups`
  (league-accurate) — never the pre-baked `pts_ppr`.
- **`web/`** — React + Vite + TypeScript + Tailwind + Recharts. No backend, no
  runtime API calls; it just reads the JSON bundles.

## Run it

```bash
# 1. ETL — fetch data + compute analysis (writes web/public/data/*.json)
python3.12 -m venv etl/.venv
etl/.venv/bin/pip install -r etl/requirements.txt
etl/.venv/bin/python -m etl.build            # uses cached raw; add --fetch to re-pull
etl/.venv/bin/python -m pytest etl/tests     # optimal-lineup + pipeline sanity tests

# 2. Web
cd web && pnpm install
pnpm dev                                       # http://localhost:5173
pnpm build                                     # static bundle in web/dist
```

Point at a different league: `SLEEPER_LEAGUE_ID=<id> etl/.venv/bin/python -m etl.build --fetch`.

## What's inside

**Pages:** Overview · Power Rankings · History & Trends · Trades · Draft · Players
· League Trends · a dedicated tab per team (`/team/:rosterId`).

**Per-team tab** — power-archetype banner, manager labels with evidence, weekly
scoring vs. the optimal lineup (points-left-on-bench), luck-vs-skill, the
real-football roster profile (snap %, target share, WOPR, age, signals),
buy-low/sell-high board, contention window, trade & draft history, rivalries, and
templated recommendations.

**The optimal-lineup engine** (`etl/lineup.py`) is exact (max-weight assignment,
superflex-aware) and unit-tested against Sleeper's own `ppts` — it powers
points-left-on-bench, lineup efficiency, and avoidable losses.

## Data sources

- **Sleeper API** (`api.sleeper.app`) — league/rosters/users/matchups/transactions/
  drafts/players. No auth.
- **nflverse** (CC-BY-4.0 release files) — weekly player stats (target share, air
  yards, WOPR), snap counts, Next Gen Stats, injuries, schedules, play-by-play
  (team pace / PROE / EPA).
- **DynastyProcess** `db_playerids.csv` — the crosswalk bridging Sleeper
  `player_id` ↔ nflverse `gsis_id` / `pfr_id`.

Attribution: *Data: Sleeper API · nflverse (CC-BY-4.0)*.

## Dynasty player & team value

Player/team quality is **forward-looking real football**, never last year's
fantasy points:

- **`etl/value.py`** blends a real-football model (in-house xFP/g + position usage
  z-scores + capped efficiency, age-adjusted by dynasty aging curves) with
  **FantasyCalc** superflex-dynasty market value (joined directly on Sleeper id) +
  **DynastyProcess** as a cross-check.
- **Injuries are a separate durability axis** — talent is measured per game played;
  `AvailabilityScore` and `RiskScore` are their own fields and never lower value. A
  hurt star reads *Elite, high risk* (a buy-low), not a discount.
- **Buy/sell** = value-vs-market gap + opportunity-vs-output (FPOE), not past points.
- **Trades** credit each side's realized production over a player's full tenure
  **plus the remaining dynasty value of still-held players**. Draft picks are
  linked to the rookie they became and valued accordingly; trades with future
  (unrealized) picks stay *pending*.
- **Justifications** — every player value, buy/sell signal, and team label exposes
  a "why" (the metric, threshold, blend, data source, confidence) on hover/expand —
  built deterministically from the data, never invented.

Manager quality stays on the fantasy axis (lineup efficiency, luck, waiver/draft
acumen) and never touches these numbers.
