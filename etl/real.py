"""Real-football enrichment layer ("Everything + forward-looking").

Joins each rostered player to nflverse real-NFL data via the crosswalk and
derives:
  • usage / opportunity (snap%, target_share, air_yards, WOPR, carries) -> the
    opportunity-vs-output spine that justifies every buy/sell with a real number
  • age + aging-curve contention window
  • structural volatility (aDOT, TD-dependence)
  • injury / availability history
  • NFL team offensive environment from play-by-play (pace, PROE, EPA)
  • forward playoff strength-of-schedule (2026 wks 15-17) from positional DvP

Offseason-projection signals (team env, forward SoS, depth role) are flagged
`projected: true` so the UI never presents them as fact.
"""
from __future__ import annotations

import functools
import json

import numpy as np
import pandas as pd

from . import config as C
from . import statlib as St
from .crosswalk import ids_for
from .metrics_fantasy import league_player_season_ppg, primary_position
from .store import load_season, players_map, seasons

NFL = C.RAW_NFLVERSE


# ---------------------------------------------------------------------------
# Loaders (cached)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=4)
def weekly_stats(season: int, reg_only: bool = True) -> pd.DataFrame:
    df = pd.read_parquet(NFL / f"stats_player_week_{season}.parquet")
    if reg_only and "season_type" in df:
        df = df[df["season_type"] == "REG"]
    return df


@functools.lru_cache(maxsize=4)
def snaps(season: int) -> pd.DataFrame:
    p = NFL / f"snap_counts_{season}.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if "game_type" in df:
        df = df[df["game_type"] == "REG"]
    return df


@functools.lru_cache(maxsize=4)
def injuries(season: int) -> pd.DataFrame:
    p = NFL / f"injuries_{season}.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@functools.lru_cache(maxsize=1)
def schedule() -> pd.DataFrame:
    return pd.read_csv(NFL / "games.csv", low_memory=False)


# ---------------------------------------------------------------------------
# Team offensive environment from play-by-play (projected for forward outlook)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=2)
def team_context(season: int) -> dict[str, dict]:
    cols = ["posteam", "play_type", "pass", "rush", "epa", "qb_epa", "pass_oe",
            "wp", "week", "season"]
    pbp = pd.read_parquet(NFL / f"play_by_play_{season}.parquet", columns=cols)
    off = pbp[(pbp["posteam"].notna()) &
              (pbp["play_type"].isin(["pass", "run"]))]
    games_per_team = off.groupby("posteam")["week"].nunique()
    ctx = {}
    for team, g in off.groupby("posteam"):
        n_games = max(int(games_per_team.get(team, 1)), 1)
        neutral = g[(g["wp"] >= 0.2) & (g["wp"] <= 0.8)]
        ctx[team] = {
            "plays_per_game": round(len(g) / n_games, 1),
            "proe": round(float(g["pass_oe"].dropna().mean() or 0), 2),
            "epa_play": round(float(g["epa"].dropna().mean() or 0), 4),
            "qb_epa": round(float(g["qb_epa"].dropna().mean() or 0), 4),
            "neutral_pass_rate": round(float(neutral["pass"].dropna().mean() or 0), 3),
        }
    # env_score: z(epa) + z(proe) + z(pace) across teams
    epa = [v["epa_play"] for v in ctx.values()]
    proe = [v["proe"] for v in ctx.values()]
    pace = [v["plays_per_game"] for v in ctx.values()]
    for v in ctx.values():
        v["env_score"] = round((St.zscore(epa, v["epa_play"]) +
                                St.zscore(proe, v["proe"]) +
                                St.zscore(pace, v["plays_per_game"])) / 3, 3)
        v["env_pctile"] = round(St.percentile_rank(epa, v["epa_play"]), 3)
    return ctx


