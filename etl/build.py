"""Orchestrate the ETL: fetch (optional) -> analyze -> label -> archetype ->
recommend -> (real-football enrich) -> emit slim JSON bundles for the web app.

Run:  python -m etl.build            (uses cached raw; re-fetches if missing)
      python -m etl.build --fetch    (force re-pull Sleeper + nflverse)
"""
from __future__ import annotations

import sys

from . import config as C
from .analyze import assemble
from .archetype import compute_archetypes
from .labels import GROUPS, build_context, label_team
from .metrics_fantasy import league_player_season_ppg, primary_position
from .recommend import recommend_team
from .store import load_season, players_map, seasons
from .util import save_json

try:
    from . import real as real_layer  # real-football enrichment (optional)
except Exception:  # noqa: BLE001
    real_layer = None

try:
    from . import value as value_layer  # dynasty player-value model (optional)
except Exception:  # noqa: BLE001
    value_layer = None


def _team_summary(rid: int, analysis: dict) -> dict:
    season = analysis["latest_season"]
    t = analysis["teams"][rid]
    d = t["seasons"].get(season, {})
    top_labels = [{"label": l["label"], "basis": l["basis"], "tone": l["direction"]}
                  for l in t.get("labels", [])[:4]]
    return {
        "roster_id": rid,
        "team_name": t["team_name"],
        "display_name": t["display_name"],
        "avatar_url": t["avatar_url"],
        "record": d.get("record"),
        "pf": d.get("pf"), "pa": d.get("pa"),
        "final_standing": d.get("final_standing"),
        "champion": d.get("champion"), "runner_up": d.get("runner_up"),
        "archetype": t.get("archetype"),
        "indices": t.get("indices"),
        "strength": (t.get("real") or {}).get("strength", {}).get("overall"),
        "strength_pctile": (t.get("real") or {}).get("strength", {}).get("overall_pctile"),
        "win_now": (t.get("real") or {}).get("strength", {}).get("win_now"),
        "future": (t.get("real") or {}).get("strength", {}).get("future"),
        "luck": d.get("luck", {}).get("luck"),
        "all_play_pct": d.get("luck", {}).get("all_play_pct"),
        "efficiency": d.get("efficiency", {}).get("eff"),
        "cv": d.get("consistency", {}).get("cv"),
        "championships": t["career"]["championships"],
        "career_record": t["career"]["record"],
        "podiums": t["career"]["podiums"],
        "top_labels": top_labels,
    }


def build_players_bundle(analysis: dict) -> dict:
    season = analysis["latest_season"]
    S = load_season(season)
    ppg = league_player_season_ppg(S)
    pm = players_map()
    owner_of_player = {}
    for r in S.rosters:
        for pid in (r.get("players") or []):
            owner_of_player[pid] = r["roster_id"]
    real_players = analysis.get("real_players", {})
    player_values = analysis.get("player_values", {})
    players = []
    for pid, rid in owner_of_player.items():
        p = pm.get(pid, {})
        prod = ppg.get(pid, {})
        rec = {
            "pid": pid,
            "name": p.get("full_name") or (f"{p.get('team','')} DEF"
                                           if p.get("position") == "DEF" else pid),
            "pos": p.get("position") or primary_position(pid),
            "nfl_team": p.get("team"),
            "age": p.get("age"), "years_exp": p.get("years_exp"),
            "roster_id": rid,
            "ppg": round(prod.get("ppg", 0), 1),
            "total": round(prod.get("total", 0), 1),
            "games": prod.get("games", 0),
            "headshot": C.CDN_PLAYER_HEADSHOT.format(player_id=pid)
            if p.get("position") != "DEF" else None,
        }
        # merge the real-football layer (usage, opportunity, signal, env, sos)
        rp = real_players.get(pid)
        if rp and rp.get("has_real"):
            rec["real"] = {k: rp.get(k) for k in (
                "snap_pct", "target_share", "air_yards_share", "wopr", "adot",
                "carries", "targets", "td_dependence", "opp_pctile_nfl",
                "games_played", "games_missed",
                "injury_reports", "real_team", "playoff_sos", "projected_flags")}
            rec["real"]["env_pctile"] = rp.get("team_env", {}).get("env_pctile")
        # dynasty player-value model (the player-quality axis)
        val = player_values.get(pid)
        if val:
            rec["value"] = {k: val.get(k) for k in (
                "player_value", "season_value", "model_value", "model_talent",
                "model_pctile", "market_value", "market_rank", "redraft_value",
                "rd_delta", "risk_score", "availability", "archetype", "grade",
                "stage", "signal", "value_gap", "dir_labels", "trend30",
                "market_tier", "pos_rank", "xfp_pg", "fpoe_pg", "usage_z",
                "age_mult", "value_pctile")}
        players.append(rec)
    players.sort(key=lambda x: x["total"], reverse=True)
    return {"season": season, "players": players}


