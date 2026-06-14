"""Dynasty player-value model — the PLAYER/TEAM quality axis.

Value is a FORWARD-LOOKING property of real football, never of realized fantasy
points:
  ModelValue  = z(xFP/g) + position usage_z + capped efficiency_z, age-adjusted
  MarketValue = FantasyCalc superflex-dynasty value (crowd-priced talent+age+
                injury+outlook), joined directly on Sleeper player_id
  PlayerValue = 0.55*market + 0.45*model            (0..100, dynasty)
Injuries are a SEPARATE durability axis: talent is measured per game actually
played; AvailabilityScore (proj games/17) and RiskScore are their own fields and
NEVER reduce PlayerValue. A hurt star reads "elite value, high risk" — a BUY, not
a discount.

Manager quality stays entirely on the fantasy axis (metrics_fantasy/labels) and
never touches these numbers.
"""
from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from . import config as C
from . import statlib as St
from .crosswalk import _xw
from .lineup import optimal_lineup
from .metrics_fantasy import primary_position
from .real import weekly_stats
from .store import fantasy_positions, players_map, seasons
from .util import load_json

# Full per-age dynasty multipliers (peak = 1.0). Forward value decays with age.
AGE_CURVES = {
    "RB": {21: .92, 22: .96, 23: .99, 24: 1, 25: 1, 26: .98, 27: .93, 28: .85,
           29: .72, 30: .58, 31: .45, 32: .33, 33: .22},
    "WR": {21: .95, 22: .97, 23: .98, 24: .99, 25: 1, 26: 1, 27: 1, 28: .99,
           29: .96, 30: .92, 31: .85, 32: .76, 33: .66, 34: .55},
    "TE": {23: .94, 24: .96, 25: .98, 26: 1, 27: 1, 28: .99, 29: .97, 30: .94,
           31: .90, 32: .85, 33: .78, 34: .70},
    "QB_pocket": {23: .95, 24: .97, 25: .99, 26: 1, 27: 1, 28: 1, 29: 1, 30: 1,
                  31: .99, 32: .97, 33: .95, 34: .91, 35: .86, 36: .80, 37: .74},
    "QB_dual": {24: 1, 25: 1, 26: 1, 27: 1, 28: .99, 29: .97, 30: .94, 31: .90,
                32: .84, 33: .76, 34: .68},
}
CLIFF_AGE = {"RB": 27, "WR": 31, "TE": 31, "QB_dual": 32, "QB_pocket": 35}
# Dynasty draft-capital prior (approx PPR/g expectation by round) for thin samples.
DRAFT_PRIOR = {
    "RB": {1: 13.1, 2: 9.6, 3: 7.0, 4: 5.5, 5: 4.0},
    "WR": {1: 10.1, 2: 8.2, 3: 5.5, 4: 4.1, 5: 4.1},
    "TE": {1: 7.5, 2: 5.5, 3: 4.0, 4: 3.0, 5: 2.5},
    "QB": {1: 14.0, 2: 9.0, 3: 6.0, 4: 4.0, 5: 3.0},
}


def age_mult(pos: str, age: float | None, qb_type: str = "pocket") -> float:
    if age is None:
        return 0.92
    key = f"QB_{qb_type}" if pos == "QB" else pos
    curve = AGE_CURVES.get(key)
    if not curve:
        return 1.0
    a = int(round(age))
    if a <= min(curve):
        return curve[min(curve)]
    if a >= max(curve):
        return curve[max(curve)]
    return curve.get(a, curve[min(curve, key=lambda k: abs(k - a))])


# ---------------------------------------------------------------------------
# Market loaders
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def load_fantasycalc() -> dict[str, dict]:
    raw = load_json(C.RAW_MARKET / "fantasycalc_sf_dynasty.json", []) or []
    out: dict[str, dict] = {}
    for r in raw:
        p = r.get("player") or {}
        sid = p.get("sleeperId")
        if not sid:
            continue
        out[str(sid)] = {
            "value": r.get("value", 0),
            "redraft": r.get("redraftValue", 0),
            "rd_diff": r.get("redraftDynastyValueDifference", 0),
            "overall_rank": r.get("overallRank"),
            "pos_rank": r.get("positionRank"),
            "trend30": r.get("trend30Day", 0),
            "tier": r.get("maybeTier"),
            "msd": r.get("maybeMovingStandardDeviation"),
        }
    return out


def _load_dp_market(path) -> dict[str, float]:
    """DynastyProcess value_2qb (SF dynasty) keyed by Sleeper id, from a CSV path."""
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    xw = _xw().reset_index()  # has sleeper_id + fantasypros_id
    fp_to_sleeper = {}
    for _, r in xw.iterrows():
        fp = r.get("fantasypros_id")
        if pd.notna(fp):
            fp_to_sleeper[str(int(fp)) if isinstance(fp, float) else str(fp)] = r["sleeper_id"]
    out = {}
    for _, r in df.iterrows():
        sid = fp_to_sleeper.get(str(r.get("fp_id")))
        if sid:
            out[str(sid)] = float(r.get("value_2qb") or 0)
    return out


@functools.lru_cache(maxsize=1)
def load_dp_value_2qb() -> dict[str, float]:
    """Current DynastyProcess value_2qb keyed by Sleeper id (ECR cross-check)."""
    return _load_dp_market(C.RAW_MARKET / "dp_values_players.csv")