# ---------------------------------------------------------------------------
# Positional defense-vs-position (DvP) and forward playoff SoS
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=2)
def dvp(season: int) -> dict[tuple[str, str], float]:
    """(defense_team, position) -> avg fantasy pts (PPR) allowed per game."""
    df = weekly_stats(season)
    df = df[df["position"].isin(["QB", "RB", "WR", "TE"])]
    grp = df.groupby(["opponent_team", "position"]).agg(
        pts=("fantasy_points_ppr", "sum"),
        games=("week", "nunique")).reset_index()
    out = {}
    for _, r in grp.iterrows():
        out[(r["opponent_team"], r["position"])] = St.safe_div(r["pts"], r["games"])
    return out


def forward_playoff_sos(team: str, pos: str, latest_season: int) -> dict | None:
    """2026 fantasy playoff weeks (15-17): opponents + positional DvP percentile.
    Returns None if the 2026 schedule isn't available."""
    sched = schedule()
    fut = sched[sched["season"] == latest_season + 1]
    if fut.empty or not team:
        return None
    opps = []
    for _, g in fut[(fut["week"].isin([15, 16, 17]))].iterrows():
        if g["home_team"] == team:
            opps.append(g["away_team"])
        elif g["away_team"] == team:
            opps.append(g["home_team"])
    if not opps:
        return None
    d = dvp(latest_season)
    allowed = [d.get((o, pos)) for o in opps if (o, pos) in d]
    if not allowed:
        return {"opponents": opps, "difficulty": None, "projected": True}
    league_vals = [v for (k, p), v in
                   [((k[0], k[1]), v) for k, v in d.items()] if p == pos]
    avg = St.mean(allowed)
    return {
        "opponents": opps,
        "avg_pts_allowed": round(avg, 1),
        # higher pts allowed by opponents == easier == better for the player
        "ease_pctile": round(St.percentile_rank(league_vals, avg), 3),
        "projected": True,
    }


# ---------------------------------------------------------------------------
# Per-player real profile
# ---------------------------------------------------------------------------
def _season_player_aggregate(season: int) -> pd.DataFrame:
    df = weekly_stats(season)
    agg = df.groupby("player_id").agg(
        games=("week", "nunique"),
        position=("position", "first"),
        team=("team", lambda s: s.value_counts().index[0] if len(s) else None),
        carries=("carries", "sum"),
        targets=("targets", "sum"),
        receptions=("receptions", "sum"),
        rec_air_yards=("receiving_air_yards", "sum"),
        pass_attempts=("attempts", "sum"),
        rush_yards=("rushing_yards", "sum"),
        rec_yards=("receiving_yards", "sum"),
        pass_yards=("passing_yards", "sum"),
        rush_tds=("rushing_tds", "sum"),
        rec_tds=("receiving_tds", "sum"),
        pass_tds=("passing_tds", "sum"),
        fpts=("fantasy_points_ppr", "sum"),
        wopr=("wopr", "mean"),
        target_share=("target_share", "mean"),
        air_yards_share=("air_yards_share", "mean"),
    ).reset_index()
    return agg


def _usage_raw(row) -> float:
    pos = row["position"]
    if pos == "QB":
        return float(row["pass_attempts"] or 0) + 1.5 * float(row["carries"] or 0)
    if pos == "RB":
        return float(row["carries"] or 0) + 0.75 * float(row["targets"] or 0)
    return float(row["targets"] or 0) + 0.10 * float(row["rec_air_yards"] or 0)