def build_trends_bundle(analysis: dict) -> dict:
    teams = analysis["teams"]
    seasons_list = analysis["seasons"]
    # scoring environment per season
    scoring = []
    for s in seasons_list:
        Sd = load_season(s)
        from .metrics_fantasy import _week_index
        vals = [p for wk in Sd.regular_weeks
                for p in _week_index(Sd, wk)[0].values()]
        scoring.append({"season": s,
                        "avg_weekly": round(sum(vals) / len(vals), 1) if vals else 0,
                        "high": round(max(vals), 1) if vals else 0})
    # champions lineage
    champions = []
    for s in seasons_list:
        champ_rid = analysis["per_season"][s]["champion"]
        ru_rid = analysis["per_season"][s]["runner_up"]
        oid = analysis["owner_of"][s].get(champ_rid)
        # map to a latest-season team for naming
        team = next((t for t in teams.values()
                     if t["season_rid"].get(s) == champ_rid), None)
        ru = next((t for t in teams.values()
                   if t["season_rid"].get(s) == ru_rid), None)
        champions.append({
            "season": s,
            "champion": team["team_name"] if team else f"Roster {champ_rid}",
            "champion_rid": champ_rid,
            "runner_up": ru["team_name"] if ru else None,
        })
    # season standings tables
    standings = {}
    for s in seasons_list:
        rows = []
        for rid, t in teams.items():
            srid = t["season_rid"].get(s)
            if srid is None or s not in analysis["per_season"]:
                continue
            m = analysis["per_season"][s]["metrics"].get(srid)
            if not m:
                continue
            rows.append({"roster_id": rid, "team_name": t["team_name"],
                         "record": m["record"], "pf": m["pf"], "pa": m["pa"],
                         "final_standing": m.get("final_standing"),
                         "champion": m.get("champion"),
                         "all_play_pct": m["luck"]["all_play_pct"]})
        rows.sort(key=lambda r: (r["final_standing"] or 99))
        standings[s] = rows
    # rivalry matrix (latest roster ids)
    rivalry = {}
    for rid, t in teams.items():
        rivalry[str(rid)] = {str(r["opp_roster_id"]):
                             {"w": r["w"], "l": r["l"], "t": r["t"],
                              "meetings": r["meetings"]}
                             for r in t["rivalries"]}
    # per-team roster-strength trend (historical-accurate, model-based per season)
    strength_trend = [
        {"roster_id": rid, "team_name": t["team_name"],
         "points": t.get("strength_trend", [])}
        for rid, t in sorted(teams.items())
    ]
    return {"scoring": scoring, "champions": champions, "standings": standings,
            "rivalry_matrix": rivalry, "seasons": seasons_list,
            "strength_trend": strength_trend}


def build_trades_bundle(analysis: dict) -> dict:
    out = {"seasons": {}}
    teams = analysis["teams"]
    name_by_season_rid = {}
    for rid, t in teams.items():
        for s, srid in t["season_rid"].items():
            if srid is not None:
                name_by_season_rid[(s, srid)] = t["team_name"]
    for s, ps in analysis["per_season"].items():
        trades = []
        for tr in ps["trades"]:
            tr2 = {**tr, "team_names": {str(r): name_by_season_rid.get((s, r), f"R{r}")
                                       for r in tr["roster_ids"]}}
            trades.append(tr2)
        # FAAB / waiver activity leaderboard
        activity = []
        for srid, mg in ps["management"].items():
            activity.append({"roster_id": srid,
                             "team_name": name_by_season_rid.get((s, srid), f"R{srid}"),
                             "adds": mg["adds"], "faab_used": mg["faab_used"],
                             "trades": mg["trades"],
                             "waiver_hit_rate": mg["waiver_hit_rate"]})
        out["seasons"][s] = {"trades": trades,
                             "activity": sorted(activity, key=lambda x: x["adds"],
                                                reverse=True)}
    return out