@functools.lru_cache(maxsize=4)
def load_dp_market_season(year: int) -> dict[str, float]:
    """End-of-`year` DynastyProcess SF-dynasty market (sleeper id -> value), the
    past-season analog of FantasyCalc that anchors that season's value."""
    return _load_dp_market(C.RAW_MARKET / f"dp_values_players_{year}.csv")


# ---------------------------------------------------------------------------
# Real-football aggregation + xFP backbone
# ---------------------------------------------------------------------------
def _season_agg(season: int) -> pd.DataFrame:
    df = weekly_stats(season)
    g = df.groupby("player_id").agg(
        games=("week", "nunique"),
        position=("position", "first"),
        carries=("carries", "sum"),
        targets=("targets", "sum"),
        receptions=("receptions", "sum"),
        rec_air_yards=("receiving_air_yards", "sum"),
        attempts=("attempts", "sum"),
        rush_yards=("rushing_yards", "sum"),
        rec_yards=("receiving_yards", "sum"),
        pass_yards=("passing_yards", "sum"),
        rush_tds=("rushing_tds", "sum"),
        rec_tds=("receiving_tds", "sum"),
        pass_tds=("passing_tds", "sum"),
        interceptions=("passing_interceptions", "sum"),
        fpts_ppr=("fantasy_points_ppr", "sum"),
        wopr=("wopr", "mean"),
        target_share=("target_share", "mean"),
        air_yards_share=("air_yards_share", "mean"),
        pass_epa=("passing_epa", "sum"),
        pass_cpoe=("passing_cpoe", "mean"),
        rec_epa=("receiving_epa", "sum"),
        rush_epa=("rushing_epa", "sum"),
    )
    return g


def _league_td_rates(agg: pd.DataFrame) -> dict[str, float]:
    return {
        "rush": St.safe_div(agg["rush_tds"].sum(), agg["carries"].sum(), 0.02),
        "rec": St.safe_div(agg["rec_tds"].sum(), agg["targets"].sum(), 0.05),
        "pass": St.safe_div(agg["pass_tds"].sum(), agg["attempts"].sum(), 0.045),
    }


def _build_pool(season: int):
    """Per-player real metrics + z-scores within position (NFL pool, games>=6)."""
    agg = _season_agg(season)
    td = _league_td_rates(agg)
    rows = {}
    for gsis, r in agg.iterrows():
        g = int(r["games"] or 0)
        if g == 0:
            continue
        pos = r["position"]
        # 0.5-PPR expected points: actual yards/receptions, EXPECTED (not actual) TDs
        xfp = (
            float(r["pass_yards"]) * 0.04 + float(r["attempts"]) * td["pass"] * 4
            - float(r["interceptions"]) * 2
            + float(r["rush_yards"]) * 0.1 + float(r["carries"]) * td["rush"] * 6
            + float(r["receptions"]) * 0.5 + float(r["rec_yards"]) * 0.1
            + float(r["targets"]) * td["rec"] * 6
        )
        actual = (
            float(r["pass_yards"]) * 0.04 + float(r["pass_tds"]) * 4
            - float(r["interceptions"]) * 2
            + float(r["rush_yards"]) * 0.1 + float(r["rush_tds"]) * 6
            + float(r["receptions"]) * 0.5 + float(r["rec_yards"]) * 0.1
            + float(r["rec_tds"]) * 6
        )
        adot = St.safe_div(float(r["rec_air_yards"]), float(r["targets"]))
        rows[gsis] = {
            "pos": pos, "games": g,
            "xfp_pg": xfp / g, "actual_pg": actual / g, "fpoe_pg": (actual - xfp) / g,
            "wopr": float(r["wopr"] or 0), "target_share": float(r["target_share"] or 0),
            "air_yards_share": float(r["air_yards_share"] or 0), "adot": adot,
            "weighted_opp_pg": (float(r["carries"]) + 2 * float(r["targets"])) / g,
            "dropbacks_pg": (float(r["attempts"]) + float(r["carries"])) / g,
            "rush_att_pg": float(r["carries"]) / g,
            "epa_per_att": St.safe_div(float(r["pass_epa"]), float(r["attempts"])),
            "cpoe": float(r["pass_cpoe"] or 0),
            "rec_epa_per_tgt": St.safe_div(float(r["rec_epa"]), float(r["targets"])),
            "snaps_td_dep": St.safe_div(
                (float(r["rush_tds"]) + float(r["rec_tds"])) * 6 + float(r["pass_tds"]) * 4,
                actual if actual else 1),
        }
    # z-score pools by position (games>=6)
    pools: dict[str, dict[str, list]] = {}
    for gsis, d in rows.items():
        if d["games"] >= 6:
            pools.setdefault(d["pos"], {})
            for k in ("xfp_pg", "wopr", "target_share", "air_yards_share", "adot",
                      "weighted_opp_pg", "dropbacks_pg", "rush_att_pg",
                      "epa_per_att", "cpoe", "rec_epa_per_tgt"):
                pools[d["pos"]].setdefault(k, []).append(d[k])

    def z(pos, k, v):
        return St.zscore(pools.get(pos, {}).get(k, [v]), v)

    for gsis, d in rows.items():
        pos = d["pos"]
        if pos in ("WR", "TE"):
            d["usage_z"] = (0.45 * z(pos, "wopr", d["wopr"])
                            + 0.25 * z(pos, "target_share", d["target_share"])
                            + 0.15 * z(pos, "air_yards_share", d["air_yards_share"])
                            + 0.15 * z(pos, "adot", d["adot"]))
            d["eff_z"] = 0.5 * z(pos, "rec_epa_per_tgt", d["rec_epa_per_tgt"])
            d["eff_w"] = 0.15
        elif pos == "RB":
            d["usage_z"] = (0.7 * z(pos, "weighted_opp_pg", d["weighted_opp_pg"])
                            + 0.3 * z(pos, "target_share", d["target_share"]))
            d["eff_z"] = 0.0  # rush efficiency non-sticky; tiebreaker only
            d["eff_w"] = 0.15
        elif pos == "QB":
            d["usage_z"] = (0.55 * z(pos, "dropbacks_pg", d["dropbacks_pg"])
                            + 0.45 * z(pos, "rush_att_pg", d["rush_att_pg"]))
            d["eff_z"] = (0.5 * z(pos, "epa_per_att", d["epa_per_att"])
                          + 0.5 * z(pos, "cpoe", d["cpoe"]))
            d["eff_w"] = 0.20
        else:
            d["usage_z"] = 0.0
            d["eff_z"] = 0.0
            d["eff_w"] = 0.15
        xfp_w = 0.50 if pos == "QB" else 0.55
        core = (xfp_w * z(pos, "xfp_pg", d["xfp_pg"]) + 0.30 * d["usage_z"]
                + d["eff_w"] * d["eff_z"])
        w = d["games"] / (d["games"] + 5)  # empirical-Bayes shrink toward pos mean (0 in z)
        d["core"] = w * core
    return rows