def build_player_profiles(latest_season: int, league_ppg: dict[str, dict],
                          rostered: dict[str, int]) -> dict[str, dict]:
    """rostered: sleeper_pid -> roster_id. Returns sleeper_pid -> real profile."""
    agg = _season_player_aggregate(latest_season).set_index("player_id")
    snp = snaps(latest_season)
    snap_pct = {}
    if not snp.empty:
        sp = snp.groupby("pfr_player_id")["offense_pct"].mean()
        snap_pct = sp.to_dict()
    ctx = team_context(latest_season)
    pm = players_map()

    # NFL position pools for usage z / opportunity percentile (>=6 games)
    pool_usage: dict[str, list[float]] = {}
    for gsis, r in agg.iterrows():
        if (r["games"] or 0) >= 6 and r["position"] in ("QB", "RB", "WR", "TE"):
            pool_usage.setdefault(r["position"], []).append(_usage_raw(r))

    profiles: dict[str, dict] = {}
    for pid, rid in rostered.items():
        p = pm.get(pid, {})
        pos = p.get("position") or primary_position(pid)
        ids = ids_for(pid)
        gsis = ids.get("gsis_id")
        prof = {
            "pid": pid, "roster_id": rid,
            "name": p.get("full_name") or pid,
            "pos": pos,
            "nfl_team": p.get("team"),
            "age": p.get("age"), "years_exp": p.get("years_exp"),
            "depth_chart_order": p.get("depth_chart_order"),  # projected
            "league_ppg": round(league_ppg.get(pid, {}).get("ppg", 0), 1),
            "league_total": round(league_ppg.get(pid, {}).get("total", 0), 1),
            "has_real": False, "projected_flags": [],
        }
        if pos == "DEF" or gsis is None or gsis not in agg.index:
            profiles[pid] = prof
            continue
        r = agg.loc[gsis]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        games = int(r["games"] or 0)
        total_tds = (r["rush_tds"] or 0) + (r["rec_tds"] or 0) + (r["pass_tds"] or 0)
        td_pts = total_tds * (4 if pos == "QB" else 6)
        team = r["team"] or p.get("team")
        sp = snap_pct.get(ids.get("pfr_id"))
        usage = _usage_raw(r)
        opp_pctile_nfl = St.percentile_rank(pool_usage.get(pos, [usage]), usage)
        prof.update({
            "has_real": games > 0,
            "real_team": team,
            "games_played": games,
            "snap_pct": round(float(sp) * 100, 1) if sp is not None else None,
            "target_share": round(float(r["target_share"] or 0), 3),
            "air_yards_share": round(float(r["air_yards_share"] or 0), 3),
            "wopr": round(float(r["wopr"] or 0), 3),
            "carries": int(r["carries"] or 0),
            "targets": int(r["targets"] or 0),
            "adot": round(St.safe_div(float(r["rec_air_yards"] or 0),
                                      float(r["targets"] or 0)), 1),
            "real_fpts": round(float(r["fpts"] or 0), 1),
            "td_dependence": round(St.safe_div(td_pts, float(r["fpts"] or 1)), 3),
            "opp_pctile_nfl": round(opp_pctile_nfl, 3),  # real role strength vs NFL
            "team_env": ctx.get(team, {}),
        })
        # forward playoff SoS (projected) using the player's CURRENT team
        sos = forward_playoff_sos(p.get("team"), pos if pos in ("QB", "RB", "WR", "TE")
                                  else "WR", latest_season)
        if sos:
            prof["playoff_sos"] = sos
            prof["projected_flags"].append("playoff_sos")
        if prof.get("team_env"):
            prof["projected_flags"].append("team_env")
        if prof.get("depth_chart_order") is not None:
            prof["projected_flags"].append("depth_role")
        profiles[pid] = prof

    # injury / availability history across all loaded seasons
    _attach_injuries(profiles, latest_season)
    # opportunity-vs-output gap, computed within rostered players at each position
    _attach_opp_output_gap(profiles)
    return profiles


def _attach_injuries(profiles: dict[str, dict], latest_season: int) -> None:
    inj_counts: dict[str, int] = {}
    for s in sorted(set(C.NFL_HISTORY_SEASONS) | {int(x) for x in seasons()}):
        idf = injuries(s)
        if idf.empty:
            continue
        out = idf[idf["report_status"].isin(["Out", "Doubtful", "IR"])]
        c = out.groupby("gsis_id")["week"].nunique()
        for g, n in c.items():
            inj_counts[g] = inj_counts.get(g, 0) + int(n)
    team_games = 17
    for prof in profiles.values():
        gsis = ids_for(prof["pid"]).get("gsis_id")
        prof["injury_reports"] = inj_counts.get(gsis, 0)
        if prof.get("has_real"):
            prof["games_missed"] = max(team_games - prof.get("games_played", 0), 0)