def build_draft_bundle(analysis: dict) -> dict:
    out = {"seasons": {}}
    teams = analysis["teams"]
    name_by_season_rid = {(s, srid): t["team_name"]
                          for t in teams.values()
                          for s, srid in t["season_rid"].items() if srid is not None}
    for s, ps in analysis["per_season"].items():
        draft = ps["draft"]
        board = draft["board"]
        # ROOKIE drafts only — skip the inaugural startup (many rounds, not rookies).
        n_rounds = max((r.get("round", 0) for r in board), default=0)
        if n_rounds > 6:
            continue
        board = [{**r, "team_name":
                  name_by_season_rid.get((s, r["roster_id"]), f"R{r['roster_id']}")}
                 for r in board]
        per_team = [{"roster_id": srid,
                     "team_name": name_by_season_rid.get((s, srid), f"R{srid}"), **dt}
                    for srid, dt in draft["per_team"].items()]
        out["seasons"][s] = {"board": board,
                             "per_team": sorted(per_team, key=lambda x: x["roi"],
                                                reverse=True),
                             "expected_curve": draft["expected_curve"]}
    out["preview"] = build_draft_preview(analysis)
    return out


def build_draft_preview(analysis: dict) -> dict | None:
    """Projected next-season rookie draft: order = reverse of the latest regular
    standings; ownership reflects traded picks. Marked projected."""
    latest = analysis["latest_season"]
    next_year = int(latest) + 1
    S = load_season(latest)
    n_teams = len(S.rosters)
    rounds = int((S.league.get("settings") or {}).get("draft_rounds") or 3)
    teams = analysis["teams"]
    name = {rid: t["team_name"] for rid, t in teams.items()}
    # League rule: rookie draft order = reverse Max Points For (potential points).
    # slot 1 (x.01) = the team with the LOWEST max-PF last season.
    maxpf = {r["roster_id"]: (r["settings"].get("ppts", 0)
                              + r["settings"].get("ppts_decimal", 0) / 100)
             for r in S.rosters}
    by_slot = sorted(S.rosters, key=lambda r: maxpf[r["roster_id"]])
    slot_to_roster = {i + 1: r["roster_id"] for i, r in enumerate(by_slot)}
    # traded next-year picks: (round, original roster) -> current owner
    traded = {}
    for tp in S.traded_picks:
        if str(tp.get("season")) == str(next_year):
            traded[(tp.get("round"), tp.get("roster_id"))] = tp.get("owner_id")
    board = []
    for rnd in range(1, rounds + 1):
        for slot in range(1, n_teams + 1):
            orig = slot_to_roster.get(slot)
            owner = traded.get((rnd, orig), orig)
            board.append({
                "round": rnd, "slot": slot, "pick_no": (rnd - 1) * n_teams + slot,
                "orig_roster": orig, "orig_team": name.get(orig, f"R{orig}"),
                "owner_roster": owner, "owner_team": name.get(owner, f"R{owner}"),
                "traded": owner != orig,
            })
    return {"season": str(next_year), "rounds": rounds,
            "order_basis": f"projected — reverse of {latest} Max Points For (potential points)",
            "board": board}