# ---------------------------------------------------------------------------
# Enrichment entry
# ---------------------------------------------------------------------------
def enrich(analysis: dict) -> dict:
    latest = int(analysis["latest_season"])
    pool = _build_pool(latest)
    # career games/season across MULTIPLE prior years (for accurate availability)
    hist_years = sorted(set(C.NFL_HISTORY_SEASONS) | {int(x) for x in seasons()})
    games_by_gsis: dict[str, list[int]] = {}
    for yr in hist_years:
        try:
            agg = _season_agg(yr)
        except Exception:  # noqa: BLE001
            continue
        for gsis, r in agg.iterrows():
            games_by_gsis.setdefault(gsis, []).append(int(r["games"] or 0))

    fc = load_fantasycalc()
    dp = load_dp_value_2qb()
    # Market is the consensus dynasty value (age/injury/outlook already priced in).
    # Use the FULL FantasyCalc landscape as the percentile reference so a top-50
    # player reads as elite (linear value÷max crushes everyone below the very top).
    all_fc_values = [v["value"] for v in fc.values()] or [1]
    all_fc_redraft = [v["redraft"] for v in fc.values()] or [1]
    pm = players_map()

    # rostered players across the latest season
    from .store import load_season
    Sd = load_season(str(latest))
    rostered = {pid: r["roster_id"] for r in Sd.rosters
                for pid in (r.get("players") or [])}
    # Rank market value among ROSTERED players (not all ~461) so the league's
    # owned players spread across 0-100 instead of all clustering near the top.
    rostered_market = [fc[str(pid)]["value"] for pid in rostered if str(pid) in fc]

    # First pass: compute model_dynasty + market percentile to enable league grades
    profiles: dict[str, dict] = {}
    pool_core = [d["core"] for d in pool.values() if d["games"] >= 6]
    for pid, rid in rostered.items():
        p = pm.get(pid, {})
        pos = p.get("position") or primary_position(pid)
        age = p.get("age")
        on_nfl_team = bool(p.get("team"))  # None => not on an NFL roster (e.g. out of league)
        ids = _gsis(pid)
        d = pool.get(ids) if ids else None
        m = fc.get(str(pid))
        qb_type = "dual" if (d and d.get("rush_att_pg", 0) >= 3.5) else "pocket"
        amult = age_mult(pos, age, qb_type)

        # MARKET (consensus) percentile among ROSTERED players — the anchor. Age
        # is already baked into market value, so it is NOT re-applied here.
        market_pctile = St.percentile_rank(rostered_market, m["value"]) * 100 if m else None
        # MODEL: real-football talent percentile (age-neutral) + an age-adjusted
        # dynasty estimate used only for the BUY/SELL signal (never to re-discount value).
        model_talent = None
        model_dynasty = None
        if d and d["games"] >= 4:
            model_talent = St.percentile_rank(pool_core or [d["core"]], d["core"]) * 100
            model_dynasty = model_talent * amult
        # rookie / thin sample: draft-capital prior (age-adjusted)
        if (not d or d["games"] < 8):
            dr = _draft_round(pid)
            if dr and pos in DRAFT_PRIOR:
                prior = min(100, DRAFT_PRIOR[pos].get(dr, 3.0) / 14.0 * 100) * amult
                model_dynasty = prior if model_dynasty is None else 0.5 * model_dynasty + 0.5 * prior
                model_talent = prior if model_talent is None else model_talent

        # PlayerValue: market dominates (it IS the dynasty consensus). The real-
        # football talent nudges it; age is NOT re-applied (market has it).
        if market_pctile is not None and model_talent is not None:
            player_value = 0.80 * market_pctile + 0.20 * model_talent
        elif market_pctile is not None:
            player_value = market_pctile
        elif model_dynasty is not None:
            player_value = model_dynasty
        else:
            player_value = 0.0
        # GUARDRAIL: not on an NFL roster and unranked by the market => irrelevant
        # (out of the league / retired / suspended). Floor it; never a "Rising Talent".
        if not on_nfl_team and market_pctile is None:
            player_value = min(player_value, 6.0)

        # availability + risk (SEPARATE)
        gps = games_by_gsis.get(ids, [])
        career_gps = St.mean(gps) if gps else 16
        proj_games = 0.55 * career_gps + 0.45 * 16
        availability = St.clamp(proj_games / 17, 0.47, 1.0)
        cliff = CLIFF_AGE.get(f"QB_{qb_type}" if pos == "QB" else pos, 99)
        age_risk = St.clamp(((age or 0) - (cliff - 2)) / 6) if age else 0
        inj = (analysis.get("real_players", {}).get(pid, {}) or {})
        inj_norm = St.clamp((inj.get("injury_reports", 0)) / 10)
        risk = round(100 * St.clamp(0.45 * (1 - availability) / 0.53
                                    + 0.30 * age_risk + 0.25 * inj_norm), 0)

        profiles[pid] = {
            "pid": pid, "roster_id": rid, "name": p.get("full_name") or pid, "pos": pos,
            "age": age, "years_exp": p.get("years_exp"),
            "on_nfl_team": on_nfl_team,
            "qb_type": qb_type if pos == "QB" else None,
            "player_value": round(player_value, 1),
            "model_value": round(model_dynasty, 1) if model_dynasty is not None else None,
            "model_talent": round(model_talent, 1) if model_talent is not None else None,
            "market_value": round(market_pctile, 1) if market_pctile is not None else None,
            "market_raw": m["value"] if m else None,
            "market_rank": m["overall_rank"] if m else None,
            "redraft_value": round(St.percentile_rank(all_fc_redraft, m["redraft"]) * 100, 1) if m else None,
            "rd_delta": m["rd_diff"] if m else None,
            "trend30": m["trend30"] if m else None,
            "market_tier": m["tier"] if m else None,
            "pos_rank": m["pos_rank"] if m else None,
            "dp_value_2qb": dp.get(str(pid)),
            "age_mult": round(amult, 3),
            "availability": round(availability, 3),
            "risk_score": int(risk),
            "season_value": round(player_value * availability, 1),
            "xfp_pg": round(d["xfp_pg"], 2) if d else None,
            "fpoe_pg": round(d["fpoe_pg"], 2) if d else None,
            "usage_z": round(d["usage_z"], 2) if d else None,
            "td_dependence": round(d["snaps_td_dep"], 3) if d else None,
            "adot": round(d["adot"], 1) if d else None,
            "games": d["games"] if d else 0,
        }

    # league percentiles for buy/sell + tiers
    pv_all = [pr["player_value"] for pr in profiles.values()]
    # Put the model's opinion on the SAME 0-100 scale as the market: percentile of
    # model_dynasty AMONG ROSTERED players. market_value is already a rostered
    # percentile, so model_pctile - market_value is a clean mispricing gap centered
    # near 0 (the buy/sell spine). Comparing the old raw model_dynasty (NFL-pool
    # percentile × age) to a rostered-market percentile was apples-to-oranges and
    # biased every gap ~+24, which is why nothing ever read SELL.
    model_dyn_vals = [pr["model_value"] for pr in profiles.values()
                      if pr["model_value"] is not None]
    for pr in profiles.values():
        pr["value_pctile"] = round(St.percentile_rank(pv_all, pr["player_value"]), 3)
        pr["model_pctile"] = (round(St.percentile_rank(model_dyn_vals, pr["model_value"]) * 100, 1)
                              if pr["model_value"] is not None else None)
        pr.update(_classify(pr))

    analysis["player_values"] = profiles
    _attach_team_strength(analysis, profiles)
    compute_strength_trend(analysis)
    return {"profiles": profiles}


