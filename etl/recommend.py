"""Recommendation engine: rank a team's labels by severity×confidence and turn
the top few into concrete, numbers-backed prescriptions — with named cross-team
candidates (buy-low / sell-high) where the logic supports it.
"""
from __future__ import annotations

from . import statlib as St
from .metrics_fantasy import primary_position


def _league_top_at(analysis: dict, season: str, pos: str, exclude_rid: int,
                   limit: int = 4) -> list[dict]:
    """Highest DYNASTY-VALUE players at a position NOT on the given roster, scoped
    to the SELECTED season (a 2024 rec must name 2024 players/owners, not the
    current roster). The latest season uses the live value model; past seasons use
    that season's roster snapshots."""
    latest = analysis["latest_season"]
    pool: list[dict] = []
    if season == latest:
        names = {rid: t["team_name"] for rid, t in analysis["teams"].items()}
        for v in analysis.get("player_values", {}).values():
            if v["pos"] == pos and v["roster_id"] != exclude_rid:
                pool.append({"name": v["name"], "pos": pos, "value": v["player_value"],
                             "owner": names.get(v["roster_id"], "?"),
                             "roster_id": v["roster_id"]})
    else:
        for orid, t in analysis["teams"].items():
            if orid == exclude_rid:
                continue
            for p in t["seasons"].get(season, {}).get("roster", []):
                v = p.get("value")
                if v and p.get("pos") == pos:
                    pool.append({"name": p["name"], "pos": pos,
                                 "value": v["player_value"], "owner": t["team_name"],
                                 "roster_id": orid})
    return sorted(pool, key=lambda x: -x["value"])[:limit]


def recommend_team(rid: int, analysis: dict, labels: list[dict],
                   season: str | None = None) -> list[dict]:
    season = season or analysis["latest_season"]
    team = analysis["teams"][rid]
    d = team["seasons"].get(season, {})
    recs: list[dict] = []
    by_key = {l["key"]: l for l in labels}

    def add(title, basis, detail, severity, players=None, kind="advice"):
        recs.append({"title": title, "basis": basis, "detail": detail,
                     "severity": round(severity, 3), "players": players or [],
                     "kind": kind})

    # Bench efficiency
    if "bench_bleeder" in by_key:
        eff = d["efficiency"]
        add("Set your lineups more carefully", "fantasy",
            f"You left {eff['plob_avg']:.1f} pts/week ({eff['plob_total']:.0f} total) "
            f"on the bench — lineup efficiency {eff['eff']:.0%}. "
            f"{eff['avoidable_losses']} of your losses were winnable with your optimal "
            f"lineup. Tightening this is the cheapest win available.",
            by_key["bench_bleeder"]["severity"], kind="fix")

    # Positional need (by dynasty value) -> trade targets at that position
    for pos in ("QB", "RB", "WR", "TE"):
        if f"thin_{pos}" in by_key:
            targets = _league_top_at(analysis, season, pos, rid, 4)
            add(f"Address your {pos} need", "both",
                f"Your {pos} group is bottom-tier in real dynasty value. Target a trade "
                f"for one of the league's higher-value {pos}s.",
                by_key[f"thin_{pos}"]["severity"],
                players=[{"name": t["name"], "pos": pos, "owner": t["owner"],
                          "note": f"val {t['value']:.0f}"}
                         for t in targets], kind="buy")

    # Stars & scrubs -> sell a star for depth
    if "stars_scrubs" in by_key:
        stars = d["construction"]["stars"][:1]
        add("Trade from your surplus for depth", "fantasy",
            f"Your value is concentrated in a few players "
            f"(top-3 = {d['construction']['top3_share']:.0%} of roster value). "
            f"Consider moving one star for two starters to shore up your weak spots.",
            by_key["stars_scrubs"]["severity"],
            players=[{"name": s["name"], "pos": s["pos"], "ppg": s["ppg"],
                      "note": "sell-high candidate"} for s in stars], kind="sell")

    # Luck-based guidance
    if "snakebitten" in by_key:
        add("Stay the course — don't panic-trade", "fantasy",
            f"You scored like a {d['luck']['all_play_pct']:.0%} all-play team but only "
            f"went {d['record']['w']}-{d['record']['l']} ({d['luck']['luck']:+.1f} wins "
            f"of bad luck). The process is sound; positive regression is coming.",
            by_key["snakebitten"]["severity"], kind="hold")
    if "lucky" in by_key:
        add("Buy insurance before regression", "fantasy",
            f"You're {d['luck']['luck']:+.1f} wins above what your scores justify "
            f"(all-play just {d['luck']['all_play_pct']:.0%}). Use the strong record to "
            f"sell-high and add depth before variance corrects.",
            by_key["lucky"]["severity"], kind="sell")

    # Engagement
    if "waiver_ghost" in by_key:
        add("Work the waiver wire", "fantasy",
            f"Only {d['management']['adds']} pickups all season — the bottom of the "
            f"league. Active managers turn over their bench for upside.",
            by_key["waiver_ghost"]["severity"], kind="fix")

    # Trajectory
    if "fading" in by_key:
        add("Your scoring is trending down", "fantasy",
            "Points-per-week declined over the season. Audit aging/injured pieces "
            "and refresh the roster.", by_key["fading"]["severity"], kind="advice")

    recs.sort(key=lambda r: r["severity"], reverse=True)
    return recs[:4]
