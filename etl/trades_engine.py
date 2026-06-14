"""Dynasty-aware trade grading + draft-pick realization.

Runs AFTER the value layer (needs analysis['player_values']). For each trade:
  • realized value  = each received player's production over their tenure on the
    manager's roster (already on the trade record), PLUS
  • remaining DYNASTY value of players a side STILL holds (the future value that
    a kept player carries — the user's requirement), PLUS
  • realized draft picks: a traded pick is linked to the rookie actually drafted
    with it (verified algorithm), valued by that player.
A trade stays PENDING only while it still contains UNrealized (future) picks.
"""
from __future__ import annotations

import functools

from . import statlib as St
from .store import load_season, player_name, players_map, seasons

# Weight of forward dynasty value (0..100/player) relative to one unit of
# realized points-over-replacement, so both axes meaningfully drive the verdict.
DYN_W = 3.0


@functools.lru_cache(maxsize=8)
def _draft_index(season: str):
    """(round, slot:int) -> player_id for a season's rookie draft; None if no draft."""
    if season not in seasons():
        return None
    S = load_season(season)
    if not S.draft or not S.draft.get("slot_to_roster_id"):
        return None
    roster_to_slot = {int(r): int(s) for s, r in S.draft["slot_to_roster_id"].items()}
    by_rs = {}
    for p in S.draft_picks:
        if p.get("player_id"):
            by_rs[(p["round"], int(p["draft_slot"]))] = p["player_id"]
    return {"roster_to_slot": roster_to_slot, "by_rs": by_rs}


def realize_pick(season: str, rnd: int, orig_roster):
    """Return (status, player_id). status: 'realized' | 'future' | 'unknown'."""
    idx = _draft_index(season)
    if idx is None:
        return ("future", None)  # draft hasn't happened (or not in our window)
    slot = idx["roster_to_slot"].get(int(orig_roster)) if orig_roster is not None else None
    if slot is None:
        return ("unknown", None)
    pid = idx["by_rs"].get((rnd, slot))
    return ("realized", pid) if pid else ("unknown", None)


def augment(analysis: dict) -> None:
    pv = analysis.get("player_values", {})
    if not pv:
        return
    latest = analysis["latest_season"]
    owner_of = analysis["owner_of"]
    # receiving owner -> their latest-season roster_id (to test "still held")
    owner_latest_rid = {oid: rid for rid, oid in owner_of[latest].items()}

    def held_value_of(pid: str, owner) -> float:
        v = pv.get(pid)
        if not v:
            return 0.0
        if v.get("roster_id") == owner_latest_rid.get(owner):
            return float(v["player_value"])
        return 0.0

    for s, ps in analysis["per_season"].items():
        for t in ps["trades"]:
            pending = False
            # bucket realized/unrealized picks by receiving roster
            picks_by_rid: dict[int, dict] = {rid: {"realized": [], "future": []}
                                             for rid in t["roster_ids"]}
            for pk in t.get("picks", []):
                to_rid = pk.get("to")
                if to_rid not in picks_by_rid:
                    continue
                status, pid = realize_pick(pk.get("season"), pk.get("round"), pk.get("orig"))
                if status == "future":
                    pending = True
                    picks_by_rid[to_rid]["future"].append(
                        {"season": pk.get("season"), "round": pk.get("round")})
                elif status == "realized" and pid:
                    owner = owner_of[s].get(to_rid)
                    hv = held_value_of(pid, owner)
                    picks_by_rid[to_rid]["realized"].append({
                        "season": pk.get("season"), "round": pk.get("round"),
                        "pid": pid, "name": player_name(pid),
                        "pos": (players_map().get(pid, {}) or {}).get("position"),
                        "value": pv.get(pid, {}).get("player_value"),
                        "held": hv > 0,
                    })
                else:
                    picks_by_rid[to_rid]["future"].append(
                        {"season": pk.get("season"), "round": pk.get("round"), "unknown": True})

            raws: dict[int, float] = {}
            for rid in t["roster_ids"]:
                side = t["sides"][str(rid)]
                owner = owner_of[s].get(rid)
                realized_pts = sum(r.get("tenure_vor", 0) for r in side.get("received", []))
                # remaining dynasty value of still-held received players
                held = sum(held_value_of(r["pid"], owner)
                           for r in side.get("received", []) if r.get("ongoing"))
                # plus realized-pick players still held
                pk_held = sum((a["value"] or 0) for a in picks_by_rid[rid]["realized"] if a["held"])
                side["realized_pts"] = round(realized_pts, 1)
                side["held_value"] = round(held + pk_held, 1)
                side["realized_picks"] = picks_by_rid[rid]["realized"]
                side["future_picks"] = picks_by_rid[rid]["future"]
                raws[rid] = realized_pts + DYN_W * (held + pk_held)

            avg = St.mean(list(raws.values()))
            for rid in t["roster_ids"]:
                t["sides"][str(rid)]["roi"] = round(raws[rid] - avg, 0)
            t["pending"] = pending
            t["graded"] = not pending
