// TypeScript types mirroring the JSON bundles emitted by the Python ETL
// (web/public/data/*.json). Kept in lockstep with etl/build.py.

export type Basis = "fantasy" | "real" | "both";
export type Direction = "good" | "bad" | "neutral";

export interface Record_ { w: number; l: number; t: number }

export interface Archetype {
  key: string;
  name: string;
  blurb: string;
  tone: string; // gold|green|sky|amber|violet|rose|slate
}

export interface Indices { skill: number; luck: number; record: number; trend: number }

export interface Label {
  key: string;
  label: string;
  basis: Basis;
  group: string;
  severity: number;
  confidence: number;
  score: number;
  evidence: string[];
  direction: Direction;
  detail: string;
  projected?: boolean;
}

export interface Recommendation {
  title: string;
  basis: Basis;
  kind: string; // fix|buy|sell|hold|advice
  detail: string;
  severity: number;
  players: { name: string; pos?: string; ppg?: number; owner?: string; note?: string }[];
}

export interface WeeklyGame {
  week: number;
  pts: number;
  opp: number | null;
  opp_pts: number;
  win: boolean | null;
  optimal: number;
  eff: number;
  plob: number;
}

export interface Consistency {
  mean: number; std: number; cv: number; floor: number; ceiling: number;
  high: number; low: number; boom_rate: number; bust_rate: number; skew: number;
}
export interface Efficiency {
  actual: number; optimal: number; plob_total: number; plob_avg: number;
  eff: number; avoidable_losses: number;
}
export interface Luck {
  all_play_w: number; all_play_l: number; all_play_pct: number; xwins: number;
  luck: number; close_w: number; close_l: number; pa_pctile: number;
}
export interface StarPlayer { pid: string; name: string; ppg: number; pos: string }
export interface Construction {
  vor_total: number; top3_share: number; gini: number; stars: StarPlayer[];
}
export interface Management {
  adds: number; waiver_adds: number; fa_adds: number; drops: number;
  faab_used: number; total_moves: number; trades: number; waiver_hits: number;
  waiver_scored: { pid: string; name: string; ppg: number; pos: string }[];
  waiver_hit_rate: number; faab_efficiency: number;
}
export interface DraftPick {
  pick_no: number; round: number; roster_id: number; pid: string; name: string;
  pos: string; actual: number; expected: number; roi: number; ppg: number;
  is_keeper: boolean; team_name?: string;
}
export interface DraftTeam {
  roi: number; hit_rate: number; n_picks: number;
  best: DraftPick[]; worst: DraftPick[]; avg_pos_pick: Record<string, number>;
}
export interface SeasonDetail {
  roster_id: number;
  record: Record_;
  pf: number; pa: number;
  weekly: WeeklyGame[];
  games: number;
  consistency: Consistency;
  efficiency: Efficiency;
  luck: Luck;
  positional: Record<string, number>;
  construction: Construction;
  final_standing: number;
  pf_rank: number;
  champion: boolean;
  runner_up: boolean;
  playoff_finish: number | null;
  made_playoffs: boolean;
  management: Management;
  draft: DraftTeam;
  // regenerated per season (as of that season's end)
  archetype?: Archetype;
  indices?: Indices;
  labels?: Label[];
  recommendations?: Recommendation[];
  strength?: { overall_pctile: number; by_pos: Record<string, { value: number; pctile: number }> };
  roster?: PlayerRow[]; // past-season snapshot (same shape as the players bundle)
  rivalries?: Rivalry[]; // that-season head-to-head
}

export interface PlayoffSos {
  opponents: string[];
  avg_pts_allowed?: number;
  ease_pctile?: number | null;
  difficulty?: number | null;
  projected: boolean;
}
export interface BuySell {
  name: string; pos: string; gap: number; snap_pct?: number; wopr?: number;
  td_dependence?: number; league_ppg: number; player_value?: number; archetype?: string;
}
export interface TeamStrength {
  overall: number;
  overall_pctile: number;
  by_pos: Record<string, { value: number; pctile: number }>;
  win_now: number;
  future: number;
  durability: number;
}
export interface TeamReal {
  available: boolean;
  core_age?: number;
  env_score?: number;
  opp_output_gap?: number;
  adot?: number;
  td_dependence?: number;
  games_missed_avg?: number;
  playoff_sos_pctile?: number | null;
  buys?: BuySell[];
  sells?: BuySell[];
  young_core?: { name: string; pos: string; age: number }[];
  aging?: { name: string; pos: string; age: number }[];
  strength?: TeamStrength;
}

export interface PlayerValue {
  player_value: number;
  season_value: number;
  model_value: number | null;
  model_talent: number | null;
  model_pctile: number | null;
  market_value: number | null;
  redraft_value: number | null;
  rd_delta: number | null;
  risk_score: number;
  availability: number;
  archetype: string;
  grade: string;
  stage: string;
  signal: "BUY" | "SELL" | "HOLD";
  value_gap: number;
  dir_labels: string[];
  trend30: number | null;
  market_tier: number | null;
  pos_rank: number | null;
  xfp_pg: number | null;
  fpoe_pg: number | null;
  usage_z: number | null;
  age_mult: number;
  value_pctile: number;
}

