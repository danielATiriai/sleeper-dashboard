"""Fantasy-side metrics: the numeric backbone for every fantasy label.

Produces a per-team analysis (keyed by the latest-season roster_id, identity
stitched across seasons by owner user_id) with per-season detail + career
aggregates. All scores come from Sleeper `matchups` (league-accurate), never the
pre-baked pts_ppr.
"""
from __future__ import annotations

from collections import defaultdict

from . import config as C
from . import statlib as S
from .lineup import matchup_efficiency
from .store import Season, fantasy_positions, players_map

# Replacement-level starter counts (league-wide) for VOR baselines. Tuned for an
# 8-team superflex; scales with team count.
_REPL_STARTERS = {"QB": 1.6, "RB": 2.6, "WR": 3.6, "TE": 1.2}


def _pos_of(pids):
    return {p: fantasy_positions(p) for p in pids}


def primary_position(pid: str) -> str:
    p = players_map().get(pid) or {}
    return p.get("position") or (next(iter(fantasy_positions(pid)), "NA"))


# ---------------------------------------------------------------------------
# Per-season scaffolding from matchups
# ---------------------------------------------------------------------------
def _week_index(season: Season, week: int):
    """Return (team_points{rid:pts}, opponent{rid:rid}, players_points{rid:dict})."""
    rows = season.matchups.get(week, [])
    team_pts = {r["roster_id"]: float(r.get("points") or 0) for r in rows}
    pp = {r["roster_id"]: (r.get("players_points") or {}) for r in rows}
    starters_pts = {r["roster_id"]: (r.get("starters_points") or []) for r in rows}
    by_matchup: dict = defaultdict(list)
    for r in rows:
        if r.get("matchup_id") is not None:
            by_matchup[r["matchup_id"]].append(r["roster_id"])
    opp = {}
    for rids in by_matchup.values():
        if len(rids) == 2:
            a, b = rids
            opp[a], opp[b] = b, a
    return team_pts, opp, pp, starters_pts


def league_player_season_ppg(season: Season) -> dict[str, dict]:
    """League-wide per-player regular-season production (for VOR baselines)."""
    acc: dict[str, list[float]] = defaultdict(list)
    for wk in season.regular_weeks:
        _, _, pp, _ = _week_index(season, wk)
        for rid, players in pp.items():
            for pid, pts in players.items():
                acc[pid].append(float(pts or 0))
    out = {}
    for pid, weekly in acc.items():
        out[pid] = {
            "ppg": S.mean(weekly),
            "total": round(sum(weekly), 2),
            "games": len(weekly),
            "pos": primary_position(pid),
        }
    return out


def vor_baselines(player_ppg: dict[str, dict], n_teams: int) -> dict[str, float]:
    """Replacement-level PPG per position = the Nth-best starter league-wide."""
    by_pos: dict[str, list[float]] = defaultdict(list)
    for v in player_ppg.values():
        if v["games"] >= 4:
            by_pos[v["pos"]].append(v["ppg"])
    base = {}
    for pos, vals in by_pos.items():
        vals.sort(reverse=True)
        n = max(1, round(n_teams * _REPL_STARTERS.get(pos, 1.0)))
        base[pos] = vals[min(n, len(vals)) - 1] if vals else 0.0
    return base