def _attach_opp_output_gap(profiles: dict[str, dict]) -> None:
    by_pos: dict[str, list[dict]] = {}
    for prof in profiles.values():
        if prof.get("has_real") and prof.get("games_played", 0) >= 4:
            by_pos.setdefault(prof["pos"], []).append(prof)
    for pos, plist in by_pos.items():
        usage = [p["opp_pctile_nfl"] for p in plist]
        output = [p["league_ppg"] for p in plist]
        for p in plist:
            opp = St.percentile_rank(usage, p["opp_pctile_nfl"])
            out = St.percentile_rank(output, p["league_ppg"])
            gap = round(opp - out, 3)
            p["opp_output_gap"] = gap  # + = usage exceeds output (BUY)
            # Gate: only flag genuine roles (real usage) / genuine producers.
            real_role = p.get("opp_pctile_nfl", 0) >= 0.45
            real_producer = p["league_ppg"] >= 8.0
            if gap >= 0.25 and real_role:
                p["signal"] = "BUY"
            elif gap <= -0.25 and real_producer:
                p["signal"] = "SELL"
            else:
                p["signal"] = "HOLD"


# ---------------------------------------------------------------------------
# Team-level real aggregation + labels
# ---------------------------------------------------------------------------
def _team_real(rid: int, profiles: dict[str, dict]) -> dict:
    members = [p for p in profiles.values() if p["roster_id"] == rid and p.get("has_real")]
    if not members:
        return {"available": False}
    # weight by league fantasy contribution, with positional aging weights
    def w(p):
        base = max(p["league_total"], 0.1)
        return base * C.AGE_CURVES.get(p["pos"], {}).get("weight", 1.0)
    tw = sum(w(p) for p in members) or 1.0
    core_age = sum((p.get("age") or 26) * w(p) for p in members) / tw
    env = sum((p.get("team_env", {}).get("env_score", 0)) * w(p) for p in members) / tw
    gap = sum((p.get("opp_output_gap", 0)) * w(p) for p in members) / tw
    adot = St.mean([p["adot"] for p in members if p.get("adot")])
    td_dep = sum((p.get("td_dependence", 0)) * w(p) for p in members) / tw
    games_missed = sum((p.get("games_missed", 0)) * w(p) for p in members) / tw
    buys = sorted([p for p in members if p.get("signal") == "BUY"],
                  key=lambda x: x["opp_output_gap"], reverse=True)
    sells = sorted([p for p in members if p.get("signal") == "SELL"],
                   key=lambda x: x["opp_output_gap"])
    sos_vals = [p["playoff_sos"]["ease_pctile"] for p in members
                if p.get("playoff_sos", {}).get("ease_pctile") is not None]
    young = [p for p in members if (p.get("age") or 30) <= 24 and p["league_total"] > 30]
    old = [p for p in members
           if (p.get("age") or 0) >= C.AGE_CURVES.get(p["pos"], {}).get("cliff", 99)
           and p["league_total"] > 50]
    return {
        "available": True,
        "core_age": round(core_age, 1),
        "env_score": round(env, 3),
        "opp_output_gap": round(gap, 3),
        "adot": round(adot, 1),
        "td_dependence": round(td_dep, 3),
        "games_missed_avg": round(games_missed, 1),
        "playoff_sos_pctile": round(St.mean(sos_vals), 3) if sos_vals else None,
        "buys": [{"name": p["name"], "pos": p["pos"], "gap": p["opp_output_gap"],
                  "snap_pct": p.get("snap_pct"), "wopr": p.get("wopr"),
                  "league_ppg": p["league_ppg"]} for p in buys[:4]],
        "sells": [{"name": p["name"], "pos": p["pos"], "gap": p["opp_output_gap"],
                   "td_dependence": p.get("td_dependence"),
                   "league_ppg": p["league_ppg"]} for p in sells[:4]],
        "young_core": [{"name": p["name"], "pos": p["pos"], "age": p["age"]}
                       for p in sorted(young, key=lambda x: -x["league_total"])[:4]],
        "aging": [{"name": p["name"], "pos": p["pos"], "age": p["age"]}
                  for p in sorted(old, key=lambda x: -x["league_total"])[:4]],
    }


