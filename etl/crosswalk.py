"""Player-id crosswalk (DynastyProcess db_playerids.csv) — bridges Sleeper
player_id to nflverse gsis_id / pfr_id (+ espn fallback).

Verified live: 200/200 rostered players in this league resolve to a gsis_id.
"""
from __future__ import annotations

import functools

import pandas as pd

from . import config as C
from .store import players_map


@functools.lru_cache(maxsize=1)
def _xw() -> pd.DataFrame:
    df = pd.read_csv(C.RAW_NFLVERSE / "db_playerids.csv", low_memory=False)
    df["sleeper_id"] = df["sleeper_id"].astype("Int64").astype(str)
    return df.drop_duplicates("sleeper_id").set_index("sleeper_id")


@functools.lru_cache(maxsize=4096)
def ids_for(sleeper_pid: str) -> dict:
    """Resolve a Sleeper player_id -> {gsis_id, pfr_id, espn_id}. Falls back to
    Sleeper's own espn_id when the crosswalk lacks the row (rare new rookies)."""
    xw = _xw()
    out = {"gsis_id": None, "pfr_id": None, "espn_id": None}
    if sleeper_pid in xw.index:
        row = xw.loc[sleeper_pid]
        for k in ("gsis_id", "pfr_id", "espn_id"):
            v = row.get(k)
            out[k] = None if pd.isna(v) else (str(int(v)) if k == "espn_id" and
                                              isinstance(v, float) else str(v))
    if not out["gsis_id"]:
        # fallback: Sleeper espn_id -> crosswalk row -> gsis_id
        esp = (players_map().get(sleeper_pid) or {}).get("espn_id")
        if esp is not None:
            m = xw[xw["espn_id"] == float(esp)]
            if len(m):
                r = m.iloc[0]
                out["gsis_id"] = None if pd.isna(r["gsis_id"]) else str(r["gsis_id"])
                out["pfr_id"] = None if pd.isna(r["pfr_id"]) else str(r["pfr_id"])
    return out