# ---------------------------------------------------------------------------
# Per-team-per-season metrics
# ---------------------------------------------------------------------------
def season_team_metrics(season: Season) -> dict[int, dict]:
    n_teams = len(season.rosters)
    rp = season.league["roster_positions"]
    reg = season.regular_weeks
    playoff = season.playoff_weeks

    # League weekly distributions (for all-play, boom/bust, PA percentile).
    weekly_all_pts: dict[int, dict[int, float]] = {}
    for wk in reg:
        team_pts, _, _, _ = _week_index(season, wk)
        weekly_all_pts[wk] = team_pts
    all_reg_scores = [p for wk in reg for p in weekly_all_pts[wk].values()]
    league_week_mean = S.mean(all_reg_scores)
    league_week_sigma = S.stdev(all_reg_scores)

    # Per-player season PPG + VOR baselines (roster construction).
    player_ppg = league_player_season_ppg(season)
    baselines = vor_baselines(player_ppg, n_teams)

    out: dict[int, dict] = {}
    rid_list = [r["roster_id"] for r in season.rosters]

    # roster -> set of player ids they rostered across the season (for VOR/positional)
    roster_player_pts: dict[int, dict[str, list[float]]] = {
        rid: defaultdict(list) for rid in rid_list}
    for wk in reg:
        _, _, pp, _ = _week_index(season, wk)
        for rid, players in pp.items():
            for pid, pts in players.items():
                roster_player_pts[rid][pid].append(float(pts or 0))

    for rid in rid_list:
        weekly = []
        wins = losses = ties = 0
        pf = pa = 0.0
        all_play_w = all_play_l = 0
        close_w = close_l = 0
        avoidable_losses = 0
        actual_sum = optimal_sum = 0.0
        boom = bust = 0
        pos_points: dict[str, float] = defaultdict(float)

        for wk in reg:
            team_pts, opp, pp, starters_pts = _week_index(season, wk)
            if rid not in team_pts:
                continue
            pts = team_pts[rid]
            opp_rid = opp.get(rid)
            opp_pts = team_pts.get(opp_rid, 0.0) if opp_rid is not None else 0.0
            win = pts > opp_pts
            tie = pts == opp_pts
            wins += int(win and not tie)
            losses += int((not win) and not tie)
            ties += int(tie)
            pf += pts
            pa += opp_pts

            # all-play: vs every other team this week
            others = [v for k, v in team_pts.items() if k != rid]
            all_play_w += sum(1 for v in others if pts > v)
            all_play_l += sum(1 for v in others if pts < v)

            # close games
            if opp_rid is not None and abs(pts - opp_pts) <= C.CLOSE_GAME_MARGIN:
                if tie:
                    pass
                elif win:
                    close_w += 1
                else:
                    close_l += 1

            # optimal lineup / efficiency
            eff = matchup_efficiency(
                starters_pts.get(rid, []), pp.get(rid, {}),
                _pos_of(pp.get(rid, {}).keys()), rp, actual_points=pts)
            actual_sum += eff.actual
            optimal_sum += eff.optimal
            if opp_rid is not None and not win and not tie and eff.optimal >= opp_pts:
                avoidable_losses += 1

            # boom/bust vs league weekly distribution
            if league_week_sigma > 0:
                if pts >= league_week_mean + league_week_sigma:
                    boom += 1
                elif pts <= league_week_mean - league_week_sigma:
                    bust += 1

            # positional production from actual starters
            for pid, ppt in zip(season_starters(season, wk, rid),
                                season_starter_points(season, wk, rid)):
                pos_points[primary_position(pid)] += float(ppt or 0)

            weekly.append({
                "week": wk, "pts": round(pts, 2),
                "opp": opp_rid, "opp_pts": round(opp_pts, 2),
                "win": bool(win) if not tie else None,
                "optimal": eff.optimal, "eff": eff.efficiency,
                "plob": eff.left_on_bench,
            })

        scores = [w["pts"] for w in weekly]
        n_games = len(scores)

        # roster construction: VOR over players with >=4 games on this roster
        vors = []
        for pid, wk_pts in roster_player_pts[rid].items():
            if len(wk_pts) >= 4:
                ppg = S.mean(wk_pts)
                base = baselines.get(primary_position(pid), 0.0)
                vors.append(max(ppg - base, 0.0))
        vors.sort(reverse=True)
        vor_total = sum(vors)
        top3_share = S.safe_div(sum(vors[:3]), vor_total, 0.0)

        # all-play expected wins
        ap_games = all_play_w + all_play_l
        ap_pct = S.safe_div(all_play_w, ap_games, 0.5)
        xwins = ap_pct * n_games
        luck = (wins + 0.5 * ties) - xwins

        out[rid] = {
            "roster_id": rid,
            "record": {"w": wins, "l": losses, "t": ties},
            "pf": round(pf, 2), "pa": round(pa, 2),
            "weekly": weekly,
            "games": n_games,
            "consistency": {
                "mean": round(S.mean(scores), 2),
                "std": round(S.stdev(scores), 2),
                "cv": round(S.cv(scores), 4),
                "floor": round(S.percentile(scores, 0.10), 2),
                "ceiling": round(S.percentile(scores, 0.90), 2),
                "high": round(max(scores), 2) if scores else 0,
                "low": round(min(scores), 2) if scores else 0,
                "boom_rate": round(S.safe_div(boom, n_games), 3),
                "bust_rate": round(S.safe_div(bust, n_games), 3),
                "skew": round(S.skewness(scores), 3),
            },
            "efficiency": {
                "actual": round(actual_sum, 2),
                "optimal": round(optimal_sum, 2),
                "plob_total": round(optimal_sum - actual_sum, 2),
                "plob_avg": round(S.safe_div(optimal_sum - actual_sum, n_games), 2),
                "eff": round(S.safe_div(actual_sum, optimal_sum, 1.0), 4),
                "avoidable_losses": avoidable_losses,
            },
            "luck": {
                "all_play_w": all_play_w, "all_play_l": all_play_l,
                "all_play_pct": round(ap_pct, 4),
                "xwins": round(xwins, 2),
                "luck": round(luck, 2),
                "close_w": close_w, "close_l": close_l,
            },
            "positional": {k: round(v, 1) for k, v in pos_points.items()},
            "construction": {
                "vor_total": round(vor_total, 1),
                "top3_share": round(top3_share, 3),
                "gini": round(S.gini(vors), 3),
                "stars": [
                    {"pid": pid, "name": players_map().get(pid, {}).get("full_name", pid),
                     "ppg": round(S.mean(wk), 1), "pos": primary_position(pid)}
                    for pid, wk in sorted(
                        roster_player_pts[rid].items(),
                        key=lambda kv: S.mean(kv[1]), reverse=True)[:5]
                    if len(wk) >= 4
                ],
            },
        }

    # schedule luck: PA percentile within league (high PA faced == unlucky)
    pa_vals = [out[rid]["pa"] for rid in rid_list]
    for rid in rid_list:
        out[rid]["luck"]["pa_pctile"] = round(
            S.percentile_rank(pa_vals, out[rid]["pa"]), 3)

    # final standings + playoff results
    _attach_standings(season, out)
    return out