def compute_strength_trend(analysis: dict) -> None:
    """Per-team roster-strength for EACH season, computed from THAT season's real
    stats + age-at-the-time (model-only, no current market) so the history is
    accurate to the year it represents. Attaches team['strength_trend']."""
    from .store import load_season
    seasons_list = analysis["seasons"]
    latest_year = int(analysis["latest_season"])
    pm = players_map()
    per_season: dict[str, dict[int, dict]] = {}
    for s in seasons_list:
        yr = int(s)
        try:
            pool = _build_pool(yr)
        except Exception:  # noqa: BLE001
            continue
        cores = [d["core"] for d in pool.values() if d["games"] >= 6]
        Sd = load_season(s)
        rp = Sd.league["roster_positions"]
        modelv: dict[str, float] = {}
        for r in Sd.rosters:
            for pid in (r.get("players") or []):
                d = pool.get(_gsis(pid))
                if not d or d["games"] < 4:
                    modelv[pid] = 0.0
                    continue
                p = pm.get(pid, {})
                age = p.get("age")
                age_at = (age - (latest_year - yr)) if age is not None else None
                pos = p.get("position") or primary_position(pid)
                qb_type = "dual" if d.get("rush_att_pg", 0) >= 3.5 else "pocket"
                core_pctile = St.percentile_rank(cores or [d["core"]], d["core"]) * 100
                modelv[pid] = core_pctile * age_mult(pos, age_at, qb_type)
        team_val: dict[int, float] = {}
        by_pos_raw: dict[int, dict[str, float]] = {}
        for r in Sd.rosters:
            vmap = {pid: modelv.get(pid, 0.0) for pid in (r.get("players") or [])}
            pos_of = {pid: fantasy_positions(pid) for pid in vmap}
            team_val[r["roster_id"]] = optimal_lineup(vmap, pos_of, rp).total
            bp: dict[str, list] = {}
            for pid, vv in vmap.items():
                bp.setdefault(primary_position(pid), []).append(vv)
            by_pos_raw[r["roster_id"]] = {
                pos: round(sum(sorted(vs, reverse=True)[:_starts(pos)]), 1)
                for pos, vs in bp.items()}
        vals = list(team_val.values())
        pos_lists: dict[str, list] = {}
        for bp in by_pos_raw.values():
            for pos, vv in bp.items():
                pos_lists.setdefault(pos, []).append(vv)
        per_season[s] = {rid: {
            "value": round(v, 1), "pctile": round(St.percentile_rank(vals, v), 3),
            "by_pos": {pos: {"value": by_pos_raw[rid].get(pos, 0),
                             "pctile": round(St.percentile_rank(
                                 pos_lists.get(pos, [0]), by_pos_raw[rid].get(pos, 0)), 3)}
                       for pos in ("QB", "RB", "WR", "TE")}}
            for rid, v in team_val.items()}
    latest = analysis["latest_season"]
    for rid, t in analysis["teams"].items():
        trend = []
        # attach per-season strength to each season detail (for per-season labels)
        for s in seasons_list:
            srid = t["season_rid"].get(s)
            if srid is None or srid not in per_season.get(s, {}):
                continue
            if s == latest and (t.get("real") or {}).get("strength"):
                t["seasons"][s]["strength"] = {
                    "overall_pctile": t["real"]["strength"]["overall_pctile"],
                    "by_pos": t["real"]["strength"]["by_pos"]}
            elif s in t["seasons"]:
                t["seasons"][s]["strength"] = {
                    "overall_pctile": per_season[s][srid]["pctile"],
                    "by_pos": per_season[s][srid]["by_pos"]}
        for s in seasons_list:
            srid = t["season_rid"].get(s)
            if srid is None or srid not in per_season.get(s, {}):
                continue
            # latest point uses the SAME blended strength as Power Rankings so the
            # two views agree; earlier seasons use the per-season real-football model.
            if s == latest and (t.get("real") or {}).get("strength"):
                e = {"value": t["real"]["strength"]["overall"],
                     "pctile": t["real"]["strength"]["overall_pctile"]}
            else:
                e = per_season[s][srid]
            trend.append({"season": s, **e})
        t["strength_trend"] = trend


