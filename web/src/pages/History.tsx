import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import clsx from "clsx";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { LeagueBundle } from "../types";
import { useAsync } from "../lib/useAsync";
import { getTrends } from "../lib/data";
import { CHART, EXPLAIN, fmt, fmt0, ordinal, pct, recordStr } from "../lib/ui";
import { Card, ErrorState, Loading, SectionTitle, Stat } from "../components/ui";

const PALETTE = ["#3ddc97", "#4cc2ff", "#ffb454", "#ff6b81", "#a78bfa",
  "#5dcaa5", "#f0997b", "#85b7eb"];

export default function History() {
  const league = useOutletContext<LeagueBundle>();
  const { data: trends, error, loading } = useAsync(getTrends, []);
  const [season, setSeason] = useState<string | null>(null);

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} />;
  if (!trends) return null;
  const activeSeason = season || league.latest_season;
  const standings = trends.standings[activeSeason] || [];

  const teams = league.teams;
  const allPlay = teams.map((t) => t.all_play_pct);
  const balance = Math.max(...allPlay) - Math.min(...allPlay);
  const pfs = teams.map((t) => t.pf);
  const pfSpread = Math.max(...pfs) - Math.min(...pfs);

  const allTime = [...teams]
    .map((t) => ({ t, champs: t.championships }))
    .sort((a, b) => b.champs - a.champs || a.t.archetype.name.localeCompare(b.t.archetype.name));

  // strength-trend: one row per season, a column per team (pctile 0-100)
  const trendRows = trends.seasons.map((s) => {
    const row: Record<string, number | string | null> = { season: s };
    trends.strength_trend.forEach((t) => {
      const pt = t.points.find((p) => p.season === s);
      row[t.team_name] = pt ? Math.round(pt.pctile * 100) : null;
    });
    return row;
  });

  const cell = (rid: number, oppRid: number) => {
    if (rid === oppRid) return null;
    const r = trends.rivalry_matrix[String(rid)]?.[String(oppRid)];
    if (!r || r.meetings === 0) return { txt: "—", cls: "text-chalk-faint" };
    const wp = r.w / Math.max(r.w + r.l, 1);
    return {
      txt: `${r.w}-${r.l}`,
      cls: wp >= 0.6 ? "bg-gridiron/15 text-gridiron"
        : wp <= 0.4 ? "bg-rose/15 text-rose" : "text-chalk-dim",
    };
  };
  const order = [...teams].sort((a, b) => a.roster_id - b.roster_id);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">History &amp; Trends</h1>
        <p className="text-sm text-chalk-dim">
          {league.seasons.join("–")} · {league.seasons.length} seasons — champions, standings, and how the
          league and each roster are trending.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Competitive balance" value={pct(balance)} sub="all-play spread (lower = tighter)"
          help={{ title: "Competitive balance", lines: ["Gap between the best and worst all-play win % — lower means a tighter, more even league."] }} />
        <Stat label="Scoring spread" value={fmt0(pfSpread)} sub="PF gap, 1st→last"
          help={{ title: "Scoring spread", lines: ["Points-for gap between the highest- and lowest-scoring team this season."] }} />
        <Stat label="Avg / week" value={fmt(trends.scoring[trends.scoring.length - 1]?.avg_weekly)} sub={`${league.latest_season} season`}
          help={EXPLAIN.avg_week} />
        <Stat label="Seasons" value={league.seasons.length} sub={league.seasons.join("–")} />
      </div>

      <Card>
        <SectionTitle icon="🏆">Championship lineage</SectionTitle>
        <div className="flex flex-wrap gap-3">
          {[...trends.champions].reverse().map((c) => (
            <Link key={c.season} to={`/team/${c.champion_rid}`}
              className="flex min-w-[180px] flex-1 items-center gap-3 rounded-xl2 border border-amber/30 bg-amber/5 p-3 hover:bg-amber/10">
              <span className="text-3xl">🏆</span>
              <div>
                <div className="text-[11px] uppercase tracking-wide text-amber">{c.season}</div>
                <div className="font-bold">{c.champion}</div>
                <div className="text-xs text-chalk-faint">def. {c.runner_up}</div>
              </div>
            </Link>
          ))}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle icon="∿"
            help={{ title: "Scoring environment", lines: ["League-average points per team per week each season, with the single-game high. Flat = roster strength (not inflation) drives results."] }}>
            Scoring environment
          </SectionTitle>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trends.scoring} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="season" stroke={CHART.axis} fontSize={12} tickLine={false} />
              <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} domain={["auto", "auto"]} />
              <Tooltip contentStyle={CHART.tip} />
              <Line type="monotone" dataKey="avg_weekly" name="avg/wk" stroke={CHART.green} strokeWidth={2.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="high" name="weekly high" stroke={CHART.amber} strokeWidth={1.5} strokeDasharray="4 3" dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <SectionTitle icon="↗"
            help={{ title: "Roster strength trend", lines: ["Each team's roster strength percentile by season, computed from THAT year's real-football value (talent + age at the time) — so the history is accurate to its year. Rising lines = rosters getting better."] }}>
            Roster strength trend
          </SectionTitle>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trendRows} margin={{ top: 8, right: 16, left: -22, bottom: 0 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="season" stroke={CHART.axis} fontSize={12} tickLine={false} />
              <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} domain={[0, 100]}
                tickFormatter={(v) => `${v}%`} />
              <Tooltip contentStyle={CHART.tip} formatter={(v: number) => [`${v}%`, ""]} />
              {trends.strength_trend.map((t, i) => (
                <Line key={t.roster_id} type="monotone" dataKey={t.team_name}
                  stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={{ r: 3 }}
                  connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px]">
            {trends.strength_trend.map((t, i) => (
              <span key={t.roster_id} className="inline-flex items-center gap-1 text-chalk-faint">
                <span className="h-2 w-2 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                {t.team_name.length > 16 ? t.team_name.slice(0, 15) + "…" : t.team_name}
              </span>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <SectionTitle icon="▦">Final standings</SectionTitle>
            <div className="flex rounded-lg border border-ink-700 p-0.5 text-sm">
              {league.seasons.map((s) => (
                <button key={s} onClick={() => setSeason(s)}
                  className={clsx("rounded px-2.5 py-0.5 font-medium",
                    s === activeSeason ? "bg-ink-700 text-chalk" : "text-chalk-faint hover:text-chalk")}>{s}</button>
              ))}
            </div>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink-700">
                <th className="th px-2 py-1.5">#</th>
                <th className="th px-2 py-1.5">Team</th>
                <th className="th px-2 py-1.5 text-right">Record</th>
                <th className="th px-2 py-1.5 text-right">PF</th>
                <th className="th px-2 py-1.5 text-right">PA</th>
                <th className="th px-2 py-1.5 text-right">All-play</th>
              </tr>
            </thead>
            <tbody>
              {standings.map((r) => (
                <tr key={r.roster_id} className="border-b border-ink-800/60 hover:bg-ink-850/50">
                  <td className="stat px-2 py-1.5 text-chalk-faint">{r.final_standing}</td>
                  <td className="px-2 py-1.5">
                    <Link to={`/team/${r.roster_id}`} className="font-medium hover:text-gridiron">
                      {r.champion && <span className="mr-1">🏆</span>}{r.team_name}
                    </Link>
                  </td>
                  <td className="stat px-2 py-1.5 text-right">{recordStr(r.record)}</td>
                  <td className="stat px-2 py-1.5 text-right text-chalk-dim">{fmt0(r.pf)}</td>
                  <td className="stat px-2 py-1.5 text-right text-chalk-dim">{fmt0(r.pa)}</td>
                  <td className="stat px-2 py-1.5 text-right text-chalk-dim">{pct(r.all_play_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card>
          <SectionTitle icon="◷">All-time résumés</SectionTitle>
          <div className="space-y-1.5">
            {allTime.map(({ t, champs }) => (
              <Link key={t.roster_id} to={`/team/${t.roster_id}`}
                className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-ink-800">
                <span className="truncate text-sm">{t.team_name}</span>
                <span className="text-xs text-chalk-faint">
                  {champs > 0 ? <span className="text-amber">{"🏆".repeat(champs)} </span> : ""}
                  best {ordinal(t.final_standing)}
                </span>
              </Link>
            ))}
          </div>
        </Card>
      </div>

      <Card className="overflow-x-auto">
        <SectionTitle icon="⚔" hint="row vs column, all-time"
          help={{ title: "Rivalry matrix", lines: ["Head-to-head record (row team's W-L vs the column team) across every season + playoffs. Green = winning record, red = losing."] }}>
          Rivalry matrix
        </SectionTitle>
        <table className="w-full text-center text-xs">
          <thead>
            <tr>
              <th className="th px-2 py-1 text-left">Team</th>
              {order.map((o) => (
                <th key={o.roster_id} className="th px-1 py-1" title={o.team_name}>
                  {o.team_name.split(" ").map((w) => w[0]).join("").slice(0, 3)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {order.map((t) => (
              <tr key={t.roster_id} className="border-t border-ink-800/60">
                <td className="px-2 py-1 text-left font-medium">{t.team_name}</td>
                {order.map((o) => {
                  const c = cell(t.roster_id, o.roster_id);
                  return (
                    <td key={o.roster_id}
                      className={clsx("stat px-1 py-1", o.roster_id === t.roster_id && "bg-ink-800")}>
                      {c ? <span className={clsx("inline-block rounded px-1", c.cls)}>{c.txt}</span> : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
