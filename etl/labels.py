"""Fantasy label/archetype emission.

Each label is graded against the LEAGUE's own distribution (percentile-based, so
it generalizes across formats) and carries:
  severity   0..1  how extreme vs the league
  confidence 0..1  scales with games/seasons (strong claims suppressed on small n)
  basis      fantasy | real | both
  evidence[] concrete numbers behind the call
"""
from __future__ import annotations

from . import config as C
from . import statlib as St

GROUPS = {
    "shape": "Scoring shape",
    "skill": "Manager skill",
    "luck": "Luck vs skill",
    "build": "Roster construction",
    "mgmt": "In-season management",
    "draft": "Draft",
    "trend": "Trajectory",
    "rivalry": "Rivalry",
    "real": "Real football",
}


def confidence(games: int, seasons: int = 1) -> float:
    g = St.clamp((games - C.MIN_GAMES_ANY_CONFIDENCE) /
                 (C.MIN_GAMES_FULL_CONFIDENCE - C.MIN_GAMES_ANY_CONFIDENCE))
    s = St.clamp(0.6 + 0.2 * (seasons - 1))  # 1 season -> 0.6, 3+ -> 1.0
    return round(St.clamp(0.4 + 0.6 * g) * s, 3)


def _arr(teams: dict, season: str, path: list[str]) -> list[float]:
    vals = []
    for t in teams.values():
        d = t["seasons"].get(season)
        if not d:
            continue
        cur = d
        for k in path:
            cur = cur.get(k, {}) if isinstance(cur, dict) else {}
        if isinstance(cur, (int, float)):
            vals.append(cur)
    return vals


def build_context(analysis: dict, season: str | None = None) -> dict:
    season = season or analysis["latest_season"]
    teams = analysis["teams"]
    ctx = {
        "season": season,
        "cv": _arr(teams, season, ["consistency", "cv"]),
        "floor": _arr(teams, season, ["consistency", "floor"]),
        "ceiling": _arr(teams, season, ["consistency", "ceiling"]),
        "boom": _arr(teams, season, ["consistency", "boom_rate"]),
        "plob": _arr(teams, season, ["efficiency", "plob_avg"]),
        "eff": _arr(teams, season, ["efficiency", "eff"]),
        "luck": _arr(teams, season, ["luck", "luck"]),
        "pa": _arr(teams, season, ["pa"]),
        "pf": _arr(teams, season, ["pf"]),
        "gini": _arr(teams, season, ["construction", "gini"]),
        "adds": _arr(teams, season, ["management", "adds"]),
        "hit": _arr(teams, season, ["management", "waiver_hit_rate"]),
    }
    # positional production arrays
    pos_arr: dict[str, list[float]] = {}
    for t in teams.values():
        d = t["seasons"].get(season, {})
        for pos, v in (d.get("positional") or {}).items():
            pos_arr.setdefault(pos, []).append(v)
    ctx["positional"] = pos_arr
    # draft acumen = total draft value-over-expected through this season
    draft_roi = {rid: round(sum(sd.get("draft", {}).get("roi", 0)
                                for s2, sd in t["seasons"].items() if s2 <= season), 1)
                 for rid, t in teams.items()}
    ctx["draft_roi"] = draft_roi
    ctx["draft_roi_arr"] = list(draft_roi.values())
    return ctx


def _lab(key, label, basis, group, severity, conf, evidence, direction, detail=""):
    return {
        "key": key, "label": label, "basis": basis, "group": group,
        "severity": round(St.clamp(severity), 3), "confidence": conf,
        "score": round(St.clamp(severity) * conf, 4),
        "evidence": evidence, "direction": direction, "detail": detail,
    }