def enrich(analysis: dict) -> dict:
    latest = int(analysis["latest_season"])
    Sd = load_season(str(latest))
    league_ppg = league_player_season_ppg(Sd)
    rostered = {pid: r["roster_id"] for r in Sd.rosters
                for pid in (r.get("players") or [])}
    profiles = build_player_profiles(latest, league_ppg, rostered)

    # league context for percentile-based real labels
    team_reals = {}
    for rid in analysis["teams"]:
        tr = _team_real(rid, profiles)
        analysis["teams"][rid]["real"] = tr
        team_reals[rid] = tr
    analysis["real_players"] = profiles
    return {"profiles": profiles, "team_reals": team_reals, "latest": latest,
            "ctx_arrays": _real_arrays(team_reals)}


def _real_arrays(team_reals: dict) -> dict:
    vals = [t for t in team_reals.values() if t.get("available")]
    return {
        "core_age": [t["core_age"] for t in vals],
        "env_score": [t["env_score"] for t in vals],
        "gap": [t["opp_output_gap"] for t in vals],
        "td_dep": [t["td_dependence"] for t in vals],
        "games_missed": [t["games_missed_avg"] for t in vals],
        "sos": [t["playoff_sos_pctile"] for t in vals
                if t.get("playoff_sos_pctile") is not None],
    }


# ---------------------------------------------------------------------------
# Real labels + recommendation merge
# ---------------------------------------------------------------------------
def _lab(key, label, basis, severity, conf, evidence, direction, detail, projected=False):
    return {"key": key, "label": label, "basis": basis, "group": "real",
            "severity": round(St.clamp(severity), 3), "confidence": conf,
            "score": round(St.clamp(severity) * conf, 4), "evidence": evidence,
            "direction": direction, "detail": detail, "projected": projected}


