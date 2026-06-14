// Formatting + the shared color language for tones, basis tags, archetypes, and
// NFL positions. Tailwind classes are referenced statically so they survive purge.
import type { Basis, Direction, PlayerRow } from "../types";

export const fmt = (n: number | null | undefined, d = 1): string =>
  n === null || n === undefined || Number.isNaN(n) ? "—" : n.toFixed(d);

export const fmt0 = (n: number | null | undefined): string => fmt(n, 0);

export const signed = (n: number | null | undefined, d = 1): string =>
  n === null || n === undefined ? "—" : (n >= 0 ? "+" : "") + n.toFixed(d);

export const pct = (n: number | null | undefined, d = 0): string =>
  n === null || n === undefined ? "—" : (n * 100).toFixed(d) + "%";

export const ordinal = (n: number | null | undefined): string => {
  if (n === null || n === undefined) return "—";
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

export const recordStr = (r?: { w: number; l: number; t: number }): string =>
  r ? `${r.w}-${r.l}${r.t ? "-" + r.t : ""}` : "—";

// Direction (good/bad/neutral) -> text + dot colors
export const TONE: Record<Direction, { text: string; dot: string; ring: string }> = {
  good: { text: "text-gridiron", dot: "bg-gridiron", ring: "ring-gridiron/40" },
  bad: { text: "text-rose", dot: "bg-rose", ring: "ring-rose/40" },
  neutral: { text: "text-sky", dot: "bg-sky", ring: "ring-sky/40" },
};

// Basis tag (fantasy / real / both)
export const BASIS: Record<Basis, { label: string; cls: string; icon: string }> = {
  fantasy: { label: "Fantasy", cls: "bg-sky/15 text-sky border-sky/30", icon: "🏈" },
  real: { label: "Real NFL", cls: "bg-gridiron/15 text-gridiron border-gridiron/30", icon: "📡" },
  both: { label: "Both", cls: "bg-violet/15 text-violet border-violet/30", icon: "⚡" },
};

// Archetype tone -> banner gradient-free accent classes
export const ARCH_TONE: Record<string, { bg: string; text: string; border: string; bar: string }> = {
  gold: { bg: "bg-amber/10", text: "text-amber", border: "border-amber/40", bar: "bg-amber" },
  green: { bg: "bg-gridiron/10", text: "text-gridiron", border: "border-gridiron/40", bar: "bg-gridiron" },
  sky: { bg: "bg-sky/10", text: "text-sky", border: "border-sky/40", bar: "bg-sky" },
  amber: { bg: "bg-amber/10", text: "text-amber", border: "border-amber/40", bar: "bg-amber" },
  violet: { bg: "bg-violet/10", text: "text-violet", border: "border-violet/40", bar: "bg-violet" },
  rose: { bg: "bg-rose/10", text: "text-rose", border: "border-rose/40", bar: "bg-rose" },
  slate: { bg: "bg-ink-700/30", text: "text-chalk-dim", border: "border-ink-600", bar: "bg-chalk-faint" },
};

export const POS_COLOR: Record<string, string> = {
  QB: "text-posQB", RB: "text-posRB", WR: "text-posWR", TE: "text-posTE",
  K: "text-chalk-dim", DEF: "text-posDEF",
};
export const POS_BG: Record<string, string> = {
  QB: "bg-posQB/15 text-posQB", RB: "bg-posRB/15 text-posRB",
  WR: "bg-posWR/15 text-posWR", TE: "bg-posTE/15 text-posTE",
  K: "bg-ink-700 text-chalk-dim", DEF: "bg-posDEF/15 text-posDEF",
};

// value GRADE -> color; aging archetypes shade amber (declining dynasty arrow)
export const GRADE_TONE: Record<string, string> = {
  star: "text-gridiron", starter: "text-sky", depth: "text-chalk-dim", fringe: "text-chalk-faint",
};
export function archetypeTone(grade?: string, archetype?: string): string {
  if (archetype && /Aging|Fading|Win-Now/.test(archetype)) return "text-amber";
  return GRADE_TONE[grade || ""] || "text-chalk";
}

// durability risk score -> color
export const riskTone = (r: number | undefined | null): string =>
  r == null ? "text-chalk-faint" : r >= 60 ? "text-rose" : r >= 40 ? "text-amber" : "text-chalk-dim";

export const SIGNAL_TONE: Record<string, { cls: string; label: string }> = {
  BUY: { cls: "bg-gridiron/15 text-gridiron border-gridiron/30", label: "BUY" },
  SELL: { cls: "bg-rose/15 text-rose border-rose/30", label: "SELL" },
  HOLD: { cls: "bg-ink-700 text-chalk-faint border-ink-600", label: "HOLD" },
};

// recommendation kind -> full static classes (Tailwind purge needs whole strings)
export const REC_KIND: Record<string, { card: string; badge: string }> = {
  fix: { card: "border-rose/30", badge: "bg-rose/15 text-rose border-rose/30" },
  buy: { card: "border-gridiron/30", badge: "bg-gridiron/15 text-gridiron border-gridiron/30" },
  sell: { card: "border-amber/30", badge: "bg-amber/15 text-amber border-amber/30" },
  hold: { card: "border-sky/30", badge: "bg-sky/15 text-sky border-sky/30" },
  advice: { card: "border-violet/30", badge: "bg-violet/15 text-violet border-violet/30" },
};

// Recharts shared theme bits
export const CHART = {
  grid: "#252b3a",
  axis: "#6b7493",
  tip: { background: "#141821", border: "1px solid #252b3a", borderRadius: 12, color: "#e6e9f0" },
  green: "#3ddc97", sky: "#4cc2ff", amber: "#ffb454", rose: "#ff6b81", violet: "#a78bfa",
  faint: "#363d51",
};

// ── Justification content builders (deterministic, from the data — no invented numbers) ──
interface JC { title: string; lines: string[]; basis?: Basis; confidence?: "low" | "med" | "high"; source?: string }

function confLevel(p: PlayerRow): "low" | "med" | "high" {
  const g = p.value && p.games ? p.games : 0;
  if (g >= 10) return "high";
  if (g >= 6) return "med";
  return "low";
}

export function playerValueWhy(p: PlayerRow): JC {
  const v = p.value!;
  const blend = v.market_value != null && v.model_talent != null
    ? `market ${fmt0(v.market_value)} + talent ${fmt0(v.model_talent)} → ${fmt0(v.player_value)} (0.80/0.20 blend)`
    : v.market_value != null ? `market-only ${fmt0(v.market_value)}`
      : `model-only ${fmt0(v.player_value)} — real football + age (no dynasty market for past seasons)`;
  return {
    title: `${p.name} — ${v.archetype}`,
    lines: [
      `dynasty value ${fmt0(v.player_value)} (${pct(v.value_pctile)}) · grade ${v.grade}`,
      blend,
      v.xfp_pg != null ? `real: ${fmt(v.xfp_pg)} xFP/g · FPOE ${signed(v.fpoe_pg ?? 0)} · usage z ${signed(v.usage_z ?? 0, 1)}` : "",
      p.age != null ? `age ${p.age} → dynasty age-mult ${fmt(v.age_mult, 2)}` : "",
      `availability ${pct(v.availability)} · risk ${v.risk_score}/100 (separate from value)`,
      v.dir_labels?.length ? v.dir_labels.join(" · ") : "",
    ],
    basis: "real", confidence: confLevel(p), source: "nflverse + FantasyCalc (SF dynasty)",
  };
}

export function playerSignalWhy(p: PlayerRow): JC {
  const v = p.value!;
  // model & market are on the SAME 0-100 rostered-percentile scale; gap = model - market.
  const hasMkt = v.market_value != null && v.model_pctile != null;
  const mk = fmt0(v.market_value), md = fmt0(v.model_pctile), gap = signed(v.value_gap, 0);
  const fpoe = signed(v.fpoe_pg ?? 0);
  let lines: string[];
  if (v.signal === "BUY")
    lines = [
      hasMkt ? `our talent read (${md}) outranks the market (${mk}) — gap ${gap}`
        : "strong real-football role for the price",
      v.fpoe_pg != null && v.fpoe_pg <= -1
        ? `scoring below the opportunity earned (FPOE ${fpoe}) → positive regression due`
        : "young, ascending role with room to grow",
      "real role intact — a buy-low, not a discount",
    ];
  else if (v.signal === "SELL")
    lines = [
      hasMkt && v.value_gap <= -12
        ? `market (${mk}) prices him above our forward read (${md}) — gap ${gap}`
        : "forward outlook is fading",
      v.stage === "aging"
        ? "past the position's age cliff — sell the name while value is high"
        : `points ran ahead of opportunity (FPOE ${fpoe}, TD/efficiency-fuelled)`,
      "cash in before the regression",
    ];
  else
    lines = [hasMkt ? `value ≈ market (gap ${gap})` : "no strong edge either way",
      "a fair hold — no clear buy/sell edge"];
  return {
    title: `${v.signal}: ${p.name}`, lines, basis: "real", confidence: confLevel(p),
    source: hasMkt ? "model vs FantasyCalc market + regression + age"
      : "real-football regression + age (model-only)",
  };
}

// ── Archetype definitions + reusable stat explanations (for hover help) ──
export const ARCHETYPE_DEF: Record<string, string> = {
  "Franchise Cornerstone": "Young, elite-value player to build around for years.",
  "Established Star": "Prime-age, top-tier dynasty value — a current difference-maker.",
  "Aging Star": "Still elite, but past the position's age cliff — window closing; sell-high candidate.",
  "Ascending Starter": "Young starter with rising real usage — trending toward star.",
  "Rising Talent": "Young starter-grade value with room to grow.",
  "Proven Starter": "Prime-age, reliable starter — a known quantity.",
  "Win-Now Veteran": "Solid starter value but aging — useful now, declining outlook.",
  "Upside Flier": "Young depth piece with breakout upside.",
  "Known Depth": "Prime-age depth / bye-fill — replaceable.",
  "Fading Veteran": "Aging depth whose dynasty value is declining.",
  "Deep Sleeper": "Young fringe piece — a lottery ticket.",
  "Roster Filler": "Low-value depth.",
  "Blue-Chip Prospect": "High-value young prospect (thin NFL résumé) priced on talent + draft capital.",
  "Prospect Stash": "Speculative young prospect — a long-horizon stash.",
  "Deep Prospect": "Deep-stash prospect.",
};

export function archetypeWhy(p: PlayerRow): JC {
  const v = p.value!;
  return {
    title: v.archetype,
    lines: [
      ARCHETYPE_DEF[v.archetype] || "Player type from value + age + role.",
      `dynasty value ${fmt0(v.player_value)} · grade ${v.grade} · ${v.stage} career stage`,
      p.age != null ? `age ${p.age}${p.years_exp != null ? `, ${p.years_exp}y exp` : ""}` : "",
    ],
    basis: "both",
    source: "value model + age/career-stage",
  };
}

const h = (title: string, ...lines: string[]): JC => ({ title, lines });
export const EXPLAIN: Record<string, JC> = {
  overall_record: h("Overall record", "Combined regular-season W–L across every season in the league."),
  reg_finish: h("Regular-season finish", "Final standing by wins, then points-for (Sleeper's tiebreaker)."),
  all_play: h("All-play win %", "Your record if you played EVERY team every week — removes schedule luck."),
  luck: h("Luck", "Actual wins minus expected wins (from all-play). + = won more than the scores justified."),
  efficiency: h("Lineup efficiency", "Points you started ÷ your best possible lineup. The gap is points left on the bench."),
  avg_week: h("Average / week", "Mean weekly points (regular season), with std-dev and coefficient of variation."),
  ceiling: h("Ceiling (P90)", "A high weekly outcome — your 90th-percentile score."),
  floor: h("Floor (P10)", "A bad-week outcome — your 10th-percentile score."),
  strength: h("Roster strength", "Forward-looking dynasty value of your BEST startable lineup (fills the superflex slots with your highest-value eligible players), ranked vs the league. Built from real-football value, not last year's points."),
  win_now: h("Win-now strength", "Top-11 players' value × projected availability — this-year punch."),
  future: h("Future strength", "Dynasty value tied up in players age ≤ 25 — where the roster is heading."),
  durability: h("Durability", "Roster-average projected games-available — an injury-risk read, separate from value."),
  core_age: h("Core age", "Production-weighted average age of contributors (RB/WR weighted heavier; QB lighter)."),
  pos_strength: h("Positional strength", "Dynasty value of your starters at this position, ranked vs the league."),
  risk: h("Durability risk", "0–100 injury/availability risk — SEPARATE from value. A high-value player can still be high-risk."),
};