export interface Rivalry {
  opp_roster_id: number; w: number; l: number; t: number;
  pf: number; pa: number; meetings: number;
}

export interface Trajectory {
  pf_rank: number[]; all_play_pct: number[]; finish: (number | null)[];
  season: string[]; pf_rank_slope: number;
}

export interface Team {
  roster_id: number;
  owner_id: string;
  display_name: string;
  team_name: string;
  avatar_url: string | null;
  co_owners: string[];
  season_rid: Record<string, number | null>;
  seasons: Record<string, SeasonDetail>;
  trajectory: Trajectory;
  career: {
    seasons_played: number; championships: number; best_finish: number | null;
    record: Record_; podiums: { season: string; place: number }[];
  };
  strength_trend?: { season: string; pctile: number; value: number }[];
  rivalries: Rivalry[];
  indices: Indices;
  archetype: Archetype;
  real: TeamReal;
  labels: Label[];
  recommendations: Recommendation[];
}

export interface TeamSummary {
  roster_id: number;
  team_name: string;
  display_name: string;
  avatar_url: string | null;
  record: Record_;
  pf: number; pa: number;
  final_standing: number;
  champion: boolean; runner_up: boolean;
  archetype: Archetype;
  indices: Indices;
  strength: number | null;
  strength_pctile: number | null;
  win_now: number | null;
  future: number | null;
  luck: number;
  all_play_pct: number;
  efficiency: number;
  cv: number;
  championships: number;
  career_record: Record_;
  podiums: { season: string; place: number }[];
  top_labels: { label: string; basis: Basis; tone: Direction }[];
}

export interface LeagueBundle {
  league: {
    name: string; season: string;
    roster_positions: string[];
    scoring_settings: Record<string, number>;
    settings: Record<string, number>;
  };
  seasons: string[];
  latest_season: string;
  n_teams: number;
  groups: Record<string, string>;
  teams: TeamSummary[];
  generated_for: string;
}

export interface PlayerRow {
  pid: string; name: string; pos: string; nfl_team: string | null;
  age: number | null; years_exp: number | null; roster_id: number;
  ppg: number; total: number; games: number; headshot: string | null;
  real?: {
    snap_pct?: number; target_share?: number; air_yards_share?: number;
    wopr?: number; adot?: number; carries?: number; targets?: number;
    td_dependence?: number; opp_pctile_nfl?: number;
    games_played?: number; games_missed?: number;
    injury_reports?: number; real_team?: string; playoff_sos?: PlayoffSos;
    projected_flags?: string[]; env_pctile?: number | null;
  };
  value?: PlayerValue;
}
export interface PlayersBundle { season: string; players: PlayerRow[] }

export interface TradeReceived {
  pid: string; name: string; pos: string;
  tenure_points: number; tenure_vor: number; games: number; ongoing: boolean;
}
export interface RealizedPick {
  season: string; round: number; pid: string; name: string;
  pos: string | null; value: number | null; held: boolean;
}
export interface FuturePick { season: string; round: number; unknown?: boolean }
export interface TradeSide {
  received: TradeReceived[];
  roi: number;
  realized_pts?: number;
  held_value?: number;
  realized_picks?: RealizedPick[];
  future_picks?: FuturePick[];
}
export interface Trade {
  season: string; week: number; roster_ids: number[];
  sides: Record<string, TradeSide>;
  n_picks: number;
  picks: { season: string; round: number; from: number; to: number; orig: number }[];
  faab: { amount: number; sender: number; receiver: number }[];
  team_names: Record<string, string>;
  pending: boolean;
  graded?: boolean;
  ongoing: boolean;
}
export interface TradesBundle {
  seasons: Record<string, {
    trades: Trade[];
    activity: { roster_id: number; team_name: string; adds: number;
      faab_used: number; trades: number; waiver_hit_rate: number }[];
  }>;
}

export interface DraftPreviewPick {
  round: number; slot: number; pick_no: number;
  orig_roster: number; orig_team: string;
  owner_roster: number; owner_team: string; traded: boolean;
}
export interface DraftBundle {
  seasons: Record<string, {
    board: DraftPick[];
    per_team: (DraftTeam & { roster_id: number; team_name: string })[];
    expected_curve: number[];
  }>;
  preview?: {
    season: string; rounds: number; order_basis: string;
    board: DraftPreviewPick[];
  } | null;
}

export interface TrendsBundle {
  scoring: { season: string; avg_weekly: number; high: number }[];
  champions: { season: string; champion: string; champion_rid: number; runner_up: string | null }[];
  standings: Record<string, {
    roster_id: number; team_name: string; record: Record_;
    pf: number; pa: number; final_standing: number; champion: boolean;
    all_play_pct: number;
  }[]>;
  rivalry_matrix: Record<string, Record<string, { w: number; l: number; t: number; meetings: number }>>;
  seasons: string[];
  strength_trend: {
    roster_id: number; team_name: string;
    points: { season: string; pctile: number; value: number }[];
  }[];
}
