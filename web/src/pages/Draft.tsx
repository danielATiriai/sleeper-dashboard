import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import clsx from "clsx";
import {
  CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis, Cell,
} from "recharts";
import type { DraftBundle, LeagueBundle } from "../types";
import { useAsync } from "../lib/useAsync";
import { getDraft } from "../lib/data";
import { CHART, POS_BG, pct, signed } from "../lib/ui";
import { Card, EmptyState, ErrorState, Loading, ProjectedBadge, SectionTitle } from "../components/ui";

export default function Draft() {
  const { data, error, loading } = useAsync(getDraft, []);
  useOutletContext<LeagueBundle>();
  const [view, setView] = useState<string | null>(null);

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} />;
  if (!data) return null;
  const rookieSeasons = Object.keys(data.seasons).sort();
  const preview = data.preview;
  const active = view || (preview ? "preview" : rookieSeasons[rookieSeasons.length - 1]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Rookie Drafts</h1>
          <p className="text-sm text-chalk-dim">
            Dynasty rookie drafts — value over expectation, plus the upcoming class preview.
          </p>
        </div>
        <div className="flex rounded-xl2 border border-ink-700 p-0.5 text-sm">
          {rookieSeasons.map((s) => (
            <button key={s} onClick={() => setView(s)}
              className={clsx("rounded-lg px-3 py-1 font-medium",
                s === active ? "bg-ink-700 text-chalk" : "text-chalk-faint hover:text-chalk")}>{s}</button>
          ))}
          {preview && (
            <button onClick={() => setView("preview")}
              className={clsx("rounded-lg px-3 py-1 font-medium",
                active === "preview" ? "bg-ink-700 text-chalk" : "text-chalk-faint hover:text-chalk")}>
              {preview.season} ▸ preview
            </button>
          )}
        </div>
      </header>

      {active === "preview" && preview ? <DraftPreview preview={preview} />
        : <DraftSeason sd={data.seasons[active]} season={active} />}
    </div>
  );
}

function DraftSeason({ sd, season }: { sd: DraftBundle["seasons"][string] | undefined; season: string }) {
  if (!sd) return <EmptyState>No draft data for {season}.</EmptyState>;
  return (
    <>
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Card>
          <SectionTitle icon="◇" hint="dot = pick · line = expected"
            help={{ title: "Value vs. draft slot", lines: ["Each rookie's season fantasy total vs. the smoothed expectation for that pick number. Above the line = a steal."] }}>
            Value vs. draft slot
          </SectionTitle>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={sd.board} margin={{ top: 8, right: 12, left: -16, bottom: 4 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="pick_no" stroke={CHART.axis} fontSize={11} tickLine={false}
                label={{ value: "pick #", fill: CHART.axis, fontSize: 11, position: "insideBottomRight", dy: 8 }} />
              <YAxis stroke={CHART.axis} fontSize={11} tickLine={false} />
              <Tooltip contentStyle={CHART.tip}
                formatter={(v: number, n: string) => [v.toFixed(0), n === "actual" ? "Actual pts" : "Expected"]}
                labelFormatter={(p) => `Pick ${p}`} />
              <Line type="monotone" dataKey="expected" stroke={CHART.faint} strokeWidth={1.5}
                strokeDasharray="4 3" dot={false} name="expected" />
              <Scatter dataKey="actual" name="actual">
                {sd.board.map((p, i) => <Cell key={i} fill={p.roi >= 0 ? CHART.green : CHART.rose} />)}
              </Scatter>
            </ComposedChart>
          </ResponsiveContainer>
        </Card>

        <Card>
          <SectionTitle icon="▲" help={{ title: "Draft ROI", lines: ["Sum of each pick's points over its slot expectation. Hit rate = share of picks that beat expectation."] }}>
            Draft ROI by team
          </SectionTitle>
          <div className="space-y-1.5">
            {sd.per_team.map((t) => (
              <div key={t.roster_id} className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-ink-800">
                <span className="truncate text-sm">{t.team_name}</span>
                <span className="flex items-center gap-3">
                  <span className="text-[11px] text-chalk-faint">{pct(t.hit_rate)} hit · {t.n_picks}p</span>
                  <span className={clsx("stat w-12 text-right text-sm font-semibold",
                    t.roi >= 0 ? "text-gridiron" : "text-rose")}>{signed(t.roi, 0)}</span>
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="!p-0 overflow-hidden">
        <div className="px-4 py-3"><SectionTitle icon="✦">{season} rookie draft board</SectionTitle></div>
        <div className="max-h-[480px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-ink-900">
              <tr className="border-y border-ink-700">
                {["Pick", "Player", "Pos", "Team", "Pts", "Exp", "+/−"].map((h) => (
                  <th key={h} className={clsx("th px-3 py-2", h !== "Player" && h !== "Pos" && h !== "Team" && "text-right")}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sd.board.map((p) => (
                <tr key={p.pick_no} className="border-b border-ink-800/60 hover:bg-ink-850/50">
                  <td className="stat px-3 py-1.5 text-chalk-faint">{p.round}.{String(p.pick_no).padStart(2, "0")}</td>
                  <td className="px-3 py-1.5 font-medium">{p.name}</td>
                  <td className="px-3 py-1.5"><span className={clsx("pill text-[10px] font-semibold", POS_BG[p.pos] || "bg-ink-700 text-chalk-dim")}>{p.pos}</span></td>
                  <td className="px-3 py-1.5 text-chalk-faint">{p.team_name}</td>
                  <td className="stat px-3 py-1.5 text-right">{p.actual}</td>
                  <td className="stat px-3 py-1.5 text-right text-chalk-faint">{p.expected}</td>
                  <td className={clsx("stat px-3 py-1.5 text-right font-semibold", p.roi >= 0 ? "text-gridiron" : "text-rose")}>{signed(p.roi, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

function DraftPreview({ preview }: { preview: NonNullable<DraftBundle["preview"]> }) {
  const rounds = Array.from({ length: preview.rounds }, (_, i) => i + 1);
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <SectionTitle icon="🔮"
          help={{ title: "Draft preview", lines: ["Projected pick order is the reverse of last season's regular-season standings (worst team picks 1.01). Ownership reflects already-traded picks. Order is an estimate and will shift with the final draft-order rules."] }}>
          {preview.season} rookie draft preview
        </SectionTitle>
        <ProjectedBadge />
      </div>
      <p className="mb-3 text-xs text-chalk-faint">{preview.order_basis}</p>
      <div className="grid gap-4 sm:grid-cols-3">
        {rounds.map((rnd) => (
          <div key={rnd}>
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-chalk-faint">Round {rnd}</div>
            <div className="space-y-1">
              {preview.board.filter((p) => p.round === rnd).map((p) => (
                <div key={p.pick_no} className="flex items-center gap-2 rounded-lg bg-ink-850/60 px-2.5 py-1.5 text-sm">
                  <span className="stat w-8 text-chalk-faint">{p.round}.{String(p.slot).padStart(2, "0")}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {p.owner_team}
                    {p.traded && <span className="ml-1 text-[10px] text-amber">via {p.orig_team.split(" ")[0]}</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
