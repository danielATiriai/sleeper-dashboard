import { useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import clsx from "clsx";
import type { LeagueBundle, PlayerRow } from "../types";
import { useAsync } from "../lib/useAsync";
import { getPlayers, getTeam } from "../lib/data";
import {
  EXPLAIN, POS_BG, archetypeTone, archetypeWhy, fmt, fmt0, ordinal, pct,
  playerSignalWhy, playerValueWhy, recordStr, riskTone, signed,
} from "../lib/ui";
import {
  ArchetypeBanner, BasisBadge, Card, EmptyState, ErrorState, HoverJustify, Loading,
  LabelRow, PodiumBadges, ProjectedBadge, RecCard, SectionTitle, SignalTag, Stat, TeamAvatar,
} from "../components/ui";
import { WeeklyChart } from "../components/charts";

export default function Team() {
  const { rid } = useParams();
  const league = useOutletContext<LeagueBundle>();
  const { data: team, error, loading } = useAsync(() => getTeam(rid!), [rid]);
  const { data: playersB } = useAsync(getPlayers, []);

  const seasonsAvail = team ? Object.keys(team.seasons).sort() : [];
  const [season, setSeason] = useState<string | null>(null);
  const activeSeason = season || (team ? league.latest_season : "");

  if (loading) return <Loading label="Loading team…" />;
  if (error) return <ErrorState error={error} />;
  if (!team) return null;
  const d = team.seasons[activeSeason] || team.seasons[league.latest_season];
  const isLatest = activeSeason === league.latest_season;
  // everything below is regenerated per season (as of that season's end)
  const arch = d.archetype || team.archetype;
  const indices = d.indices || team.indices;
  const labels = d.labels || team.labels;
  const recs = d.recommendations || team.recommendations;

  const roster = (playersB?.players || [])
    .filter((p) => p.roster_id === team.roster_id)
    .sort((a, b) => b.total - a.total);
  // The roster table is the SAME component every season: the current season uses
  // the live players bundle (market-blended dynasty value); past seasons use the
  // end-of-season snapshot embedded in the team bundle (model-only value).
  const rosterRows = isLatest ? roster : (d.roster || []);

  const teamName = (rosterId: number) =>
    league.teams.find((t) => t.roster_id === rosterId)?.team_name || `Team ${rosterId}`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <header className="flex flex-wrap items-center gap-4">
        <TeamAvatar url={team.avatar_url} name={team.team_name} size={60} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl font-extrabold tracking-tight">{team.team_name}</h1>
            <PodiumBadges podiums={team.career.podiums} />
          </div>
          <p className="text-sm text-chalk-dim">
            {team.display_name}
            {team.co_owners?.length ? " · co-owned" : ""} ·{" "}
            <span className="stat text-chalk">{recordStr(team.career.record)}</span> all-time
            {" · "}{team.career.seasons_played} seasons
            {team.career.championships > 0 && (
              <span className="ml-2 text-amber">🏆 {team.career.championships}× champion</span>
            )}
          </p>
        </div>
        <div className="flex rounded-xl2 border border-ink-700 p-0.5">
          {seasonsAvail.map((s) => (
            <button key={s} onClick={() => setSeason(s)}
              className={clsx("rounded-lg px-3 py-1 text-sm font-medium",
                s === activeSeason ? "bg-ink-700 text-chalk" : "text-chalk-faint hover:text-chalk")}>
              {s}
            </button>
          ))}
          <button disabled title="Current-state view — coming soon"
            className="cursor-not-allowed rounded-lg px-3 py-1 text-sm font-medium text-chalk-faint/40">
            2026
          </button>
        </div>
      </header>

      <ArchetypeBanner archetype={arch}>
        <div className="mt-3 flex flex-wrap gap-4 text-xs text-chalk-dim">
          <span>as of end of {activeSeason}</span>
          <span>skill <b className="stat text-chalk">{signed(indices.skill, 2)}</b></span>
          <span>luck <b className="stat text-chalk">{signed(indices.luck, 2)}</b></span>
          <span>trend <b className="stat text-chalk">{indices.trend > 0 ? "↗ rising" : indices.trend < 0 ? "↘ falling" : "→ flat"}</b></span>
        </div>
      </ArchetypeBanner>

      {/* Key stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label={`${activeSeason} record`} value={recordStr(d.record)}
          sub={d.champion ? "🏆 champion" : d.runner_up ? "runner-up" : d.made_playoffs ? `playoffs (${ordinal(d.playoff_finish)})` : "missed playoffs"} />
        <Stat label="Reg. finish" value={ordinal(d.final_standing)} sub={`#${d.pf_rank} in points`} help={EXPLAIN.reg_finish} />
        <Stat label="All-play" value={pct(d.luck.all_play_pct)} sub="vs whole league" help={EXPLAIN.all_play} />
        <Stat label="Luck" value={signed(d.luck.luck)} tone={d.luck.luck >= 0 ? "good" : "bad"} sub="wins vs expected" help={EXPLAIN.luck} />
        <Stat label="Lineup eff" value={pct(d.efficiency.eff)} sub={`${fmt0(d.efficiency.plob_total)} pts benched`}
          tone={d.efficiency.eff >= 0.85 ? "good" : "bad"} help={EXPLAIN.efficiency} />
        <Stat label="Avg / wk" value={fmt(d.consistency.mean)} sub={`±${fmt0(d.consistency.std)} · CV ${fmt(d.consistency.cv, 2)}`} help={EXPLAIN.avg_week} />
      </div>

      {/* Labels + recommendations */}
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div>
          <SectionTitle icon="◈" hint={`${labels.length} signals · end of ${activeSeason}`}>Team labels</SectionTitle>
          <div className="space-y-2">
            {labels.slice(0, 9).map((l) => <LabelRow key={l.key} label={l} />)}
          </div>
        </div>
        <div>
          <SectionTitle icon="➔" hint={`end of ${activeSeason}`}>Recommendations</SectionTitle>
          <div className="space-y-2">
            {recs.length
              ? recs.map((r, i) => <RecCard key={i} rec={r} />)
              : <EmptyState>No urgent moves — a well-rounded roster.</EmptyState>}
          </div>
        </div>
      </div>

      {/* Weekly chart */}
      <Card>
        <SectionTitle icon="∿" hint={`${activeSeason} regular season`}>
          Weekly scoring vs. optimal lineup
        </SectionTitle>
        <p className="mb-2 text-xs text-chalk-faint">
          Green = what you started. Dashed area = your best possible lineup. The gap is points left on the bench
          ({fmt(d.efficiency.plob_avg)}/wk, {d.efficiency.avoidable_losses} winnable losses).
        </p>
        <WeeklyChart weekly={d.weekly} />
        <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Ceiling (P90)" value={fmt0(d.consistency.ceiling)} help={EXPLAIN.ceiling} />
          <Stat label="Floor (P10)" value={fmt0(d.consistency.floor)} help={EXPLAIN.floor} />
          <Stat label="Boom weeks" value={pct(d.consistency.boom_rate)} tone="good"
            help={{ title: "Boom weeks", lines: ["Share of weeks scoring ≥ 1 std-dev above the league weekly average."] }} />
          <Stat label="Bust weeks" value={pct(d.consistency.bust_rate)} tone="bad"
            help={{ title: "Bust weeks", lines: ["Share of weeks scoring ≥ 1 std-dev below the league weekly average."] }} />
        </div>
      </Card>

      {/* Roster strength (dynasty value, as of the selected season) */}
      {d.strength && (
        <Card>
          <SectionTitle icon="◆"
            hint={isLatest ? "forward dynasty value — real talent" : `roster value as of end of ${activeSeason}`}
            help={EXPLAIN.strength}>
            Roster strength
          </SectionTitle>
          <div className="grid gap-4 sm:grid-cols-[1fr_1.4fr]">
            <div className="grid grid-cols-3 gap-2">
              <Stat label="Overall" value={pct(d.strength.overall_pctile)}
                sub="league rank" tone={d.strength.overall_pctile >= 0.5 ? "good" : "bad"}
                help={EXPLAIN.strength} />
              {isLatest && team.real?.strength ? <>
                <Stat label="Win-now" value={fmt0(team.real.strength.win_now)} sub="starters × availability" help={EXPLAIN.win_now} />
                <Stat label="Future" value={fmt0(team.real.strength.future)} sub="value age ≤ 25" help={EXPLAIN.future} />
              </> : <div className="col-span-2 self-center text-xs text-chalk-faint">Win-now / future are forward-looking — see the current ({league.latest_season}) view.</div>}
            </div>
            <div className="space-y-2 self-center">
              {(["QB", "RB", "WR", "TE"] as const).map((pos) => {
                const s = d.strength!.by_pos[pos];
                if (!s) return null;
                return (
                  <div key={pos} className="flex items-center gap-2">
                    <span className={clsx("w-8 text-xs font-semibold", POS_BG[pos]?.split(" ")[1])}>{pos}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-700">
                      <div className={clsx("h-full rounded-full",
                        s.pctile >= 0.66 ? "bg-gridiron" : s.pctile >= 0.33 ? "bg-sky" : "bg-rose")}
                        style={{ width: `${Math.max(3, s.pctile * 100)}%` }} />
                    </div>
                    <span className="stat w-10 text-right text-xs text-chalk-dim">{pct(s.pctile)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      )}

      {/* Roster — same columns every season. Current = forward dynasty value;
          past = the end-of-season snapshot (model-only value). */}
      <Card>
        <SectionTitle icon="📡"
          hint={isLatest ? "snap%, target share, WOPR via nflverse"
            : `snapshot as of end of ${activeSeason}`}>
          {isLatest ? "Roster — real-football profile" : `Roster — ${activeSeason}`}
        </SectionTitle>
        {isLatest && team.real?.available && (
          <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-chalk-dim">
            <span>core age <b className="stat text-chalk">{team.real.core_age}</b></span>
            <span>offense env <b className="stat text-chalk">{signed(team.real.env_score ?? 0, 2)}</b> <ProjectedBadge /></span>
            <span>opportunity tilt <b className={clsx("stat", (team.real.opp_output_gap ?? 0) >= 0 ? "text-gridiron" : "text-rose")}>{signed(team.real.opp_output_gap ?? 0, 2)}</b></span>
            <span>aDOT <b className="stat text-chalk">{fmt(team.real.adot)}</b></span>
          </div>
        )}
        {!isLatest && (
          <p className="mb-3 text-xs text-chalk-faint">
            The roster held at the end of {activeSeason}, with value, type, risk and signal snapshotted as of
            that season — built from that year's real football and age-at-the-time. Dynasty <i>market</i> prices
            only exist for the current season, so past values are model-only.
          </p>
        )}
        {rosterRows.length
          ? <RosterTable roster={rosterRows} />
          : <EmptyState>No roster data for {activeSeason}.</EmptyState>}
      </Card>

      {/* Buy / sell board + window */}
      {isLatest && team.real?.available && (
        <div className="grid gap-6 lg:grid-cols-3">
          <BuySell title="Buy-low / hold" tone="good" items={team.real.buys || []} kind="buy" />
          <BuySell title="Sell-high" tone="bad" items={team.real.sells || []} kind="sell" />
          <Card>
            <SectionTitle icon="⧗">Contention window</SectionTitle>
            <div className="mb-2 text-sm text-chalk-dim">
              Core age <b className="stat text-chalk">{team.real.core_age}</b>
            </div>
            {(team.real.young_core?.length ?? 0) > 0 && (
              <div className="mb-2">
                <div className="text-[11px] uppercase tracking-wide text-gridiron">Young core</div>
                {team.real.young_core!.map((p, i) => (
                  <div key={i} className="text-sm">{p.name} <span className="text-chalk-faint">{p.pos} · {p.age}</span></div>
                ))}
              </div>
            )}
            {(team.real.aging?.length ?? 0) > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wide text-amber">Aging / win-now</div>
                {team.real.aging!.map((p, i) => (
                  <div key={i} className="text-sm">{p.name} <span className="text-chalk-faint">{p.pos} · {p.age}</span></div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Rivalries — scoped to the selected season */}
      <Card>
        <SectionTitle icon="⚔" hint={`head-to-head · ${activeSeason}`}>Rivalries</SectionTitle>
        {(d.rivalries?.length ?? 0) > 0 ? (
          <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {d.rivalries!.map((r) => {
              const wpct = r.w / Math.max(r.w + r.l, 1);
              return (
                <Link key={r.opp_roster_id} to={`/team/${r.opp_roster_id}`}
                  className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-ink-800">
                  <span className="text-sm">{teamName(r.opp_roster_id)}</span>
                  <span className="flex items-center gap-2">
                    <span className={clsx("stat text-sm", wpct >= 0.6 ? "text-gridiron" : wpct <= 0.4 ? "text-rose" : "text-chalk-dim")}>
                      {r.w}-{r.l}{r.t ? "-" + r.t : ""}
                    </span>
                    <span className="text-[11px] text-chalk-faint">{r.meetings}×</span>
                  </span>
                </Link>
              );
            })}
          </div>
        ) : <EmptyState>No head-to-head games recorded for {activeSeason}.</EmptyState>}
      </Card>

      {/* Draft + waiver history */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle icon="✦" hint={`${activeSeason} draft`}>Draft results</SectionTitle>
          {d.draft?.n_picks ? (
            <>
              <div className="mb-2 flex gap-4 text-sm">
                <span>ROI <b className={clsx("stat", d.draft.roi >= 0 ? "text-gridiron" : "text-rose")}>{signed(d.draft.roi, 0)}</b></span>
                <span>hit rate <b className="stat text-chalk">{pct(d.draft.hit_rate)}</b></span>
                <span>{d.draft.n_picks} picks</span>
              </div>
              <DraftMini label="Best picks" picks={d.draft.best} tone="good" />
              <DraftMini label="Worst picks" picks={d.draft.worst} tone="bad" />
            </>
          ) : <EmptyState>No draft picks this season.</EmptyState>}
        </Card>
        <Card>
          <SectionTitle icon="⇄">Waiver wire & trades</SectionTitle>
          <div className="mb-2 grid grid-cols-3 gap-2">
            <Stat label="Pickups" value={d.management.adds} sub={`${pct(d.management.waiver_hit_rate)} hit`} />
            <Stat label="FAAB used" value={`$${d.management.faab_used}`} />
            <Stat label="Trades" value={d.management.trades} />
          </div>
          {d.management.waiver_scored.length > 0 && (
            <div>
              <div className="text-[11px] uppercase tracking-wide text-chalk-faint">Best pickups</div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {d.management.waiver_scored.map((w, i) => (
                  <span key={i} className="pill bg-ink-800 text-chalk text-xs">{w.name}
                    <span className="ml-1 text-chalk-faint">{w.pos} · {w.ppg}</span></span>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function RosterTable({ roster }: { roster: PlayerRow[] }) {
  if (!roster.length) return <EmptyState>No roster data.</EmptyState>;
  const sorted = [...roster].sort((a, b) => (b.value?.player_value ?? -1) - (a.value?.player_value ?? -1));
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-ink-700">
            {["Player", "Pos", "Age", "NFL", "Value", "Type", "Risk", "Snap%", "WOPR", "Signal"].map((h) => (
              <th key={h} className={clsx("th px-2 py-1.5", h !== "Player" && "text-right")}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => {
            const v = p.value;
            return (
              <tr key={p.pid} className="border-b border-ink-800/60 hover:bg-ink-850/50">
                <td className="px-2 py-1.5 font-medium" title={v?.dir_labels?.join(" · ")}>{p.name}</td>
                <td className="px-2 py-1.5 text-right">
                  <span className={clsx("pill text-[10px] font-semibold", POS_BG[p.pos] || "bg-ink-700 text-chalk-dim")}>{p.pos}</span>
                </td>
                <td className="stat px-2 py-1.5 text-right text-chalk-dim">{p.age ?? "—"}</td>
                <td className="px-2 py-1.5 text-right text-chalk-faint">{p.real?.real_team || p.nfl_team || "—"}</td>
                <td className="px-2 py-1.5 text-right">
                  {v ? (
                    <HoverJustify content={playerValueWhy(p)}>
                      <span className={clsx("stat font-semibold", archetypeTone(v.grade, v.archetype))}>{fmt0(v.player_value)}</span>
                    </HoverJustify>
                  ) : "—"}
                </td>
                <td className="px-2 py-1.5 text-right">
                  {v ? (
                    <HoverJustify content={archetypeWhy(p)}>
                      <span className={clsx("text-xs", archetypeTone(v.grade, v.archetype))}>{v.archetype}</span>
                    </HoverJustify>
                  ) : <span className="text-xs text-chalk-dim">—</span>}
                </td>
                <td className={clsx("stat px-2 py-1.5 text-right text-xs", riskTone(v?.risk_score))}>{v ? v.risk_score : "—"}</td>
                <td className="stat px-2 py-1.5 text-right text-chalk-dim">{p.real?.snap_pct != null ? fmt0(p.real.snap_pct) : "—"}</td>
                <td className="stat px-2 py-1.5 text-right text-chalk-dim">{p.real?.wopr != null ? fmt(p.real.wopr, 2) : "—"}</td>
                <td className="px-2 py-1.5 text-right">
                  {v ? <HoverJustify content={playerSignalWhy(p)}><SignalTag signal={v.signal} /></HoverJustify>
                    : <SignalTag signal={undefined} />}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function BuySell({ title, tone, items, kind }: {
  title: string; tone: "good" | "bad"; items: any[]; kind: "buy" | "sell";
}) {
  return (
    <Card>
      <SectionTitle icon={kind === "buy" ? "▲" : "▼"}>{title}</SectionTitle>
      {items.length ? (
        <div className="space-y-2">
          {items.map((p, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-ink-850/60 px-3 py-2">
              <div>
                <div className="text-sm font-medium">{p.name} <span className="text-chalk-faint">{p.pos}</span></div>
                <div className="text-[11px] text-chalk-faint">
                  {kind === "buy"
                    ? `${p.snap_pct != null ? fmt0(p.snap_pct) + "% snaps · " : ""}WOPR ${fmt(p.wopr, 2)} · ${p.league_ppg} PPG`
                    : `${p.league_ppg} PPG · ${pct(p.td_dependence ?? 0)} TD-reliant`}
                </div>
              </div>
              <span className={clsx("stat text-sm font-semibold", tone === "good" ? "text-gridiron" : "text-rose")}>
                {signed(p.gap, 2)}
              </span>
            </div>
          ))}
        </div>
      ) : <EmptyState>None flagged.</EmptyState>}
      <div className="mt-2"><BasisBadge basis="real" sm /></div>
    </Card>
  );
}

function DraftMini({ label, picks, tone }: { label: string; picks: any[]; tone: "good" | "bad" }) {
  if (!picks?.length) return null;
  return (
    <div className="mt-2">
      <div className="text-[11px] uppercase tracking-wide text-chalk-faint">{label}</div>
      <div className="mt-1 space-y-1">
        {picks.map((p, i) => (
          <div key={i} className="flex items-center justify-between text-sm">
            <span><span className="stat text-chalk-faint">{p.round}.{String(p.pick_no).padStart(2, "0")}</span> {p.name}
              <span className="ml-1 text-chalk-faint">{p.pos}</span></span>
            <span className={clsx("stat", tone === "good" ? "text-gridiron" : "text-rose")}>{signed(p.roi, 0)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
