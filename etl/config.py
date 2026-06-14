"""Central configuration + paths for the Sleeper-dashboard ETL.

Everything that varies per-league lives here. Thresholds are intentionally
*percentile-based* (computed at runtime against this league's own distribution)
so the pipeline generalizes across scoring formats (PPR / standard / superflex).
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# League under analysis
# ---------------------------------------------------------------------------
LEAGUE_ID: str = os.environ.get("SLEEPER_LEAGUE_ID", "1237889751156011008")

# How far back to walk previous_league_id. None = all the way to the inaugural.
MAX_SEASONS_BACK: int | None = None

# ---------------------------------------------------------------------------
# Sleeper API
# ---------------------------------------------------------------------------
SLEEPER_BASE = "https://api.sleeper.app/v1"
SLEEPER_STATS_BASE = "https://api.sleeper.com"  # projections live here
# The regular+playoff weeks we probe per season (empty weeks are skipped).
WEEK_RANGE = range(1, 19)
# Politeness: stay well under Sleeper's <1000 req/min limit.
REQUEST_DELAY_S = 0.06
PLAYERS_CACHE_MAX_AGE_H = 24  # /players/nfl is ~15MB; refetch at most daily.

# Sleeper CDN (we ship URLs, never bytes)
CDN_AVATAR = "https://sleepercdn.com/avatars/thumbs/{avatar}"
CDN_PLAYER_HEADSHOT = "https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"
CDN_TEAM_LOGO = "https://sleepercdn.com/images/team_logos/nfl/{team}.png"

# ---------------------------------------------------------------------------
# Real-football (nflverse + DynastyProcess crosswalk)
# ---------------------------------------------------------------------------
NFLVERSE_RELEASES = "https://github.com/nflverse/nflverse-data/releases/download"
CROSSWALK_URL = (
    "https://github.com/dynastyprocess/data/raw/master/files/db_playerids.csv"
)

# ---------------------------------------------------------------------------
# Market values (forward-looking dynasty/redraft) — anchor the player-value model
# ---------------------------------------------------------------------------
FANTASYCALC_URL = "https://api.fantasycalc.com/values/current"
DP_VALUES_PLAYERS_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
)
DP_VALUES_PICKS_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-picks.csv"
)
# Past-season dynasty market snapshots: DynastyProcess values-players.csv pinned to
# the commit just after each season ended (early January). Lets past seasons score
# on the SAME market-dominant axis as the current season. No FantasyCalc historical
# API exists; these are downloaded once into raw/ and the build runs offline.
DP_HISTORICAL_SHAS: dict[int, str] = {
    2024: "2ad1ee905d2db6db6aff8307eb7ebaa457185a68",  # 2025-01-03, end of 2024 season
}
# Market query params (match this league: 0.5 PPR, superflex => 2 QB-eligible slots, 8 teams)
MARKET_PPR = 0.5
MARKET_NUM_QBS = 2     # superflex
MARKET_NUM_TEAMS = 8
MARKET_CACHE_MAX_AGE_H = 24
# Which real-NFL seasons to pull. Defaults to the league's own seasons (filled
# in by build.py from the chain); this is the fallback if run standalone.
DEFAULT_NFL_SEASONS = [2024, 2025]
# Pull several PRIOR years of real-NFL data (stats/snaps/injuries/depth) so career
# availability + injury history are accurate; pbp (team context) stays league-only.
NFL_HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]
PULL_PBP = True  # "Everything + forward-looking": derive team context from pbp.

# ---------------------------------------------------------------------------
# Analysis tunables
# ---------------------------------------------------------------------------
CLOSE_GAME_MARGIN = 5.0          # |margin| <= this == a "close" game
MIN_GAMES_FULL_CONFIDENCE = 14   # confidence ramps to 1.0 around a full season
MIN_GAMES_ANY_CONFIDENCE = 4     # below this, strong labels are suppressed
LABEL_SEVERITY_PCTILE = 0.75     # a label "fires" past this league percentile
# Lineup slot eligibility (fantasy_positions a player must intersect).
FLEX_ELIGIBLE = {"RB", "WR", "TE"}
SUPERFLEX_ELIGIBLE = {"QB", "RB", "WR", "TE"}
IDP_FLEX_ELIGIBLE = {"DL", "LB", "DB"}
REC_FLEX_ELIGIBLE = {"WR", "TE"}
# Positional aging-curve windows (real football). (peak_lo, peak_hi, cliff)
AGE_CURVES = {
    "RB": {"peak": (23, 27), "cliff": 28, "weight": 1.3},
    "WR": {"peak": (24, 29), "cliff": 30, "weight": 1.1},
    "TE": {"peak": (25, 30), "cliff": 31, "weight": 0.9},
    "QB": {"peak": (26, 35), "cliff": 37, "weight": 0.5},
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ETL_DIR = Path(__file__).resolve().parent
ROOT_DIR = ETL_DIR.parent
RAW_DIR = ETL_DIR / "raw"
RAW_SLEEPER = RAW_DIR / "sleeper"
RAW_NFLVERSE = RAW_DIR / "nflverse"
RAW_MARKET = RAW_DIR / "market"
PLAYERS_CACHE = RAW_DIR / "players_nfl.json"
# The web app consumes these (Vite serves /data/* from web/public/data).
DATA_OUT = ROOT_DIR / "web" / "public" / "data"


def ensure_dirs() -> None:
    for d in (RAW_DIR, RAW_SLEEPER, RAW_NFLVERSE, RAW_MARKET, DATA_OUT, DATA_OUT / "teams"):
        d.mkdir(parents=True, exist_ok=True)
