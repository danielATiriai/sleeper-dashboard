"""Assemble the league analysis: stitch owner identity across seasons, fold in
management (waiver/trade) + draft metrics + rivalries + multi-season trajectory,
and key everything by the latest-season roster_id (a "team" = an owner).
"""
from __future__ import annotations

from collections import defaultdict

from . import statlib as S
from .metrics_fantasy import (
    league_player_season_ppg,
    primary_position,
    season_team_metrics,
    vor_baselines,
)
from .store import Season, load_all, players_map


def _team_meta(season: Season, rid: int) -> dict:
    owner = season.roster_owner(rid)
    roster = next((r for r in season.rosters if r["roster_id"] == rid), {})
    md = owner.get("metadata") or {}
    avatar = owner.get("avatar")
    return {
        "roster_id": rid,
        "owner_id": roster.get("owner_id"),
        "display_name": owner.get("display_name") or f"Team {rid}",
        "team_name": md.get("team_name") or owner.get("display_name") or f"Team {rid}",
        "avatar_url": f"https://sleepercdn.com/avatars/thumbs/{avatar}" if avatar else None,
        "co_owners": roster.get("co_owners") or [],
    }


def _player_week_points(season: Season) -> dict[int, dict[str, dict[int, float]]]:
    """roster_id -> pid -> {week: points} across all weeks."""
    out: dict[int, dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    for wk, rows in season.matchups.items():
        for r in rows:
            rid = r["roster_id"]
            for pid, pts in (r.get("players_points") or {}).items():
                out[rid][pid][wk] = float(pts or 0)
    return out


# ---------------------------------------------------------------------------
# Management: waivers + trades
# ---------------------------------------------------------------------------
def management_metrics(season: Season, baselines: dict[str, float],
                       pw: dict) -> dict[int, dict]:
    res: dict[int, dict] = {
        r["roster_id"]: {
            "adds": 0, "waiver_adds": 0, "fa_adds": 0, "drops": 0,
            "faab_used": (r.get("settings") or {}).get("waiver_budget_used", 0),
            "total_moves": (r.get("settings") or {}).get("total_moves", 0),
            "trades": 0, "waiver_hits": 0, "waiver_scored": [],
        } for r in season.rosters
    }
    for wk, txs in season.transactions.items():
        for tx in txs:
            if tx.get("status") != "complete":
                continue
            ttype = tx.get("type")
            if ttype in ("waiver", "free_agent"):
                for pid, rid in (tx.get("adds") or {}).items():
                    if rid not in res:
                        continue
                    res[rid]["adds"] += 1
                    res[rid]["waiver_adds" if ttype == "waiver" else "fa_adds"] += 1
                    # realized value: this player's points for rid in weeks after add
                    later = {w: p for w, p in pw.get(rid, {}).get(pid, {}).items() if w >= wk}
                    if later:
                        ppg = S.mean(list(later.values()))
                        base = baselines.get(primary_position(pid), 6.0)
                        if ppg >= base and len(later) >= 2:
                            res[rid]["waiver_hits"] += 1
                            res[rid]["waiver_scored"].append({
                                "pid": pid,
                                "name": players_map().get(pid, {}).get("full_name", pid),
                                "ppg": round(ppg, 1), "pos": primary_position(pid),
                            })
                for _pid, rid in (tx.get("drops") or {}).items():
                    if rid in res:
                        res[rid]["drops"] += 1
            elif ttype == "trade":
                for rid in (tx.get("roster_ids") or []):
                    if rid in res:
                        res[rid]["trades"] += 1
    for rid, m in res.items():
        m["waiver_hit_rate"] = round(S.safe_div(m["waiver_hits"], m["adds"]), 3)
        m["faab_efficiency"] = round(
            S.safe_div(sum(x["ppg"] for x in m["waiver_scored"]),
                       max(m["faab_used"], 1)), 3)
        m["waiver_scored"] = sorted(m["waiver_scored"],
                                    key=lambda x: x["ppg"], reverse=True)[:8]
    return res


def build_cross_season(seasons: list[Season], owner_of: dict):
    """owner_id -> pid -> sorted [(season_idx, week, points)] across ALL seasons,
    plus per-season VOR baselines. Lets trade value follow a player's full tenure
    on a manager's roster (dynasty scope), spanning seasons."""
    owner_pw: dict = defaultdict(lambda: defaultdict(list))
    season_baselines: dict[str, dict] = {}
    for i, s in enumerate(seasons):
        ppg = league_player_season_ppg(s)
        season_baselines[s.season] = vor_baselines(ppg, len(s.rosters))
        oof = owner_of[s.season]
        for wk, rows in s.matchups.items():
            for row in rows:
                owner = oof.get(row["roster_id"])
                if not owner:
                    continue
                for pid, pts in (row.get("players_points") or {}).items():
                    owner_pw[owner][pid].append((i, wk, float(pts or 0)))
    for o in owner_pw:
        for pid in owner_pw[o]:
            owner_pw[o][pid].sort()
    return owner_pw, season_baselines


def trade_ledger(season: Season, si: int, owner_of: dict, owner_pw: dict,
                 seasons: list[Season], season_baselines: dict,
                 latest_roster_by_owner: dict) -> list[dict]:
    """One record per completed trade. Each received player is valued over its
    ENTIRE tenure on the acquiring manager's roster (from the trade onward, across
    seasons, ongoing if still held) — not just rest-of-current-season."""
    ledger = []
    oof = owner_of[season.season]
    for wk, txs in season.transactions.items():
        for tx in txs:
            if tx.get("type") != "trade" or tx.get("status") != "complete":
                continue
            adds = tx.get("adds") or {}     # pid -> roster receiving
            picks = tx.get("draft_picks") or []
            faab = tx.get("waiver_budget") or []
            rids = tx.get("roster_ids") or []
            sides: dict[int, dict] = {rid: {"received": [], "roi": 0.0} for rid in rids}
            for pid, to_rid in adds.items():
                if to_rid not in sides:
                    continue
                owner = oof.get(to_rid)
                pos = primary_position(pid)
                pts_total = vor_total = 0.0
                games = 0
                for (s_i, w, pts) in owner_pw.get(owner, {}).get(pid, []):
                    if (s_i, w) >= (si, wk):
                        base = season_baselines[seasons[s_i].season].get(pos, 6.0)
                        pts_total += pts
                        vor_total += pts - base
                        games += 1
                ongoing = pid in latest_roster_by_owner.get(owner, set())
                sides[to_rid]["received"].append({
                    "pid": pid, "name": players_map().get(pid, {}).get("full_name", pid),
                    "pos": pos, "tenure_points": round(pts_total, 1),
                    "tenure_vor": round(vor_total, 1), "games": games,
                    "ongoing": ongoing,
                })
                sides[to_rid]["roi"] += vor_total
            any_ongoing = any(r.get("ongoing") for s in sides.values()
                              for r in s["received"])
            ledger.append({
                "season": season.season, "week": wk,
                "roster_ids": rids,
                "sides": {str(k): v for k, v in sides.items()},
                "n_picks": len(picks),
                "picks": [{"season": p.get("season"), "round": p.get("round"),
                           "from": p.get("previous_owner_id"), "to": p.get("owner_id"),
                           "orig": p.get("roster_id")}  # original slot owner (for realization)
                          for p in picks],
                "faab": [{"amount": f.get("amount"), "sender": f.get("sender"),
                          "receiver": f.get("receiver")} for f in faab],
                # Picks can't be graded until they become players -> PENDING.
                "pending": len(picks) > 0,
                # Player tenure may still be accruing if a player is still rostered.
                "ongoing": any_ongoing,
            })
    # normalize ROI per trade so the two sides sum to ~0 (relative fleece)
    for t in ledger:
        rois = [s["roi"] for s in t["sides"].values()]
        avg = S.mean(rois)
        for s in t["sides"].values():
            s["roi"] = round(s["roi"] - avg, 1)
    return ledger


# ---------------------------------------------------------------------------
# Draft analysis
# ---------------------------------------------------------------------------
def draft_metrics(season: Season, player_ppg: dict[str, dict]) -> dict:
    picks = season.draft_picks
    if not picks:
        return {"per_team": {}, "board": [], "expected_curve": []}
    # expected production by pick_no: smooth the realized totals vs pick order.
    ordered = sorted(picks, key=lambda p: p.get("pick_no") or 0)
    totals = [player_ppg.get(p.get("player_id"), {}).get("total", 0.0) for p in ordered]
    # monotone-ish expectation: running average of sorted-desc totals mapped to slot
    sorted_tot = sorted(totals, reverse=True)
    n = len(sorted_tot)
    win = max(1, n // 12)
    expected_curve = [round(S.mean(sorted_tot[max(0, i - win): i + win + 1]), 1)
                      for i in range(n)]

    board = []
    per_team: dict[int, dict] = defaultdict(
        lambda: {"roi": 0.0, "picks": [], "hits": 0, "n": 0, "pos_pick_no": defaultdict(list)})
    for idx, p in enumerate(ordered):
        pid = p.get("player_id")
        rid = p.get("roster_id")
        pos = (p.get("metadata") or {}).get("position") or primary_position(pid or "")
        actual = player_ppg.get(pid, {}).get("total", 0.0)
        ppg = player_ppg.get(pid, {}).get("ppg", 0.0)
        expected = expected_curve[idx]
        roi = actual - expected
        name = (p.get("metadata") or {})
        name = f"{name.get('first_name','')} {name.get('last_name','')}".strip() or pid
        rec = {
            "pick_no": p.get("pick_no"), "round": p.get("round"),
            "roster_id": rid, "pid": pid, "name": name, "pos": pos,
            "actual": round(actual, 1), "expected": round(expected, 1),
            "roi": round(roi, 1), "ppg": round(ppg, 1),
            "is_keeper": bool(p.get("is_keeper")),
        }
        board.append(rec)
        t = per_team[rid]
        t["roi"] += roi
        t["n"] += 1
        t["picks"].append(rec)
        t["pos_pick_no"][pos].append(p.get("pick_no") or 0)
        if roi > 0:
            t["hits"] += 1
    out_team = {}
    for rid, t in per_team.items():
        out_team[rid] = {
            "roi": round(t["roi"], 1),
            "hit_rate": round(S.safe_div(t["hits"], t["n"]), 3),
            "n_picks": t["n"],
            "best": sorted(t["picks"], key=lambda r: r["roi"], reverse=True)[:3],
            "worst": sorted(t["picks"], key=lambda r: r["roi"])[:3],
            "avg_pos_pick": {pos: round(S.mean(v), 1)
                             for pos, v in t["pos_pick_no"].items()},
        }
    return {"per_team": out_team, "board": board, "expected_curve": expected_curve}


# ---------------------------------------------------------------------------
# Cross-season: rivalries + trajectory
# ---------------------------------------------------------------------------
def rivalries(all_seasons: list[Season], owner_of: dict) -> dict[str, dict[str, dict]]:
    """owner_id -> opp_owner_id -> {w,l,t,pf,pa,meetings,margins}."""
    rec: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0, "meetings": 0}))
    for season in all_seasons:
        oid = owner_of[season.season]  # rid -> owner_id for this season
        for wk in season.regular_weeks + season.playoff_weeks:
            rows = season.matchups.get(wk, [])
            by_m: dict = defaultdict(list)
            for r in rows:
                if r.get("matchup_id") is not None:
                    by_m[r["matchup_id"]].append(r)
            for pair in by_m.values():
                if len(pair) != 2:
                    continue
                a, b = pair
                oa, ob = oid.get(a["roster_id"]), oid.get(b["roster_id"])
                if not oa or not ob:
                    continue
                pa_, pb = float(a.get("points") or 0), float(b.get("points") or 0)
                for (me, opp, mp, op) in ((oa, ob, pa_, pb), (ob, oa, pb, pa_)):
                    d = rec[me][opp]
                    d["meetings"] += 1
                    d["pf"] += mp
                    d["pa"] += op
                    if mp > op:
                        d["w"] += 1
                    elif mp < op:
                        d["l"] += 1
                    else:
                        d["t"] += 1
    return rec