def real_labels(rid: int, analysis: dict, real_data: dict) -> list[dict]:
    tr = real_data["team_reals"].get(rid, {})
    if not tr.get("available"):
        return []
    arr = real_data["ctx_arrays"]
    conf = 0.75  # real usage over a full season is solid; projected ones lower
    out = []
    pr = St.percentile_rank

    # Youth vs aging window
    age_pr = pr(arr["core_age"], tr["core_age"])
    if age_pr <= 0.3 and tr["young_core"]:
        names = ", ".join(f"{p['name']} ({p['age']})" for p in tr["young_core"][:3])
        out.append(_lab("youth", "Youth Movement", "both", 1 - age_pr, conf,
                        [f"core age {tr['core_age']} (youngest tier)", names],
                        "good", "A young, ascending core — dynasty arrow up."))
    elif age_pr >= 0.7 and tr["aging"]:
        names = ", ".join(f"{p['name']} ({p['age']})" for p in tr["aging"][:3])
        out.append(_lab("aging", "Win-Now Window", "both", age_pr, conf,
                        [f"core age {tr['core_age']} (oldest tier)", names],
                        "neutral", "Veteran core — the contention window is now."))

    # Opportunity-vs-output team tilt (BUY / SELL spine)
    gap_pr = pr(arr["gap"], tr["opp_output_gap"])
    if tr["buys"] and tr["opp_output_gap"] >= 0.1:
        b = tr["buys"][0]
        out.append(_lab("hoarders", "Opportunity Hoarders", "real",
                        gap_pr, conf,
                        [f"{b['name']}: {int((b.get('snap_pct') or 0))}% snaps / "
                         f"{b['wopr']:.2f} WOPR but only {b['league_ppg']} PPG"],
                        "good", "Real usage outruns fantasy output — positive "
                        "regression / buy-low candidates on the roster."))
    if tr["sells"] and tr["opp_output_gap"] <= -0.1:
        s = tr["sells"][0]
        out.append(_lab("empty_prod", "Empty Production", "real",
                        1 - gap_pr, conf,
                        [f"{s['name']}: {s['league_ppg']} PPG on thin usage, "
                         f"{s['td_dependence']:.0%} TD-dependent"],
                        "bad", "Points built on unsustainable usage/TDs — sell-high "
                        "candidates."))

    # Volatility by design (real)
    td_pr = pr(arr["td_dep"], tr["td_dependence"])
    if td_pr >= 0.7 or tr["adot"] >= 11:
        out.append(_lab("volatility_real", "Volatility by Design", "real",
                        max(td_pr, St.clamp((tr["adot"] - 8) / 6)), conf,
                        [f"{tr['td_dependence']:.0%} of points from TDs",
                         f"team aDOT {tr['adot']:.1f} (boom-bust)"],
                        "neutral", "Structurally boom-bust: deep targets + TD-reliant."))
    elif td_pr <= 0.3 and tr["adot"] <= 8:
        out.append(_lab("volume_real", "Built on Volume", "real",
                        1 - td_pr, conf,
                        [f"low TD-dependence ({tr['td_dependence']:.0%})",
                         f"short-area volume (aDOT {tr['adot']:.1f})"],
                        "good", "A stable, high-floor usage profile."))

    # Offensive environment
    env_pr = pr(arr["env_score"], tr["env_score"])
    if env_pr >= 0.7:
        out.append(_lab("elite_offense", "Plugged Into Elite Offenses", "real",
                        env_pr, 0.6,
                        [f"roster-weighted offense env {tr['env_score']:+.2f} (top tier)"],
                        "good", "Players sit in high-pace, efficient NFL offenses.",
                        projected=True))
    elif env_pr <= 0.3:
        out.append(_lab("bad_offense", "Stuck in Bad Situations", "real",
                        1 - env_pr, 0.6,
                        [f"roster-weighted offense env {tr['env_score']:+.2f} (bottom tier)"],
                        "bad", "Talent capped by weak NFL offensive environments.",
                        projected=True))

    # Injury risk
    if arr["games_missed"]:
        gm_pr = pr(arr["games_missed"], tr["games_missed_avg"])
        if gm_pr >= 0.7:
            out.append(_lab("fragile", "Injury-Prone Core", "real", gm_pr, 0.7,
                            [f"avg {tr['games_missed_avg']:.1f} games missed by "
                             f"contributors"], "bad",
                            "Availability risk across key pieces."))

    # Forward playoff SoS (projected)
    if tr.get("playoff_sos_pctile") is not None and arr["sos"]:
        sos_pr = pr(arr["sos"], tr["playoff_sos_pctile"])
        if sos_pr >= 0.7:
            out.append(_lab("easy_playoffs", "Playoff-Schedule Winner", "real",
                            sos_pr, 0.5,
                            [f"favorable wk15-17 2026 matchups (ease "
                             f"{tr['playoff_sos_pctile']:.0%})"], "good",
                            "Rostered players draw soft fantasy-playoff defenses.",
                            projected=True))
        elif sos_pr <= 0.3:
            out.append(_lab("hard_playoffs", "Brutal Playoff Stretch", "real",
                            1 - sos_pr, 0.5,
                            [f"tough wk15-17 2026 matchups (ease "
                             f"{tr['playoff_sos_pctile']:.0%})"], "bad",
                            "Rostered players face hard fantasy-playoff defenses.",
                            projected=True))

    # Scheme-change wildcards (curated, optional)
    out += _scheme_labels(rid, analysis)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


