"""End-to-end sanity checks: identity/standings integrity, score reconciliation
against Sleeper, crosswalk coverage, and emitted-bundle schema."""
from __future__ import annotations

import json

import pytest

from etl import config as C
from etl.analyze import assemble
from etl.crosswalk import ids_for
from etl.store import load_season, players_map, seasons

_RAW = (C.RAW_SLEEPER / "chain.json").exists()
pytestmark = pytest.mark.skipif(not _RAW, reason="raw Sleeper data not fetched")


@pytest.fixture(scope="module")
def analysis():
    return assemble()


def test_records_balance(analysis):
    for s in analysis["seasons"]:
        ms = analysis["per_season"][s]["metrics"]
        w = sum(t["record"]["w"] for t in ms.values())
        l = sum(t["record"]["l"] for t in ms.values())
        assert w == l, f"{s}: {w} wins != {l} losses"


def test_pf_reconciles_with_sleeper(analysis):
    """Regular-season points-for recomputed from matchups must match Sleeper's fpts."""
    for s in analysis["seasons"]:
        S = load_season(s)
        ms = analysis["per_season"][s]["metrics"]
        for r in S.rosters:
            fpts = r["settings"].get("fpts", 0) + r["settings"].get("fpts_decimal", 0) / 100
            mine = ms[r["roster_id"]]["pf"]
            assert abs(mine - fpts) <= 1.5, f"{s} r{r['roster_id']}: {mine} vs {fpts}"


def test_champion_matches_bracket(analysis):
    for s in analysis["seasons"]:
        S = load_season(s)
        champ_match = next((m for m in S.winners_bracket if m.get("p") == 1), None)
        if champ_match:
            assert analysis["per_season"][s]["champion"] == champ_match["w"]


def test_crosswalk_coverage():
    """Rostered non-DEF players should overwhelmingly resolve to a gsis_id."""
    S = load_season(seasons()[-1])
    pm = players_map()
    rostered = {pid for r in S.rosters for pid in (r.get("players") or [])}
    skill = [pid for pid in rostered if (pm.get(pid) or {}).get("position") != "DEF"]
    resolved = sum(1 for pid in skill if ids_for(pid).get("gsis_id"))
    assert resolved / len(skill) >= 0.95, f"only {resolved}/{len(skill)} resolved"


def test_every_team_has_analysis(analysis):
    for rid, t in analysis["teams"].items():
        assert t["team_name"]
        assert t["seasons"], f"team {rid} has no season detail"
        assert "trajectory" in t and "rivalries" in t


@pytest.mark.skipif(not (C.DATA_OUT / "league.json").exists(),
                    reason="bundles not built yet (run etl.build)")
def test_emitted_bundles_schema():
    league = json.loads((C.DATA_OUT / "league.json").read_text())
    assert league["teams"] and len(league["teams"]) == league["n_teams"]
    for summ in league["teams"]:
        assert {"roster_id", "team_name", "archetype", "record"} <= summ.keys()
    for summ in league["teams"]:
        tb = json.loads((C.DATA_OUT / "teams" / f"{summ['roster_id']}.json").read_text())
        assert tb["labels"] and tb["recommendations"] is not None
        assert "archetype" in tb
    for name in ("players", "trades", "draft", "trends"):
        assert (C.DATA_OUT / f"{name}.json").exists()


@pytest.mark.skipif(not (C.DATA_OUT / "players.json").exists(),
                    reason="bundles not built yet (run etl.build)")
def test_player_value_is_independent_of_fantasy_points():
    """PLAYER value must come from real football + market, NOT realized fantasy
    points: a low-PPG (hurt/underused) player can still be high value, and
    durability is a SEPARATE field (never folded into value)."""
    players = json.loads((C.DATA_OUT / "players.json").read_text())["players"]
    valued = [p for p in players if p.get("value")]
    assert valued, "no player has a value block"
    # availability + risk are separate fields; season_value = value × availability ≤ value
    for p in valued:
        v = p["value"]
        assert "availability" in v and "risk_score" in v
        assert v["season_value"] <= v["player_value"] + 0.1
    # a player with low last-year PPG but high dynasty value MUST exist
    low_ppg_high_value = [p for p in valued if p["ppg"] < 10 and p["value"]["player_value"] >= 65]
    assert low_ppg_high_value, "value looks coupled to fantasy points (injury bug)"
    # value must not be a perfect function of ppg (low rank correlation sanity)
    pairs = [(p["ppg"], p["value"]["player_value"]) for p in valued if p["ppg"] > 0]
    hi_ppg_low_val = [p for p in valued if p["ppg"] >= 12 and p["value"]["player_value"] < 50]
    assert pairs and hi_ppg_low_val  # some good scorers are low dynasty value (e.g., old)