def _classify(pr: dict) -> dict:
    pv = pr["player_value"]
    pos = pr["pos"]
    age = pr.get("age")
    mp = pr.get("model_pctile")     # our real-football opinion (rostered pctile, 0-100)
    mk = pr.get("market_value")     # market's opinion (rostered pctile, 0-100); None historically
    fpoe = pr.get("fpoe_pg")
    td = pr.get("td_dependence") or 0
    usage = pr.get("usage_z") or 0
    trend = pr.get("trend30") or 0
    games = pr.get("games", 0)
    vp = pr.get("value_pctile", 0.5)  # standing AMONG ROSTERED players

    # GUARDRAIL: not on an NFL roster and unranked by the market => out of the league.
    if not pr.get("on_nfl_team") and pr.get("market_value") is None:
        return {"archetype": "Out of the League", "grade": "fringe", "stage": "none",
                "signal": "HOLD", "value_gap": 0.0, "dir_labels": ["Inactive"]}

    # ---- value GRADE — percentile-based so it self-calibrates (no tier inflation) ----
    grade = ("star" if vp >= 0.92 else "starter" if vp >= 0.62
             else "depth" if vp >= 0.30 else "fringe")

    # ---- career STAGE (age dimension) ----
    cliff = CLIFF_AGE.get(f"QB_{pr['qb_type']}" if pos == "QB" else pos, 99)
    young_age = {"RB": 23, "WR": 24, "TE": 24, "QB": 25}.get(pos, 24)
    yoe = pr.get("years_exp")
    # rookie/prospect = genuinely little NFL résumé (not just a veteran who missed time)
    is_rookie = (yoe is not None and yoe <= 1) and games < 10
    if age is None:
        stage = "prime"
    elif age >= cliff and (pr.get("age_mult") or 1) < 0.92:
        stage = "aging"
    elif age <= young_age:
        stage = "young"
    else:
        stage = "prime"
    rising = usage >= 0.5 or trend >= 60  # role/market trajectory dimension

    # ---- composite ARCHETYPE (value × stage × trajectory) ----
    if is_rookie:
        arch = "Blue-Chip Prospect" if pv >= 55 else "Prospect Stash" if pv >= 28 else "Deep Prospect"
    elif grade == "star":
        arch = ("Aging Star" if stage == "aging"
                else "Franchise Cornerstone" if stage == "young" else "Established Star")
    elif grade == "starter":
        arch = ("Win-Now Veteran" if stage == "aging"
                else ("Ascending Starter" if rising else "Rising Talent") if stage == "young"
                else "Proven Starter")
    elif grade == "depth":
        arch = ("Fading Veteran" if stage == "aging"
                else "Upside Flier" if stage == "young" else "Known Depth")
    else:  # fringe
        arch = ("Deep Sleeper" if stage == "young" else "Roster Filler")

    # ---- BUY / SELL / HOLD: market mispricing leads, regression + age confirm ----
    # Every season now has a dynasty market (FantasyCalc current / DynastyProcess
    # past), so the same three-lens vote applies throughout:
    #   • market mispricing: model_pctile vs market_pctile on a common 0-100 scale
    #   • real-football regression: fantasy points vs expected (FPOE) + TD-reliance
    #   • age / career stage: aging studs are sell-windows; ascending youth are buys
    # Buying needs a real role (so percentile noise on low-snap filler doesn't fire)
    # and dynasty relevance; selling on "market rates him above our model" applies
    # only to AGING players (the market is slow to discount the cliff) — never to
    # ascending young / prime studs; career-year sells come through regression.
    gap = (mp - mk) if (mp is not None and mk is not None) else None
    real_role = usage >= 0.3            # a genuine NFL role (above positional average)
    buy = sell = 0.0
    buyable = stage == "young" or grade in ("starter", "depth", "star")
    if gap is not None:
        if gap >= 12 and real_role and buyable:
            buy += min(1.0 + (gap - 12) / 14, 2.0)
        elif gap <= -12 and stage == "aging":
            sell += min(1.0 + (-gap - 12) / 14, 2.0)
    if fpoe is not None and fpoe <= -2.0 and usage >= -0.2 and grade in ("star", "starter", "depth"):
        buy += 1.0                                  # below opportunity -> positive regression
    if fpoe is not None and fpoe >= 3.0 and (td >= 0.38 or fpoe >= 5.0):
        sell += 1.0                                 # ahead of opportunity -> negative regression
    if stage == "aging" and grade in ("star", "starter"):
        sell += 1.0                                 # past the cliff — sell the name
    if stage == "young" and rising and grade in ("starter", "depth"):
        buy += 0.8                                  # ascending role, room to grow
    # NB: deliberately NOT timing the 30-day market trend — per dynasty theory
    # (Harstad) a falling/rising price is neither buy nor sell by itself; the current
    # market_value already prices it in, so the gap above is sufficient.
    # Never sell an elite, non-aging forward asset (a prime star posts a high FPOE by
    # being great — not unsustainable; you hold franchise players).
    if stage != "aging" and pv >= 72:
        sell = 0.0

    labels: list[str] = []
    signal = "HOLD"
    if buy - sell >= 1.0:
        signal = "BUY"; labels.append("Buy-low")
    elif sell - buy >= 1.0:
        signal = "SELL"
        labels.append("Overvalued" if (gap is not None and gap <= -12) else "Sell-high")

    if pr["risk_score"] >= 60 or pr["availability"] < 0.75:
        labels.append("Injury-risk")          # separate durability flag, never a value cut
    if pos in ("WR", "TE") and (pr.get("adot") or 0) >= 11:
        labels.append("Boom-bust")
    elif td and td <= 0.18 and usage >= 0.5:
        labels.append("Volume-anchored")
    return {"archetype": arch, "grade": grade, "stage": stage, "signal": signal,
            "value_gap": round(gap, 1) if gap is not None else 0.0, "dir_labels": labels}