def season_rivalries(season: Season, oid_map: dict[int, str]) -> dict[str, dict[str, dict]]:
    """Single-season H2H: owner_id -> opp_owner_id -> {w,l,t,meetings,pf,pa}.
    Lets the team page show that-season matchups (not an all-time blend)."""
    rec: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0, "meetings": 0}))
    for wk in season.regular_weeks + season.playoff_weeks:
        rows = season.matchups.get(wk, [])
        by_m: dict = defaultdict(list)
        for r in rows:
            if r.get("matchup_id") is not None:
                by_m[r["matchup_id"]].append(r)
        for pair in by_m.values():
            if len(pair) != 2:
                continue
            a, b = pair
            oa, ob = oid_map.get(a["roster_id"]), oid_map.get(b["roster_id"])
            if not oa or not ob:
                continue
            pa_, pb = float(a.get("points") or 0), float(b.get("points") or 0)
            for (me, opp, mp, op) in ((oa, ob, pa_, pb), (ob, oa, pb, pa_)):
                d = rec[me][opp]
                d["meetings"] += 1
                d["pf"] += mp
                d["pa"] += op
                if mp > op:
                    d["w"] += 1
                elif mp < op:
                    d["l"] += 1
                else:
                    d["t"] += 1
    return rec


def assemble() -> dict:
    seasons = load_all()
    if not seasons:
        raise RuntimeError("no seasons loaded — run fetch_sleeper first")
    latest = seasons[-1]
    n_teams = len(latest.rosters)

    # owner_id -> roster_id per season, and rid -> owner per season
    owner_of: dict[str, dict[int, str]] = {}
    for s in seasons:
        owner_of[s.season] = {r["roster_id"]: r.get("owner_id") for r in s.rosters}

    # Cross-season structures so trade value follows a player's full tenure.
    season_index = {s.season: i for i, s in enumerate(seasons)}
    owner_pw, season_baselines = build_cross_season(seasons, owner_of)
    latest_roster_by_owner = {r.get("owner_id"): set(r.get("players") or [])
                              for r in latest.rosters}

    per_season: dict[str, dict] = {}
    for s in seasons:
        metrics = season_team_metrics(s)
        player_ppg = league_player_season_ppg(s)
        baselines = vor_baselines(player_ppg, len(s.rosters))
        pw = _player_week_points(s)
        per_season[s.season] = {
            "metrics": metrics,
            "management": management_metrics(s, baselines, pw),
            "trades": trade_ledger(s, season_index[s.season], owner_of, owner_pw,
                                   seasons, season_baselines, latest_roster_by_owner),
            "draft": draft_metrics(s, player_ppg),
            "playoff_week_start": s.playoff_week_start,
            "champion": next((rid for rid, t in metrics.items() if t.get("champion")), None),
            "runner_up": next((rid for rid, t in metrics.items() if t.get("runner_up")), None),
        }

    riv = rivalries(seasons, owner_of)
    # per-season H2H so the team page can scope rivalries to the selected year
    season_riv = {s.season: season_rivalries(s, owner_of[s.season]) for s in seasons}
    latest_rid_by_owner = {rr.get("owner_id"): rr["roster_id"] for rr in latest.rosters}

    # Build teams keyed by latest roster_id, identity stitched by owner.
    teams: dict[int, dict] = {}
    for r in latest.rosters:
        rid = r["roster_id"]
        oid = r.get("owner_id")
        meta = _team_meta(latest, rid)
        # collect this owner's roster_id per season
        season_rid = {s.season: next(
            (rr["roster_id"] for rr in s.rosters if rr.get("owner_id") == oid), None)
            for s in seasons}
        seasons_detail = {}
        traj = {"pf_rank": [], "all_play_pct": [], "finish": [], "season": []}
        championships = 0
        for s in seasons:
            srid = season_rid[s.season]
            if srid is None:
                continue
            tm = per_season[s.season]["metrics"][srid]
            mgmt = per_season[s.season]["management"][srid]
            draft = per_season[s.season]["draft"]["per_team"].get(srid, {})
            seasons_detail[s.season] = {**tm, "management": mgmt, "draft": draft}
            sr = season_riv[s.season].get(oid, {})
            seasons_detail[s.season]["rivalries"] = sorted(
                [{"opp_roster_id": latest_rid_by_owner[oo], "w": dd["w"], "l": dd["l"],
                  "t": dd["t"], "meetings": dd["meetings"],
                  "pf": round(dd["pf"], 1), "pa": round(dd["pa"], 1)}
                 for oo, dd in sr.items() if oo in latest_rid_by_owner],
                key=lambda x: x["meetings"], reverse=True)
            traj["season"].append(s.season)
            traj["pf_rank"].append(tm["pf_rank"])
            traj["all_play_pct"].append(tm["luck"]["all_play_pct"])
            traj["finish"].append(tm.get("final_standing"))
            championships += int(tm.get("champion", False))
        # rivalries: map owner-keyed to opp roster meta in latest season
        my_riv = []
        for opp_oid, d in riv.get(oid, {}).items():
            opp_rid = next((rr["roster_id"] for rr in latest.rosters
                            if rr.get("owner_id") == opp_oid), None)
            if opp_rid is None:
                continue
            my_riv.append({"opp_roster_id": opp_rid, **d,
                           "pf": round(d["pf"], 1), "pa": round(d["pa"], 1)})
        teams[rid] = {
            **meta,
            "season_rid": season_rid,
            "seasons": seasons_detail,
            "trajectory": {**traj, "pf_rank_slope": round(S.ols_slope(
                [-x for x in traj["pf_rank"]]), 3)},  # rising rank = positive
            "career": {
                "seasons_played": len(seasons_detail),
                "championships": championships,
                "best_finish": min((d.get("final_standing", 99)
                                    for d in seasons_detail.values()), default=None),
                "record": {
                    "w": sum(d["record"]["w"] for d in seasons_detail.values()),
                    "l": sum(d["record"]["l"] for d in seasons_detail.values()),
                    "t": sum(d["record"]["t"] for d in seasons_detail.values()),
                },
                # podium finishes (playoff 1st/2nd/3rd) with the year, for badges
                "podiums": sorted(
                    [{"season": s, "place": d.get("playoff_finish")}
                     for s, d in seasons_detail.items()
                     if d.get("playoff_finish") in (1, 2, 3)],
                    key=lambda x: x["season"]),
            },
            "rivalries": sorted(my_riv, key=lambda x: x["meetings"], reverse=True),
        }

    return {
        "seasons": [s.season for s in seasons],
        "latest_season": latest.season,
        "n_teams": n_teams,
        "league": {
            "name": latest.league.get("name"),
            "season": latest.season,
            "roster_positions": latest.league.get("roster_positions"),
            "scoring_settings": latest.league.get("scoring_settings"),
            "settings": latest.league.get("settings"),
        },
        "per_season": per_season,
        "teams": teams,
        "owner_of": owner_of,
    }
