"""Pull forward-looking MARKET values that anchor the player-value model:
  - FantasyCalc superflex dynasty + redraft values (joins on Sleeper player_id)
  - DynastyProcess player values (ECR cross-check) + draft-pick values

These price in real talent, age, injury, and outlook — the crowd's forward view.
Cached daily; non-fatal on failure (we degrade loudly, never silently).

Run standalone:  python -m etl.fetch_market
"""
from __future__ import annotations

import sys
import time

from . import config as C
from .util import download, get_json, save_json


def fetch_fantasycalc(force: bool = False) -> list | None:
    dest = C.RAW_MARKET / "fantasycalc_sf_dynasty.json"
    if dest.exists() and not force:
        age_h = (time.time() - dest.stat().st_mtime) / 3600
        if age_h < C.MARKET_CACHE_MAX_AGE_H:
            from .util import load_json
            return load_json(dest)
    params = {"isDynasty": "true", "numQbs": C.MARKET_NUM_QBS,
              "ppr": C.MARKET_PPR, "numTeams": C.MARKET_NUM_TEAMS}
    data = get_json(C.FANTASYCALC_URL, params=params)
    if data:
        save_json(data, dest)
    return data


def fetch_dp_historical(seasons: list[int], force: bool = False) -> None:
    """Past-season dynasty market: FantasyCalc has no historical API, so we pin the
    DynastyProcess values-players.csv as it stood just after each season ended
    (early January) to a specific commit and download that snapshot once into raw/.
    This is the '<year> version' of the same dynasty-market data that anchors the
    current-season value, so past seasons score on the same axis (market-dominant)
    instead of a model-only proxy. No live API resolution — the SHA is pinned for
    reproducibility, and a cached copy means the build never calls out."""
    for y in seasons:
        sha = C.DP_HISTORICAL_SHAS.get(y)
        dest = C.RAW_MARKET / f"dp_values_players_{y}.csv"
        if (dest.exists() and not force) or not sha:
            if not sha and not dest.exists():
                print(f"  ! DP {y} market: no pinned commit — past-season value "
                      f"will fall back to model-only", file=sys.stderr)
            continue
        try:
            url = (f"https://raw.githubusercontent.com/dynastyprocess/data/{sha}"
                   f"/files/values-players.csv")
            download(url, dest, force=True)
            print(f"  · DynastyProcess {y} market: {dest.name} (@{sha[:8]})")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! DP {y} market failed: {exc}", file=sys.stderr)


def main(force: bool = False, hist_seasons: list[int] | None = None) -> int:
    C.ensure_dirs()
    print("[market] FantasyCalc superflex dynasty values …")
    ok = 0
    try:
        fc = fetch_fantasycalc(force=force)
        if fc:
            n_ids = sum(1 for r in fc if (r.get("player") or {}).get("sleeperId"))
            print(f"  · FantasyCalc: {len(fc)} players ({n_ids} with sleeperId)")
            ok += 1
        else:
            print("  ! FantasyCalc returned no data", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! FantasyCalc fetch failed: {exc}", file=sys.stderr)

    for name, url, fname in (
        ("DynastyProcess players", C.DP_VALUES_PLAYERS_URL, "dp_values_players.csv"),
        ("DynastyProcess picks", C.DP_VALUES_PICKS_URL, "dp_values_picks.csv"),
    ):
        try:
            download(url, C.RAW_MARKET / fname, force=force)
            print(f"  · {name}: {fname}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {name} failed: {exc}", file=sys.stderr)

    if hist_seasons:
        print("[market] DynastyProcess historical (past-season) markets …")
        fetch_dp_historical(hist_seasons, force=force)
    print(f"[market] done: {ok}/3 current sources cached")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--force" in sys.argv))
