"""Read the raw Sleeper pulls back into convenient in-memory structures.

The metric layer depends only on this module (not on the network), so compute
can be re-run offline against cached raw JSON.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

from . import config as C
from .util import load_json


@dataclass
class Season:
    season: str
    league: dict
    rosters: list[dict]
    users: list[dict]
    winners_bracket: list[dict]
    losers_bracket: list[dict]
    traded_picks: list[dict]
    drafts: list[dict]
    draft: dict
    draft_picks: list[dict]
    draft_traded_picks: list[dict]
    matchups: dict[int, list[dict]]      # week -> rows
    transactions: dict[int, list[dict]]  # week -> rows
    meta: dict = field(default_factory=dict)

    @property
    def playoff_week_start(self) -> int:
        return int((self.league.get("settings") or {}).get("playoff_week_start") or 15)

    @property
    def regular_weeks(self) -> list[int]:
        return [w for w in sorted(self.matchups) if w < self.playoff_week_start]

    @property
    def playoff_weeks(self) -> list[int]:
        return [w for w in sorted(self.matchups) if w >= self.playoff_week_start]

    def user_by_id(self, uid: str | None) -> dict:
        for u in self.users:
            if u.get("user_id") == uid:
                return u
        return {}

    def roster_owner(self, roster_id: int) -> dict:
        for r in self.rosters:
            if r.get("roster_id") == roster_id:
                return self.user_by_id(r.get("owner_id"))
        return {}


def _season_dir(season: str) -> Path:
    return C.RAW_SLEEPER / season


def load_season(season: str) -> Season:
    d = _season_dir(season)

    def w_files(sub: str) -> dict[int, list[dict]]:
        out: dict[int, list[dict]] = {}
        wd = d / sub
        if wd.exists():
            for f in wd.glob("*.json"):
                out[int(f.stem)] = load_json(f, [])
        return out

    return Season(
        season=season,
        league=load_json(d / "league.json", {}),
        rosters=load_json(d / "rosters.json", []),
        users=load_json(d / "users.json", []),
        winners_bracket=load_json(d / "winners_bracket.json", []),
        losers_bracket=load_json(d / "losers_bracket.json", []),
        traded_picks=load_json(d / "traded_picks.json", []),
        drafts=load_json(d / "drafts.json", []),
        draft=load_json(d / "draft.json", {}),
        draft_picks=load_json(d / "draft_picks.json", []),
        draft_traded_picks=load_json(d / "draft_traded_picks.json", []),
        matchups=w_files("matchups"),
        transactions=w_files("transactions"),
        meta=load_json(d / "_meta.json", {}),
    )


def seasons() -> list[str]:
    """Season strings, oldest -> newest."""
    chain = load_json(C.RAW_SLEEPER / "chain.json", [])
    if chain:
        return [str(c["season"]) for c in chain]
    return sorted(p.name for p in C.RAW_SLEEPER.iterdir()
                  if p.is_dir() and p.name.isdigit())


def load_all() -> list[Season]:
    return [load_season(s) for s in seasons()]


@functools.lru_cache(maxsize=1)
def players_map() -> dict[str, dict]:
    """Sleeper /players/nfl (pid -> attributes)."""
    return load_json(C.PLAYERS_CACHE, {})


def fantasy_positions(pid: str) -> set[str]:
    p = players_map().get(pid) or {}
    fps = p.get("fantasy_positions") or ([p["position"]] if p.get("position") else [])
    return set(fps)


def player_name(pid: str) -> str:
    p = players_map().get(pid) or {}
    if p.get("full_name"):
        return p["full_name"]
    if p.get("first_name") or p.get("last_name"):
        return f"{p.get('first_name','')} {p.get('last_name','')}".strip()
    # DEF pseudo-players are keyed by team code
    if (p.get("position") == "DEF") and p.get("team"):
        return f"{p['team']} DEF"
    return pid