def season_starters(season: Season, week: int, rid: int) -> list[str]:
    for r in season.matchups.get(week, []):
        if r["roster_id"] == rid:
            return r.get("starters") or []
    return []


def season_starter_points(season: Season, week: int, rid: int) -> list[float]:
    for r in season.matchups.get(week, []):
        if r["roster_id"] == rid:
            return r.get("starters_points") or []
    return []


def _attach_standings(season: Season, out: dict[int, dict]) -> None:
    # Regular-season standings: wins, then points-for (Sleeper tiebreaker).
    order = sorted(out.values(),
                   key=lambda t: (t["record"]["w"] + 0.5 * t["record"]["t"], t["pf"]),
                   reverse=True)
    for i, t in enumerate(order, start=1):
        t["final_standing"] = i
        t["pf_rank"] = i  # provisional; replaced below by pure PF rank

    pf_order = sorted(out.values(), key=lambda t: t["pf"], reverse=True)
    for i, t in enumerate(pf_order, start=1):
        t["pf_rank"] = i

    champ, runner_up, place = _bracket_results(season.winners_bracket)
    for rid, t in out.items():
        t["champion"] = (rid == champ)
        t["runner_up"] = (rid == runner_up)
        t["playoff_finish"] = place.get(rid)
        t["made_playoffs"] = rid in place


def _bracket_results(winners_bracket: list[dict]):
    """Return (champion_rid, runner_up_rid, {rid: final_place})."""
    place: dict[int, int] = {}
    champ = runner_up = None
    for m in winners_bracket:
        p = m.get("p")
        w, l = m.get("w"), m.get("l")
        if p and isinstance(w, int) and isinstance(l, int):
            place[w] = p
            place[l] = p + 1
            if p == 1:
                champ, runner_up = w, l
    return champ, runner_up, place
