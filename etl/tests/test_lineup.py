"""Tests for the optimal-lineup engine (the analysis crux).

Includes hand-computed cases that distinguish exact matching from naive greedy,
plus an integration cross-check against Sleeper's own pre-computed `ppts`.
"""
from __future__ import annotations

import pytest

from etl import config as C
from etl import store
from etl.lineup import SLOT_ELIGIBILITY, matchup_efficiency, optimal_lineup


def test_superflex_second_qb_goes_to_superflex():
    pts = {"qb1": 30, "qb2": 25, "rb1": 20, "rb2": 10, "wr1": 15, "wr2": 5}
    pos = {"qb1": {"QB"}, "qb2": {"QB"}, "rb1": {"RB"}, "rb2": {"RB"},
           "wr1": {"WR"}, "wr2": {"WR"}}
    rp = ["QB", "RB", "WR", "FLEX", "SUPER_FLEX", "BN", "BN"]
    res = optimal_lineup(pts, pos, rp)
    # QB1+RB1+WR1 + FLEX(rb2=10) + SF(qb2=25) = 100
    assert res.total == pytest.approx(100.0)
    sf = next(pid for slot, pid, _ in res.assignment if slot == "SUPER_FLEX")
    assert sf == "qb2"  # second QB belongs in the superflex


def test_exact_matching_beats_greedy_ordering():
    # Greedy that fills SUPER_FLEX first would burn the only QB there and leave
    # the QB slot empty (total 55). Exact matching keeps QB in QB (total 75).
    pts = {"qb1": 30, "rb1": 25, "rb2": 20}
    pos = {"qb1": {"QB"}, "rb1": {"RB"}, "rb2": {"RB"}}
    rp = ["SUPER_FLEX", "QB", "RB"]
    res = optimal_lineup(pts, pos, rp)
    assert res.total == pytest.approx(75.0)
    qb_slot = next(pid for slot, pid, _ in res.assignment if slot == "QB")
    assert qb_slot == "qb1"


def test_position_eligibility_enforced():
    # A WR cannot fill a QB slot; with no QB available the QB slot is empty.
    pts = {"wr1": 20, "wr2": 18}
    pos = {"wr1": {"WR"}, "wr2": {"WR"}}
    rp = ["QB", "WR", "BN"]
    res = optimal_lineup(pts, pos, rp)
    qb = next(pid for slot, pid, _ in res.assignment if slot == "QB")
    assert qb == ""               # unfilled
    assert res.total == pytest.approx(20.0)  # only the WR slot scores


def test_efficiency_and_points_left_on_bench():
    pts = {"a": 20, "b": 10, "c": 5}
    pos = {"a": {"RB"}, "b": {"RB"}, "c": {"RB"}}
    rp = ["RB", "FLEX", "BN"]
    # Manager started a(20) + c(5) = 25; optimal a(20)+b(10) = 30.
    eff = matchup_efficiency([20, 5], pts, pos, rp)
    assert eff.optimal == pytest.approx(30.0)
    assert eff.actual == pytest.approx(25.0)
    assert eff.left_on_bench == pytest.approx(5.0)
    assert eff.efficiency == pytest.approx(25 / 30, abs=1e-4)


# --------------------------------------------------------------------------
# Integration: validate against the live league's cached data + Sleeper ppts.
# --------------------------------------------------------------------------
_RAW_PRESENT = (C.RAW_SLEEPER / "chain.json").exists()
pytestmark_int = pytest.mark.skipif(not _RAW_PRESENT, reason="raw Sleeper data not fetched")


def _pos_of(pids):
    return {p: store.fantasy_positions(p) for p in pids}


@pytestmark_int
def test_all_optimal_lineups_are_legal():
    violations = 0
    for season in store.seasons():
        S = store.load_season(season)
        rp = S.league["roster_positions"]
        for rows in S.matchups.values():
            for row in rows:
                pp = row.get("players_points") or {}
                res = optimal_lineup(pp, _pos_of(pp.keys()), rp)
                used = [pid for _, pid, _ in res.assignment if pid]
                assert len(used) == len(set(used)), f"dup in {season} {row['roster_id']}"
                for slot, pid, _ in res.assignment:
                    if pid:
                        allowed = SLOT_ELIGIBILITY.get(slot, {slot})
                        assert store.fantasy_positions(pid) & allowed
    assert violations == 0


@pytestmark_int
def test_optimal_matches_sleeper_ppts():
    """opt over regular weeks must NEVER undershoot Sleeper's ppts (would mean a
    bug), and should match to the penny for the vast majority of roster-seasons
    (Sleeper's ppts is occasionally a hair suboptimal on superflex)."""
    exact = total = 0
    for season in store.seasons():
        S = store.load_season(season)
        rp = S.league["roster_positions"]
        opt_reg: dict[int, float] = {}
        for wk in S.regular_weeks:
            for row in S.matchups[wk]:
                pp = row.get("players_points") or {}
                opt_reg[row["roster_id"]] = opt_reg.get(row["roster_id"], 0.0) + \
                    optimal_lineup(pp, _pos_of(pp.keys()), rp).total
        for r in S.rosters:
            s = r["settings"]
            ppts = s.get("ppts", 0) + s.get("ppts_decimal", 0) / 100
            mine = round(opt_reg.get(r["roster_id"], 0.0), 2)
            total += 1
            assert mine >= ppts - 0.05, f"{season} r{r['roster_id']}: {mine} < ppts {ppts}"
            if abs(mine - ppts) <= 0.05:
                exact += 1
    assert exact / total >= 0.85, f"only {exact}/{total} matched Sleeper ppts exactly"