def main(argv: list[str]) -> int:
    fetch = "--fetch" in argv
    C.ensure_dirs()

    if fetch or not (C.RAW_SLEEPER / "chain.json").exists():
        from .fetch_sleeper import main as fetch_sleeper
        if fetch_sleeper() != 0:
            return 1
    if fetch or not any(C.RAW_NFLVERSE.glob("*.parquet")):
        from .fetch_nflverse import main as fetch_nflverse
        league_yrs = [int(s) for s in seasons()]
        # prior years for history + the league seasons; pbp only for league seasons
        hist = sorted(set(C.NFL_HISTORY_SEASONS) | set(league_yrs))
        fetch_nflverse(seasons=hist, pbp_seasons=league_yrs)
    market_yrs = [int(s) for s in seasons()]
    past_market = [y for y in market_yrs if y != max(market_yrs)] if market_yrs else []
    if (fetch or not (C.RAW_MARKET / "fantasycalc_sf_dynasty.json").exists()
            or any(not (C.RAW_MARKET / f"dp_values_players_{y}.csv").exists()
                   for y in past_market)):
        from .fetch_market import main as fetch_market
        fetch_market(force=fetch, hist_seasons=past_market)

    print("[build] analyzing …")
    analysis = assemble()
    # archetypes + indices for EVERY season (each as of that season's end)
    for s in analysis["seasons"]:
        compute_archetypes(analysis, s)

    # real-football enrichment (adds team['real'], player real layer, real labels)
    real_data = None
    if real_layer is not None:
        try:
            real_data = real_layer.enrich(analysis)
            print("[build] real-football layer attached")
        except Exception as exc:  # noqa: BLE001
            print(f"[build] WARNING real-football layer failed: {exc}", file=sys.stderr)

    # Dynasty player-value model (real football + market; injury = separate risk).
    # Runs AFTER real_layer so it can overwrite buy/sell + team strength on the
    # value axis (not realized fantasy points).
    if value_layer is not None:
        try:
            value_layer.enrich(analysis)
            print("[build] dynasty value layer attached")
        except Exception as exc:  # noqa: BLE001
            print(f"[build] WARNING value layer failed: {exc}", file=sys.stderr)

    # Dynasty-aware trade grading + draft-pick realization (needs player_values).
    try:
        from . import trades_engine
        trades_engine.augment(analysis)
        print("[build] trade dynasty value + pick realization attached")
    except Exception as exc:  # noqa: BLE001
        print(f"[build] WARNING trades engine failed: {exc}", file=sys.stderr)

    # Per-season historical roster snapshots (same columns as the current view,
    # as-of-that-season) — needs the value model, so runs after it.
    if value_layer is not None:
        try:
            value_layer.build_season_rosters(analysis)
            print("[build] per-season rosters attached")
        except Exception as exc:  # noqa: BLE001
            print(f"[build] WARNING season rosters failed: {exc}", file=sys.stderr)

    # labels + recommendations — regenerated PER SEASON (as of that season's end).
    # The current real-football value layer (buy/sell, market) only applies to the
    # latest season; past seasons get fantasy + that-season positional labels.
    latest = analysis["latest_season"]
    has_real = real_layer is not None and real_data is not None
    for s in analysis["seasons"]:
        ctx = build_context(analysis, s)
        for rid, t in analysis["teams"].items():
            if s not in t["seasons"]:
                continue
            labels = label_team(rid, analysis, ctx)
            if s == latest and has_real:
                labels += real_layer.real_labels(rid, analysis, real_data)
            labels.sort(key=lambda x: x["score"], reverse=True)
            recs = recommend_team(rid, analysis, labels, s)
            if s == latest and has_real:
                recs = real_layer.merge_recs(rid, analysis, real_data, recs)
            t["seasons"][s]["labels"] = labels
            t["seasons"][s]["recommendations"] = recs
    # top-level (summaries / overview / power rankings) mirror the latest season
    for rid, t in analysis["teams"].items():
        t["labels"] = t["seasons"].get(latest, {}).get("labels", [])
        t["recommendations"] = t["seasons"].get(latest, {}).get("recommendations", [])

    # ---- emit bundles ----
    league_bundle = {
        "league": analysis["league"],
        "seasons": analysis["seasons"],
        "latest_season": analysis["latest_season"],
        "n_teams": analysis["n_teams"],
        "groups": GROUPS,
        "teams": [_team_summary(rid, analysis)
                  for rid in sorted(analysis["teams"])],
        "generated_for": C.LEAGUE_ID,
    }
    save_json(league_bundle, C.DATA_OUT / "league.json")

    for rid, t in analysis["teams"].items():
        save_json(t, C.DATA_OUT / "teams" / f"{rid}.json")

    save_json(build_players_bundle(analysis), C.DATA_OUT / "players.json")
    save_json(build_trends_bundle(analysis), C.DATA_OUT / "trends.json")
    save_json(build_trades_bundle(analysis), C.DATA_OUT / "trades.json")
    save_json(build_draft_bundle(analysis), C.DATA_OUT / "draft.json")

    print(f"[build] wrote bundles to {C.DATA_OUT}")
    print(f"[build] teams: {len(analysis['teams'])}, seasons: {analysis['seasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