def label_team(rid: int, analysis: dict, ctx: dict) -> list[dict]:
    season = ctx["season"]
    team = analysis["teams"][rid]
    d = team["seasons"].get(season)
    if not d:
        return []
    games = d.get("games", 0)
    conf = confidence(games, 1)
    out: list[dict] = []
    pr = St.percentile_rank

    cons, eff, luck = d["consistency"], d["efficiency"], d["luck"]

    # ---- Scoring shape ----
    cv_pr = pr(ctx["cv"], cons["cv"])
    if cv_pr <= 0.34:
        out.append(_lab("metronome", "The Metronome", "fantasy", "shape",
                        1 - cv_pr, conf,
                        [f"CV {cons['cv']:.3f} (lowest tier)",
                         f"weekly {cons['mean']:.0f}±{cons['std']:.0f}"],
                        "good", "Remarkably consistent week to week."))
    elif cv_pr >= 0.66:
        out.append(_lab("rollercoaster", "The Rollercoaster", "fantasy", "shape",
                        cv_pr, conf,
                        [f"CV {cons['cv']:.3f} (highest tier)",
                         f"range {cons['low']:.0f}–{cons['high']:.0f}"],
                        "neutral", "Boom-or-bust week to week."))
    if pr(ctx["floor"], cons["floor"]) >= 0.7:
        out.append(_lab("high_floor", "High Floor", "fantasy", "shape",
                        pr(ctx["floor"], cons["floor"]), conf,
                        [f"floor (P10) {cons['floor']:.0f}",
                         f"bust rate {cons['bust_rate']:.0%}"], "good",
                        "Rarely posts a dud."))
    if pr(ctx["ceiling"], cons["ceiling"]) >= 0.7 or cons["boom_rate"] >= 0.3:
        out.append(_lab("ceiling", "Ceiling Merchant", "fantasy", "shape",
                        max(pr(ctx["ceiling"], cons["ceiling"]),
                            pr(ctx["boom"], cons["boom_rate"])), conf,
                        [f"ceiling (P90) {cons['ceiling']:.0f}",
                         f"boom weeks {cons['boom_rate']:.0%}"], "good",
                        "Massive upside when it hits."))

    # ---- Manager skill ----
    plob_pr = pr(ctx["plob"], eff["plob_avg"])
    if plob_pr >= 0.6:
        out.append(_lab("bench_bleeder", "Bench-Points Bleeder", "fantasy", "skill",
                        plob_pr, conf,
                        [f"{eff['plob_avg']:.1f} pts/wk left on bench",
                         f"{eff['plob_total']:.0f} total; lineup eff {eff['eff']:.0%}"],
                        "bad", "Leaves startable points on the bench."))
    elif pr(ctx["eff"], eff["eff"]) >= 0.66:
        out.append(_lab("surgeon", "Lineup Surgeon", "fantasy", "skill",
                        pr(ctx["eff"], eff["eff"]), conf,
                        [f"lineup efficiency {eff['eff']:.1%}",
                         f"only {eff['plob_avg']:.1f} pts/wk left on bench"],
                        "good", "Sets near-optimal lineups."))
    if eff["avoidable_losses"] >= 2:
        out.append(_lab("costly", "Costly Mistakes", "fantasy", "skill",
                        St.clamp(eff["avoidable_losses"] / 4), conf,
                        [f"{eff['avoidable_losses']} losses winnable with the "
                         f"optimal lineup"], "bad",
                        "Lineup errors flipped real games."))

    # ---- Luck vs skill ----
    if luck["luck"] >= 1.0:
        out.append(_lab("lucky", "Fortune's Favorite", "fantasy", "luck",
                        St.clamp(luck["luck"] / 3), conf,
                        [f"{luck['luck']:+.1f} wins above expected",
                         f"all-play {luck['all_play_pct']:.0%} vs "
                         f"{d['record']['w']}-{d['record']['l']} record"],
                        "neutral", "Winning more than the scores justify."))
    elif luck["luck"] <= -1.0:
        out.append(_lab("snakebitten", "Snakebitten", "fantasy", "luck",
                        St.clamp(-luck["luck"] / 3), conf,
                        [f"{luck['luck']:+.1f} wins below expected",
                         f"all-play {luck['all_play_pct']:.0%} but only "
                         f"{d['record']['w']}-{d['record']['l']}"],
                        "neutral", "Better than the record — positive regression coming."))
    pa_pr = luck["pa_pctile"]
    if pa_pr >= 0.75:
        out.append(_lab("sufferer", "Schedule Sufferer", "fantasy", "luck",
                        pa_pr, conf, [f"faced {d['pa']:.0f} PA (toughest slate)"],
                        "neutral", "Drew the league's hardest schedule."))
    elif pa_pr <= 0.25:
        out.append(_lab("cupcake", "Cupcake Schedule", "fantasy", "luck",
                        1 - pa_pr, conf, [f"faced just {d['pa']:.0f} PA (easiest slate)"],
                        "neutral", "Got the league's softest schedule."))
    if luck["close_l"] >= 3 and luck["close_l"] > luck["close_w"]:
        out.append(_lab("heartbreak", "Heartbreak Kid", "fantasy", "luck",
                        St.clamp(luck["close_l"] / 5), conf,
                        [f"{luck['close_w']}-{luck['close_l']} in games within "
                         f"{C.CLOSE_GAME_MARGIN:.0f} pts"], "neutral",
                        "Keeps losing the nail-biters."))
    elif luck["close_w"] >= 3 and luck["close_w"] > luck["close_l"]:
        out.append(_lab("closer", "The Closer", "fantasy", "luck",
                        St.clamp(luck["close_w"] / 5), conf,
                        [f"{luck['close_w']}-{luck['close_l']} in one-score games"],
                        "good", "Wins the close ones."))
    standing = d.get("final_standing")
    if standing and d.get("pf_rank") and standing - d["pf_rank"] >= 2:
        out.append(_lab("stat_padder", "Stat-Padder", "fantasy", "luck",
                        St.clamp((standing - d["pf_rank"]) / 4), conf,
                        [f"#{d['pf_rank']} in points but finished #{standing}"],
                        "bad", "Scores don't convert to wins."))

    # ---- Roster construction ----
    gini_pr = pr(ctx["gini"], d["construction"]["gini"])
    if gini_pr >= 0.7:
        stars = ", ".join(s["name"] for s in d["construction"]["stars"][:2])
        out.append(_lab("stars_scrubs", "Stars & Scrubs", "fantasy", "build",
                        gini_pr, conf,
                        [f"top-3 hold {d['construction']['top3_share']:.0%} of roster value",
                         f"carried by {stars}"], "neutral",
                        "Top-heavy: a few elites, thin after."))
    elif gini_pr <= 0.3:
        out.append(_lab("balanced", "Balanced Build", "fantasy", "build",
                        1 - gini_pr, conf,
                        [f"even value spread (Gini {d['construction']['gini']:.2f})"],
                        "good", "Depth over top-end."))
    # positional strength/weakness — from DYNASTY VALUE (real football, that
    # season), NOT realized fantasy production (which can contradict the roster).
    strength = (d.get("strength") or {})
    for pos, sp in (strength.get("by_pos") or {}).items():
        pp = sp.get("pctile")
        if pp is None:
            continue
        if pp >= 0.80:
            out.append(_lab(f"strong_{pos}", f"Loaded at {pos}", "both", "build",
                            pp, conf,
                            [f"{pos} dynasty value in the top {pp * 100:.0f}% of the league"],
                            "good", f"Real top-end talent + depth at {pos}."))
        elif pp <= 0.20:
            out.append(_lab(f"thin_{pos}", f"Thin at {pos}", "both", "build",
                            1 - pp, conf,
                            [f"{pos} dynasty value in the bottom {pp * 100:.0f}% of the league"],
                            "bad", f"A real roster need at {pos} to address."))

    # ---- Management ----
    mg = d["management"]
    adds_pr = pr(ctx["adds"], mg["adds"])
    if adds_pr >= 0.7 and mg["waiver_hit_rate"] >= 0.15:
        hits = ", ".join(x["name"] for x in mg["waiver_scored"][:2])
        out.append(_lab("waiver_shark", "Waiver Shark", "fantasy", "mgmt",
                        adds_pr, conf,
                        [f"{mg['adds']} pickups, {mg['waiver_hit_rate']:.0%} hit rate"]
                        + ([f"found {hits}"] if hits else []), "good",
                        "Works the wire and finds contributors."))
    elif adds_pr <= 0.25:
        out.append(_lab("waiver_ghost", "Waiver Ghost", "fantasy", "mgmt",
                        1 - adds_pr, conf,
                        [f"only {mg['adds']} pickups all year"], "bad",
                        "Disengaged from the waiver wire."))

    # ---- Draft acumen (manager; fed by realized draft outcomes) ----
    dr = ctx["draft_roi"].get(rid, 0)
    dr_pr = pr(ctx["draft_roi_arr"], dr)
    n_picks = sum(d2.get("draft", {}).get("n_picks", 0)
                  for s2, d2 in team["seasons"].items() if s2 <= season)
    dconf = confidence(min(n_picks, C.MIN_GAMES_FULL_CONFIDENCE), len(team["seasons"]))
    if dr_pr >= 0.75 and dr > 0:
        out.append(_lab("draft_wizard", "Draft Wizard", "fantasy", "draft", dr_pr, dconf,
                        [f"+{dr:.0f} draft value over expectation ({n_picks} picks)"],
                        "good", "Consistently drafts above slot — picks that beat expectation."))
    elif dr_pr <= 0.25 and dr < 0:
        out.append(_lab("draft_liability", "Draft Liability", "fantasy", "draft",
                        1 - dr_pr, dconf,
                        [f"{dr:.0f} draft value vs expectation ({n_picks} picks)"],
                        "bad", "Draft picks underperform their slot."))

    # ---- Trajectory (multi-season, THROUGH this season) ----
    traj = team["trajectory"]
    idxs = [i for i, sy in enumerate(traj["season"]) if sy <= season]
    fin = [traj["finish"][i] for i in idxs]
    seas = [traj["season"][i] for i in idxs]
    if len(fin) >= 2 and None not in fin:
        delta = fin[0] - fin[-1]  # improved finish = positive
        sconf = confidence(games, len(fin))
        if delta >= 2:
            out.append(_lab("rising", "On the Rise", "fantasy", "trend",
                            St.clamp(delta / 4), sconf,
                            [f"finish {fin[0]}→{fin[-1]} ({'→'.join(seas)})"], "good",
                            "Climbing the standings year over year."))
        elif delta <= -2:
            out.append(_lab("declining", "In Decline", "fantasy", "trend",
                            St.clamp(-delta / 4), sconf,
                            [f"finish {fin[0]}→{fin[-1]}"],
                            "bad", "Sliding down the standings."))
    # within-season heating/fading
    weekly = [w["pts"] for w in d["weekly"]]
    slope = St.ols_slope(weekly)
    if abs(slope) >= 1.5 and len(weekly) >= 8:
        if slope > 0:
            out.append(_lab("heating", "Heating Up", "fantasy", "trend",
                            St.clamp(slope / 4), conf,
                            [f"+{slope:.1f} pts/wk trend over the season"], "good",
                            "Peaking at the right time."))
        else:
            out.append(_lab("fading", "Fading Down the Stretch", "fantasy", "trend",
                            St.clamp(-slope / 4), conf,
                            [f"{slope:.1f} pts/wk trend over the season"], "bad",
                            "Cooling off late."))

    # ---- Rivalry ----
    for r in team["rivalries"]:
        if r["meetings"] >= 4 and r["w"] + r["l"] > 0:
            wpct = r["w"] / (r["w"] + r["l"])
            opp = analysis["teams"].get(r["opp_roster_id"], {}).get("team_name", "?")
            if wpct <= 0.25:
                out.append(_lab(f"nemesis_{r['opp_roster_id']}", f"Owned by {opp}",
                                "fantasy", "rivalry", 1 - wpct,
                                confidence(r["meetings"] * 3, 2),
                                [f"{r['w']}-{r['l']} vs {opp} all-time"], "bad",
                                "A genuine nemesis."))
            elif wpct >= 0.75:
                out.append(_lab(f"owns_{r['opp_roster_id']}", f"Owns {opp}",
                                "fantasy", "rivalry", wpct,
                                confidence(r["meetings"] * 3, 2),
                                [f"{r['w']}-{r['l']} vs {opp} all-time"], "good",
                                "Has this matchup's number."))

    if d.get("champion"):
        out.append(_lab("champion", "Reigning Champion", "fantasy", "trend", 1.0, conf,
                        [f"won the {season} title"], "good", "Banner hangs forever."))
    elif d.get("runner_up"):
        out.append(_lab("runner_up", "So Close", "fantasy", "trend", 0.7, conf,
                        [f"lost the {season} championship game"], "neutral",
                        "One game from the title."))

    out.sort(key=lambda x: x["score"], reverse=True)
    return out
