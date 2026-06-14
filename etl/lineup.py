"""Exact optimal-lineup engine — the crux of the fantasy analysis.

Given a week's per-player points and each player's eligible positions, fill the
league's starting slots to MAXIMIZE total points, honoring FLEX / SUPER_FLEX
eligibility. Uses exact max-weight bipartite matching (scipy linear_sum_assignment),
not greedy, so superflex edge cases (a 2nd QB belongs in SUPER_FLEX) are correct.

Powers: points-left-on-bench, lineup efficiency, avoidable losses, and several
recommendations. Validated against Sleeper's own pre-computed `ppts` in tests.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

# Slot -> the set of fantasy_positions a player must intersect to be eligible.
SLOT_ELIGIBILITY: dict[str, set[str]] = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "K": {"K"},
    "DEF": {"DEF"},
    "DL": {"DL"}, "LB": {"LB"}, "DB": {"DB"},
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "IDP_FLEX": {"DL", "LB", "DB"},
}
# Roster slots that are NOT started.
BENCH_SLOTS = {"BN", "IR", "TAXI", "NA"}

_BIG = 1e7  # penalty for assigning a player to an ineligible slot


def starting_slots(roster_positions: list[str]) -> list[str]:
    return [s for s in roster_positions if s not in BENCH_SLOTS]


def _eligible(slot: str, pos: set[str]) -> bool:
    allowed = SLOT_ELIGIBILITY.get(slot)
    if allowed is None:  # unknown slot -> treat as flex of its own name
        return slot in pos
    return bool(pos & allowed)


@dataclass
class LineupResult:
    total: float                       # optimal starter points
    assignment: list[tuple[str, str, float]]  # (slot, pid, pts)
    used: set[str]                     # pids in the optimal lineup


def optimal_lineup(
    player_points: dict[str, float],
    pos_of: dict[str, set[str]],
    roster_positions: list[str],
) -> LineupResult:
    """Best legal lineup. `pos_of` maps pid -> eligible fantasy positions."""
    slots = starting_slots(roster_positions)
    pids = [p for p in player_points.keys()]
    if not slots:
        return LineupResult(0.0, [], set())
    if not pids:
        return LineupResult(0.0, [(s, "", 0.0) for s in slots], set())

    n_p, n_s = len(pids), len(slots)
    # Cost matrix (we minimize): -points if eligible, +BIG if not.
    cost = np.full((n_p, n_s), _BIG, dtype=float)
    for i, pid in enumerate(pids):
        pts = float(player_points.get(pid) or 0.0)
        pos = pos_of.get(pid, set())
        for j, slot in enumerate(slots):
            if _eligible(slot, pos):
                cost[i, j] = -pts
    rows, cols = linear_sum_assignment(cost)

    assignment: list[tuple[str, str, float]] = [("", "", 0.0)] * n_s
    used: set[str] = set()
    total = 0.0
    for r, c in zip(rows, cols):
        slot = slots[c]
        if cost[r, c] >= _BIG:  # forced ineligible -> slot effectively empty
            assignment[c] = (slot, "", 0.0)
            continue
        pid = pids[r]
        pts = float(player_points.get(pid) or 0.0)
        assignment[c] = (slot, pid, pts)
        used.add(pid)
        total += pts
    # any column not returned (n_p < n_s) stays empty
    for j, slot in enumerate(slots):
        if assignment[j] == ("", "", 0.0):
            assignment[j] = (slot, "", 0.0)
    return LineupResult(round(total, 2), assignment, used)


@dataclass
class WeekEfficiency:
    actual: float       # points the manager actually started
    optimal: float      # best legal lineup
    left_on_bench: float
    efficiency: float   # actual / optimal (1.0 == perfect)
    optimal_assignment: list[tuple[str, str, float]]


def matchup_efficiency(
    starters_points: list[float],
    players_points: dict[str, float],
    pos_of: dict[str, set[str]],
    roster_positions: list[str],
    *,
    actual_points: float | None = None,
) -> WeekEfficiency:
    """Compare the started lineup to the optimal one for a single team-week."""
    actual = float(actual_points) if actual_points is not None else round(
        sum(float(x or 0) for x in (starters_points or [])), 2)
    opt = optimal_lineup(players_points, pos_of, roster_positions)
    left = round(opt.total - actual, 2)
    eff = (actual / opt.total) if opt.total > 0 else 1.0
    return WeekEfficiency(actual, opt.total, max(left, 0.0), round(eff, 4),
                          opt.assignment)