def _attach_team_strength(analysis: dict, profiles: dict) -> None:
    latest = analysis["latest_season"]
    from .store import load_season
    Sd = load_season(latest)
    rp = Sd.league["roster_positions"]
    # value-weighted optimal lineup = forward roster strength (reuse the engine)
    overalls: dict[int, float] = {}
    by_pos_raw: dict[int, dict[str, float]] = {}
    for r in Sd.rosters:
        rid = r["roster_id"]
        vmap = {pid: profiles[pid]["player_value"] for pid in (r.get("players") or [])
                if pid in profiles}
        pos_of = {pid: fantasy_positions(pid) for pid in vmap}
        overalls[rid] = optimal_lineup(vmap, pos_of, rp).total
        bp: dict[str, list] = {}
        for pid, v in vmap.items():
            bp.setdefault(profiles[pid]["pos"], []).append(v)
        by_pos_raw[rid] = {pos: round(sum(sorted(vs, reverse=True)[:_starts(pos)]), 1)
                           for pos, vs in bp.items()}
    overall_list = list(overalls.values())
    pos_lists: dict[str, list] = {}
    for rid, bp in by_pos_raw.items():
        for pos, v in bp.items():
            pos_lists.setdefault(pos, []).append(v)
    for rid, t in analysis["teams"].items():
        srid = t["season_rid"].get(latest, rid)
        if srid not in overalls:
            continue
        members = [p for p in profiles.values() if p["roster_id"] == srid]
        win_now = sum(p["season_value"] for p in
                      sorted(members, key=lambda x: -x["player_value"])[:11])
        future = sum(p["player_value"] for p in members
                     if (p["age"] or 99) <= 25)
        t.setdefault("real", {})
        t["real"]["strength"] = {
            "overall": round(overalls[srid], 1),
            "overall_pctile": round(St.percentile_rank(overall_list, overalls[srid]), 3),
            "by_pos": {pos: {"value": by_pos_raw[srid].get(pos, 0),
                             "pctile": round(St.percentile_rank(
                                 pos_lists.get(pos, [0]), by_pos_raw[srid].get(pos, 0)), 3)}
                       for pos in ("QB", "RB", "WR", "TE")},
            "win_now": round(win_now, 1),
            "future": round(future, 1),
            "durability": round(St.mean([p["availability"] for p in members]), 3) if members else 1.0,
        }
        # overwrite buy/sell with value-model signals (keep fields real_labels reads)
        rp_real = analysis.get("real_players", {})
        buys = sorted([p for p in members if p["signal"] == "BUY"],
                      key=lambda x: -x["value_gap"])
        sells = sorted([p for p in members if p["signal"] == "SELL"],
                       key=lambda x: x["value_gap"])

        def card(p):
            rr = rp_real.get(p["pid"], {}) or {}
            return {"name": p["name"], "pos": p["pos"], "gap": p["value_gap"],
                    "player_value": p["player_value"], "archetype": p["archetype"],
                    "snap_pct": rr.get("snap_pct"), "wopr": rr.get("wopr"),
                    "league_ppg": round((rr.get("league_ppg") or 0), 1),
                    "td_dependence": p.get("td_dependence")}
        t["real"]["buys"] = [card(p) for p in buys[:4]]
        t["real"]["sells"] = [card(p) for p in sells[:4]]
        # value-based team opportunity tilt (so real_labels hoarders/empty use new logic)
        t["real"]["opp_output_gap"] = round(
            St.mean([p["value_gap"] for p in members]) / 100, 3) if members else 0.0