@functools.lru_cache(maxsize=1)
def _manual_signals() -> dict:
    p = C.ETL_DIR / "manual_signals.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _scheme_labels(rid: int, analysis: dict) -> list[dict]:
    sig = _manual_signals()
    changes = {c["team"]: c for c in sig.get("scheme_changes", [])}
    if not changes:
        return []
    profiles = analysis.get("real_players", {})
    affected = []
    for p in profiles.values():
        if p["roster_id"] == rid and p.get("nfl_team") in changes and p["league_total"] > 40:
            affected.append((p["name"], changes[p["nfl_team"]]))
    if not affected:
        return []
    ev = [f"{n}: {c['note']}" for n, c in affected[:3]]
    return [_lab("scheme_wildcard", "Scheme-Change Wildcards", "real",
                 St.clamp(len(affected) / 3), 0.4, ev, "neutral",
                 "Key players face new coaching/scheme in 2026.", projected=True)]


def _season_roster_usage(Sd) -> dict[int, dict[str, dict]]:
    """roster_id -> pid -> {'started': weeks-started, 'rostered_weeks'} across the
    full season (reg + playoffs). How often the manager actually played each piece."""
    out: dict[int, dict[str, dict]] = {}
    for _wk, rows in Sd.matchups.items():
        for r in rows:
            d = out.setdefault(r["roster_id"], {})
            starters = set(r.get("starters") or [])
            for pid in (r.get("players_points") or {}):
                e = d.setdefault(pid, {"started": 0, "rostered_weeks": 0})
                e["rostered_weeks"] += 1
                if pid in starters:
                    e["started"] += 1
    return out


def merge_recs(rid: int, analysis: dict, real_data: dict, recs: list[dict]) -> list[dict]:
    tr = real_data["team_reals"].get(rid, {})
    if not tr.get("available"):
        return recs
    extra = []
    if tr["buys"]:
        b = tr["buys"][0]
        extra.append({
            "title": "Hold / acquire your buy-low assets", "basis": "real",
            "kind": "buy", "severity": St.clamp(tr["opp_output_gap"] + 0.3),
            "detail": f"{b['name']} ({b['pos']}) is earning a strong real role "
                      f"({int(b.get('snap_pct') or 0)}% snaps, {b['wopr']:.2f} WOPR) but "
                      f"only scoring {b['league_ppg']} PPG — usage that good tends to pay "
                      f"off. Hold, or buy similar profiles cheap.",
            "players": [{"name": p["name"], "pos": p["pos"], "note": "buy-low (high usage)"}
                        for p in tr["buys"][:3]],
        })
    if tr["sells"]:
        s = tr["sells"][0]
        extra.append({
            "title": "Sell-high before the production craters", "basis": "real",
            "kind": "sell", "severity": St.clamp(-tr["opp_output_gap"] + 0.3),
            "detail": f"{s['name']} ({s['pos']}) is scoring {s['league_ppg']} PPG on thin "
                      f"real usage ({s['td_dependence']:.0%} TD-dependent). Cash in while "
                      f"the name value is high.",
            "players": [{"name": p["name"], "pos": p["pos"], "note": "sell-high (low usage)"}
                        for p in tr["sells"][:3]],
        })
    if tr.get("aging") and tr.get("young_core") == []:
        extra.append({
            "title": "Win now — your window is open", "basis": "real", "kind": "advice",
            "severity": 0.6,
            "detail": f"Core age {tr['core_age']} is among the oldest in the league. "
                      f"Trade future picks for immediate help; don't let the window close.",
            "players": [{"name": p["name"], "pos": p["pos"], "note": f"age {p['age']}"}
                        for p in tr["aging"][:3]],
        })
    merged = recs + extra
    merged.sort(key=lambda r: r.get("severity", 0), reverse=True)
    return merged[:6]
