"""Download real-NFL data (nflverse releases + DynastyProcess crosswalk) to
etl/raw/nflverse/. Files are cached; re-run is cheap. Parsing happens later in
crosswalk.py / metrics_real.py via pandas.

URLs verified live 2026-06-13. NGS is per-type across all seasons (filtered by
season downstream); stats/snaps/injuries/depth/pbp are per-season.

Run standalone:  python -m etl.fetch_nflverse
"""
from __future__ import annotations

import sys

from . import config as C
from .util import download

B = C.NFLVERSE_RELEASES


def manifest(seasons: list[int], pbp_seasons: list[int] | None = None) -> list[tuple[str, str, str, bool]]:
    """(name, url, filename, required)."""
    items: list[tuple[str, str, str, bool]] = [
        ("crosswalk", C.CROSSWALK_URL, "db_playerids.csv", True),
        ("players", f"{B}/players/players.parquet", "players.parquet", False),
        ("draft_picks", f"{B}/draft_picks/draft_picks.parquet", "draft_picks.parquet", False),
        ("schedules", "https://github.com/nflverse/nfldata/raw/master/data/games.csv", "games.csv", False),
    ]
    for t in ("passing", "receiving", "rushing"):
        items.append((f"ngs_{t}", f"{B}/nextgen_stats/ngs_{t}.parquet", f"ngs_{t}.parquet", False))
    for s in seasons:
        items += [
            (f"stats_{s}", f"{B}/stats_player/stats_player_week_{s}.parquet", f"stats_player_week_{s}.parquet", s == max(seasons)),
            (f"snaps_{s}", f"{B}/snap_counts/snap_counts_{s}.parquet", f"snap_counts_{s}.parquet", False),
            (f"injuries_{s}", f"{B}/injuries/injuries_{s}.parquet", f"injuries_{s}.parquet", False),
            (f"depth_{s}", f"{B}/depth_charts/depth_charts_{s}.parquet", f"depth_charts_{s}.parquet", False),
        ]
        # play-by-play (team context) is heavy — only for the requested pbp seasons.
        if s in (pbp_seasons or []):
            items.append((f"pbp_{s}", f"{B}/pbp/play_by_play_{s}.parquet", f"play_by_play_{s}.parquet", False))
    return items


def main(seasons: list[int] | None = None, force: bool = False,
         pbp_seasons: list[int] | None = None) -> int:
    C.ensure_dirs()
    seasons = seasons or C.NFL_HISTORY_SEASONS
    pbp_seasons = pbp_seasons if pbp_seasons is not None else (
        C.DEFAULT_NFL_SEASONS if C.PULL_PBP else [])
    print(f"[nflverse] downloading real-NFL data for seasons {seasons} (pbp: {pbp_seasons}) …")
    ok, warned, failed = 0, 0, 0
    for name, url, fname, required in manifest(seasons, pbp_seasons):
        dest = C.RAW_NFLVERSE / fname
        try:
            download(url, dest, force=force)
            size_mb = dest.stat().st_size / 1e6
            print(f"  · {name:18s} {size_mb:7.1f} MB  {fname}")
            ok += 1
        except Exception as exc:  # noqa: BLE001 - we classify by required-ness
            if required:
                print(f"  ✗ REQUIRED {name} failed: {exc}", file=sys.stderr)
                failed += 1
            else:
                print(f"  ! optional {name} unavailable ({exc}); continuing", file=sys.stderr)
                warned += 1
    print(f"[nflverse] done: {ok} ok, {warned} optional-missing, {failed} required-failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