def _historical_profiles(yr: int, Sd, latest_year: int,
                         games_year: dict[int, dict[str, int]]) -> dict[str, dict]:
    """Past-season player profiles computed with the EXACT same pipeline as the
    current season — only the inputs are sliced to that season: that year's real
    football (`_build_pool`), age/experience-at-the-time, and the dynasty MARKET as
    it stood at season's end (DynastyProcess snapshot standing in for FantasyCalc,
    which has no historical API). Value = 0.80·market + 0.20·talent, same grades,
    archetypes, risk and buy/sell signal as enrich()."""
    pool = _build_pool(yr)
    pool_core = [d["core"] for d in pool.values() if d["games"] >= 6]
    market = load_dp_market_season(yr)  # sleeper_id -> SF dynasty value (end of yr)
    pm = players_map()
    rostered = {pid: r["roster_id"] for r in Sd.rosters
                for pid in (r.get("players") or [])}
    rostered_market = [market[pid] for pid in rostered if pid in market]
    avail_years = sorted(games_year)
    profiles: dict[str, dict] = {}
    for pid, rid in rostered.items():
        p = pm.get(pid, {})
        pos = p.get("position") or primary_position(pid)
        age = p.get("age")
        age_at = (age - (latest_year - yr)) if age is not None else None
        yoe = p.get("years_exp")
        yoe_at = max(yoe - (latest_year - yr), 0) if yoe is not None else None
        on_nfl_team = bool(p.get("team"))
        ids = _gsis(pid)
        d = pool.get(ids) if ids else None
        qb_type = "dual" if (d and d.get("rush_att_pg", 0) >= 3.5) else "pocket"
        amult = age_mult(pos, age_at, qb_type)

        # MARKET percentile among that season's rostered players (the anchor).
        mval = market.get(pid)
        market_pctile = St.percentile_rank(rostered_market, mval) * 100 if mval else None
        # MODEL talent (age-neutral) + an age-adjusted dynasty estimate for the signal.
        model_talent = model_dynasty = None
        if d and d["games"] >= 4:
            model_talent = St.percentile_rank(pool_core or [d["core"]], d["core"]) * 100
            model_dynasty = model_talent * amult
        if not d or d["games"] < 8:
            dr = _draft_round(pid)
            if dr and pos in DRAFT_PRIOR:
                prior = min(100, DRAFT_PRIOR[pos].get(dr, 3.0) / 14.0 * 100) * amult
                model_dynasty = prior if model_dynasty is None else 0.5 * model_dynasty + 0.5 * prior
                model_talent = prior if model_talent is None else model_talent

        # SAME value formula as the current season: market dominates, talent nudges.
        if market_pctile is not None and model_talent is not None:
            player_value = 0.80 * market_pctile + 0.20 * model_talent
        elif market_pctile is not None:
            player_value = market_pctile
        elif model_dynasty is not None:
            player_value = model_dynasty
        else:
            player_value = 0.0
        if not on_nfl_team and market_pctile is None:
            player_value = min(player_value, 6.0)

        # availability + risk AS OF that season (games in seasons <= yr)
        gps = [games_year[y][ids] for y in avail_years if y <= yr and ids in games_year.get(y, {})]
        career_gps = St.mean(gps) if gps else 16
        proj_games = 0.55 * career_gps + 0.45 * 16
        availability = St.clamp(proj_games / 17, 0.47, 1.0)
        cliff = CLIFF_AGE.get(f"QB_{qb_type}" if pos == "QB" else pos, 99)
        age_risk = St.clamp(((age_at or 0) - (cliff - 2)) / 6) if age_at else 0
        risk = round(100 * St.clamp(0.55 * (1 - availability) / 0.53 + 0.45 * age_risk), 0)
        profiles[pid] = {
            "pid": pid, "roster_id": rid, "pos": pos, "age": age_at, "years_exp": yoe_at,
            "on_nfl_team": on_nfl_team, "qb_type": qb_type if pos == "QB" else None,
            "player_value": round(player_value, 1),
            "model_value": round(model_dynasty, 1) if model_dynasty is not None else None,
            "model_talent": round(model_talent, 1) if model_talent is not None else None,
            "market_value": round(market_pctile, 1) if market_pctile is not None else None,
            "market_raw": mval, "market_rank": None, "redraft_value": None,
            "rd_delta": None, "trend30": None, "market_tier": None, "pos_rank": None,
            "age_mult": round(amult, 3), "availability": round(availability, 3),
            "risk_score": int(risk), "season_value": round(player_value * availability, 1),
            "xfp_pg": round(d["xfp_pg"], 2) if d else None,
            "fpoe_pg": round(d["fpoe_pg"], 2) if d else None,
            "usage_z": round(d["usage_z"], 2) if d else None,
            "td_dependence": round(d["snaps_td_dep"], 3) if d else None,
            "adot": round(d["adot"], 1) if d else None,
            "games": d["games"] if d else 0,
        }
    pv_all = [pr["player_value"] for pr in profiles.values()]
    model_dyn_vals = [pr["model_value"] for pr in profiles.values() if pr["model_value"] is not None]
    for pr in profiles.values():
        pr["value_pctile"] = round(St.percentile_rank(pv_all, pr["player_value"]), 3)
        pr["model_pctile"] = (round(St.percentile_rank(model_dyn_vals, pr["model_value"]) * 100, 1)
                              if pr["model_value"] is not None else None)
        pr.update(_classify(pr))
    return profiles


