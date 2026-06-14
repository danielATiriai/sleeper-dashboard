"""Composite Power Archetype — one headline banner per team on a Luck × Skill ×
Trend grid. Skill and luck are z-scored within the league; an age/window hook
(set later by the real-football layer) nudges win-now vs rebuild.
"""
from __future__ import annotations

from . import statlib as St


def _z(arr, x):
    return St.zscore(arr, x)


def compute_archetypes(analysis: dict, season: str | None = None) -> None:
    """Annotate each team's SEASON detail with archetype + skill/luck indices,
    computed as of the end of that season. Mirrors the latest season to the
    team's top-level fields (used by summaries/overview/power rankings)."""
    season = season or analysis["latest_season"]
    latest = analysis["latest_season"]
    teams = analysis["teams"]
    rows = [(rid, t["seasons"][season]) for rid, t in teams.items()
            if season in t["seasons"]]

    ap = [d["luck"]["all_play_pct"] for _, d in rows]
    pf = [d["pf"] for _, d in rows]
    eff = [d["efficiency"]["eff"] for _, d in rows]
    luck = [d["luck"]["luck"] for _, d in rows]
    winpct = [(d["record"]["w"] + 0.5 * d["record"]["t"]) / max(d["games"], 1)
              for _, d in rows]
    cv_list = [d["consistency"]["cv"] for _, d in rows]
    cv_thresh = St.percentile(cv_list, 0.66) if cv_list else 0

    for rid, d in rows:
        t = teams[rid]
        skill = round((_z(ap, d["luck"]["all_play_pct"]) + _z(pf, d["pf"]) +
                       _z(eff, d["efficiency"]["eff"])) / 3, 3)
        luck_z = round(_z(luck, d["luck"]["luck"]), 3)
        wp = (d["record"]["w"] + 0.5 * d["record"]["t"]) / max(d["games"], 1)
        rec_z = round(_z(winpct, wp), 3)
        # trend = finish improvement THROUGH this season
        traj = t["trajectory"]
        fin = [traj["finish"][i] for i, sy in enumerate(traj["season"]) if sy <= season]
        trend = (fin[0] - fin[-1]) if len(fin) >= 2 and None not in fin else 0
        cv_high = d["consistency"]["cv"] >= cv_thresh

        idx = {"skill": skill, "luck": luck_z, "record": rec_z, "trend": trend}
        arch = _classify(d, skill, luck_z, rec_z, trend, cv_high, t)
        d["indices"] = idx
        d["archetype"] = arch
        if season == latest:
            t["indices"] = idx
            t["archetype"] = arch


def _classify(d, skill, luck_z, rec_z, trend, cv_high, team) -> dict:
    champ = d.get("champion")
    runner = d.get("runner_up")

    def arch(key, name, blurb, tone):
        return {"key": key, "name": name, "blurb": blurb, "tone": tone}

    rec = f"{d['record']['w']}-{d['record']['l']}"
    # Champions first (with character)
    if champ and skill < 0.2:
        return arch("cinderella", "Cinderella Champion",
                    f"Won it all at {rec} — rode a hot bracket and good fortune "
                    f"(luck {d['luck']['luck']:+.1f}). A title is a title.", "gold")
    if champ:
        return arch("true_champion", "True Champion",
                    f"Earned the {team['trajectory']['season'][-1]} crown with a "
                    f"top-tier roster (skill {skill:+.2f}).", "gold")

    if skill >= 0.6 and rec_z >= 0.4 and abs(luck_z) < 0.8:
        return arch("contender", "True Contender",
                    f"Elite by every measure — strong scores ({rec}) with little "
                    f"luck involved.", "green")
    if rec_z >= 0.5 and skill < 0.2:
        return arch("pretender", "Paper Tiger",
                    f"Record ({rec}) outruns the underlying scoring — luck "
                    f"{d['luck']['luck']:+.1f}. Regression looms.", "amber")
    if skill >= 0.4 and rec_z <= -0.3:
        return arch("sleeping_giant", "Sleeping Giant",
                    f"Scores like a contender but the record ({rec}) doesn't show "
                    f"it — {d['luck']['luck']:+.1f} wins of bad luck.", "sky")
    if runner:
        return arch("so_close", "Heartbreak Finalist",
                    f"One win from the title at {rec}. The window is open.", "violet")
    if cv_high and d["consistency"]["boom_rate"] >= 0.2 and abs(rec_z) < 0.6:
        return arch("wildcard", "The Wildcard",
                    f"Volatile and dangerous — a high ceiling ({d['consistency']['ceiling']:.0f}) "
                    f"that can beat anyone on its day.", "violet")
    if skill <= -0.4 and rec_z <= -0.4:
        if trend > 0:
            return arch("rebuild", "The Rebuild",
                        f"Bottom of the table ({rec}) but trending up — building "
                        f"toward something.", "sky")
        return arch("bottom_feeder", "Honest Bottom-Feeder",
                    f"The scores match the record ({rec}). Work to do.", "rose")
    if not cv_high and abs(rec_z) < 0.5:
        return arch("middling", "Mr. Consistent Middling",
                    f"Steady and mid ({rec}) — reliable, rarely scary.", "slate")
    return arch("balanced_mid", "Solid Middle-Tier",
                f"A competitive, well-rounded squad ({rec}).", "slate")
