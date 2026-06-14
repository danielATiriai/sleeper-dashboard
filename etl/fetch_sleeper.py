"""Pull a Sleeper league's full multi-season history into etl/raw/sleeper/.

Source of truth = the raw JSON saved here; metric modules read it back, so
compute can be re-run without re-hitting the API.

Run standalone:  python -m etl.fetch_sleeper
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from . import config as C
from .util import get_json, save_json, load_json


def _slug(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum())


def walk_chain(league_id: str, max_back: int | None) -> list[dict]:
    """Follow previous_league_id newest->oldest. Returns oldest-first."""
    chain: list[dict] = []
    seen: set[str] = set()
    cur: str | None = league_id
    while cur and cur != "0" and cur not in seen:
        seen.add(cur)
        lg = get_json(f"{C.SLEEPER_BASE}/league/{cur}")
        if not lg:
            break
        chain.append(lg)
        if max_back is not None and len(chain) >= max_back:
            break
        cur = lg.get("previous_league_id")
    chain.reverse()  # oldest first -> natural chronological order
    return chain


def fetch_season(league: dict) -> dict:
    """Fetch every per-season + per-week artifact for one league node."""
    lid = league["league_id"]
    season = str(league["season"])
    out = C.RAW_SLEEPER / season
    out.mkdir(parents=True, exist_ok=True)

    save_json(league, out / "league.json")
    rosters = get_json(f"{C.SLEEPER_BASE}/league/{lid}/rosters") or []
    users = get_json(f"{C.SLEEPER_BASE}/league/{lid}/users") or []
    save_json(rosters, out / "rosters.json")
    save_json(users, out / "users.json")
    save_json(get_json(f"{C.SLEEPER_BASE}/league/{lid}/winners_bracket") or [],
              out / "winners_bracket.json")
    save_json(get_json(f"{C.SLEEPER_BASE}/league/{lid}/losers_bracket") or [],
              out / "losers_bracket.json")
    save_json(get_json(f"{C.SLEEPER_BASE}/league/{lid}/traded_picks") or [],
              out / "traded_picks.json")

    # Drafts (newest first); grab the primary draft detail + picks.
    drafts = get_json(f"{C.SLEEPER_BASE}/league/{lid}/drafts") or []
    save_json(drafts, out / "drafts.json")
    if drafts:
        did = drafts[0]["draft_id"]
        save_json(get_json(f"{C.SLEEPER_BASE}/draft/{did}") or {}, out / "draft.json")
        save_json(get_json(f"{C.SLEEPER_BASE}/draft/{did}/picks") or [],
                  out / "draft_picks.json")
        save_json(get_json(f"{C.SLEEPER_BASE}/draft/{did}/traded_picks") or [],
                  out / "draft_traded_picks.json")

    # Per-week matchups + transactions. Keep only weeks with real data.
    mdir = out / "matchups"
    tdir = out / "transactions"
    mdir.mkdir(exist_ok=True)
    tdir.mkdir(exist_ok=True)
    weeks_with_matchups: list[int] = []
    for wk in C.WEEK_RANGE:
        m = get_json(f"{C.SLEEPER_BASE}/league/{lid}/matchups/{wk}") or []
        has_points = any((row.get("points") or 0) > 0 for row in m)
        if m and has_points:
            save_json(m, mdir / f"{wk}.json")
            weeks_with_matchups.append(wk)
        t = get_json(f"{C.SLEEPER_BASE}/league/{lid}/transactions/{wk}") or []
        if t:
            save_json(t, tdir / f"{wk}.json")

    meta = {
        "season": season,
        "league_id": lid,
        "name": league.get("name"),
        "total_rosters": league.get("total_rosters"),
        "weeks_with_matchups": weeks_with_matchups,
        "playoff_week_start": (league.get("settings") or {}).get("playoff_week_start"),
        "n_rosters": len(rosters),
        "n_users": len(users),
        "n_draft_picks": len(load_json(out / "draft_picks.json", [])),
    }
    save_json(meta, out / "_meta.json", slim=False)
    return meta


def fetch_players(force: bool = False) -> dict:
    """Cache the giant /players/nfl map (≈15MB). Refetch at most daily."""
    p = C.PLAYERS_CACHE
    if p.exists() and not force:
        age_h = (time.time() - p.stat().st_mtime) / 3600
        if age_h < C.PLAYERS_CACHE_MAX_AGE_H:
            return load_json(p)
    players = get_json(f"{C.SLEEPER_BASE}/players/nfl")
    save_json(players, p)
    return players


def main() -> int:
    C.ensure_dirs()
    print(f"[sleeper] walking chain from league {C.LEAGUE_ID} …")
    chain = walk_chain(C.LEAGUE_ID, C.MAX_SEASONS_BACK)
    if not chain:
        print("[sleeper] ERROR: empty chain (bad league id?)", file=sys.stderr)
        return 1
    seasons = [str(lg["season"]) for lg in chain]
    print(f"[sleeper] seasons (oldest→newest): {seasons}")
    save_json([{k: lg.get(k) for k in
               ("season", "league_id", "previous_league_id", "name",
                "total_rosters", "status")} for lg in chain],
              C.RAW_SLEEPER / "chain.json", slim=False)

    metas = []
    for lg in chain:
        meta = fetch_season(lg)
        metas.append(meta)
        print(f"  · {meta['season']}: {meta['n_rosters']} rosters, "
              f"{len(meta['weeks_with_matchups'])} scored weeks, "
              f"{meta['n_draft_picks']} draft picks")

    print("[sleeper] caching /players/nfl …")
    players = fetch_players()
    print(f"[sleeper] players cached: {len(players)} entries")
    print("[sleeper] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