def build_season_rosters(analysis: dict) -> None:
    """Per-season roster snapshots for the team page. PAST seasons get the SAME
    value/archetype/risk/signal/usage columns as the current view, computed by the
    SAME pipeline with that season's inputs (that year's real football + the dynasty
    market as it stood at season's end). The latest season already ships via
    players.json, so it is skipped here. Stores full records at
    team['seasons'][s]['roster']."""
    from .store import load_season
    from .real import _season_roster_usage, _season_player_aggregate, snaps
    from .crosswalk import ids_for
    from .metrics_fantasy import league_player_season_ppg
    pm = players_map()
    latest = analysis["latest_season"]
    latest_year = int(latest)

    hist_years = sorted(set(C.NFL_HISTORY_SEASONS) | {int(x) for x in analysis["seasons"]})
    games_year: dict[int, dict[str, int]] = {}
    for y in hist_years:
        try:
            agg = _season_agg(y)
        except Exception:  # noqa: BLE001
            continue
        games_year[y] = {g: int(r["games"] or 0) for g, r in agg.iterrows()}

    for s in analysis["seasons"]:
        if s == latest:
            continue  # current season already ships full records via players.json
        yr = int(s)
        Sd = load_season(s)
        usage = _season_roster_usage(Sd)
        ppg = league_player_season_ppg(Sd)
        try:
            ragg = _season_player_aggregate(yr).set_index("player_id")
        except Exception:  # noqa: BLE001
            ragg = None
        snap_pct: dict[str, float] = {}
        snp = snaps(yr)
        if not snp.empty:
            snap_pct = snp.groupby("pfr_player_id")["offense_pct"].mean().to_dict()
        prof = _historical_profiles(yr, Sd, latest_year, games_year)

        for rid, t in analysis["teams"].items():
            srid = t["season_rid"].get(s)
            if srid is None or s not in t["seasons"]:
                continue
            roster = next((r for r in Sd.rosters if r["roster_id"] == srid), None)
            if not roster:
                continue
            rows = []
            for pid in (roster.get("players") or []):
                p = pm.get(pid, {})
                pos = p.get("position") or primary_position(pid)
                v = prof.get(pid, {})
                prod = ppg.get(pid, {})
                u = usage.get(srid, {}).get(pid, {})
                rec = {
                    "pid": pid,
                    "name": p.get("full_name") or (f"{p.get('team','')} DEF"
                                                   if pos == "DEF" else pid),
                    "pos": pos, "nfl_team": p.get("team"),
                    "age": v.get("age"), "years_exp": v.get("years_exp"),
                    "roster_id": srid,
                    "ppg": round(prod.get("ppg", 0.0), 1),
                    "total": round(prod.get("total", 0.0), 1),
                    "games": prod.get("games", 0),
                    "started": u.get("started", 0),
                    "headshot": C.CDN_PLAYER_HEADSHOT.format(player_id=pid)
                    if pos != "DEF" else None,
                }
                gsis = ids_for(pid).get("gsis_id")
                if ragg is not None and gsis is not None and gsis in ragg.index:
                    r = ragg.loc[gsis]
                    if isinstance(r, pd.DataFrame):
                        r = r.iloc[0]
                    sp = snap_pct.get(ids_for(pid).get("pfr_id"))
                    rec["real"] = {
                        "real_team": r["team"] or p.get("team"),
                        "games_played": int(r["games"] or 0),
                        "snap_pct": round(float(sp) * 100, 1) if sp is not None else None,
                        "target_share": round(float(r["target_share"] or 0), 3) or None,
                        "air_yards_share": round(float(r["air_yards_share"] or 0), 3) or None,
                        "wopr": round(float(r["wopr"] or 0), 3) or None,
                    }
                if v:
                    rec["value"] = {k: v.get(k) for k in (
                        "player_value", "season_value", "model_value", "model_talent",
                        "model_pctile", "market_value", "market_rank", "redraft_value",
                        "rd_delta", "risk_score", "availability", "archetype", "grade",
                        "stage", "signal", "value_gap", "dir_labels", "trend30",
                        "market_tier", "pos_rank", "xfp_pg", "fpoe_pg", "usage_z",
                        "age_mult", "value_pctile")}
                rows.append(rec)
            rows.sort(key=lambda x: (x.get("value") or {}).get("player_value", -1),
                      reverse=True)
            t["seasons"][s]["roster"] = rows


def _starts(pos: str) -> int:
    return {"QB": 2, "RB": 3, "WR": 4, "TE": 1}.get(pos, 1)


@functools.lru_cache(maxsize=4096)
def _gsis(pid: str):
    from .crosswalk import ids_for
    return ids_for(pid).get("gsis_id")


@functools.lru_cache(maxsize=4096)
def _draft_round(pid: str):
    xw = _xw()
    if pid in xw.index:
        v = xw.loc[pid].get("draft_round")
        if pd.notna(v):
            return int(v)
    return None
