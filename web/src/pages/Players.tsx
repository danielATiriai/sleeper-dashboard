import { useMemo, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import clsx from "clsx";
import type { LeagueBundle, PlayerRow } from "../types";
import { useAsync } from "../lib/useAsync";
import { getPlayers } from "../lib/data";
import { POS_BG, archetypeTone, archetypeWhy, fmt, fmt0, playerSignalWhy, playerValueWhy, riskTone, signed } from "../lib/ui";
import { Card, EmptyState, ErrorState, HoverJustify, Loading, SectionTitle, SignalTag } from "../components/ui";

type SortKey = "value" | "season_value" | "risk" | "ppg" | "snap_pct" | "wopr" | "age";

export default function Players() {
  const league = useOutletContext<LeagueBundle>();
  const { data, error, loading } = useAsync(getPlayers, []);
  const [posF, setPosF] = useState("ALL");
  const [signalF, setSignalF] = useState("ALL");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("value");

  const teamName = (rid: number) =>
    league.teams.find((t) => t.roster_id === rid)?.team_name || `Team ${rid}`;

  const filtered = useMemo(() => {
    let rows = data?.players || [];
    if (posF !== "ALL") rows = rows.filter((p) => p.pos === posF);
    if (signalF !== "ALL") rows = rows.filter((p) => p.value?.signal === signalF);
    if (q.trim()) rows = rows.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
    const key = (p: PlayerRow): number =>
      sort === "value" ? p.value?.player_value ?? -1
        : sort === "season_value" ? p.value?.season_value ?? -1
          : sort === "risk" ? p.value?.risk_score ?? -1
            : sort === "ppg" ? p.ppg
              : sort === "snap_pct" ? p.real?.snap_pct ?? -1
                : sort === "wopr" ? p.real?.wopr ?? -1
                  : -(p.age ?? 99);
    return [...rows].sort((a, b) => key(b) - key(a));
  }, [data, posF, signalF, q, sort]);

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} />;
  if (!data) return null;

  const buys = [...data.players].filter((p) => p.value?.signal === "BUY")
    .sort((a, b) => (b.value!.value_gap) - (a.value!.value_gap)).slice(0, 6);
  const sells = [...data.players].filter((p) => p.value?.signal === "SELL")
    .sort((a, b) => (a.value!.value_gap) - (b.value!.value_gap)).slice(0, 6);

  const SortTh = ({ k, label }: { k: SortKey; label: string }) => (
    <th className={clsx("th cursor-pointer select-none px-2 py-2 text-right hover:text-chalk",
      sort === k && "text-gridiron")} onClick={() => setSort(k)}>
      {label}{sort === k ? " ↓" : ""}
    </th>
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Players</h1>
        <p className="text-sm text-chalk-dim">
          Forward-looking <b className="text-gridiron">dynasty value</b> (real-football model + market),
          with durability risk shown <b>separately</b> — a hurt star stays valuable. Last-year fantasy
          points are just history.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <BuySellBoard title="Buy-low (value &gt; market, due to regress up)" tone="good" rows={buys} teamName={teamName} kind="buy" />
        <BuySellBoard title="Sell-high (market &gt; value, TD/efficiency-fueled)" tone="bad" rows={sells} teamName={teamName} kind="sell" />
      </div>

      <Card className="!p-0 overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-ink-700 px-3 py-2.5">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search players…"
            className="w-44 rounded-lg border border-ink-700 bg-ink-850 px-3 py-1.5 text-sm outline-none focus:border-gridiron/50" />
          <FilterGroup value={posF} onChange={setPosF} options={["ALL", "QB", "RB", "WR", "TE"]} />
          <FilterGroup value={signalF} onChange={setSignalF} options={["ALL", "BUY", "SELL", "HOLD"]} />
          <span className="ml-auto text-xs text-chalk-faint">{filtered.length} players</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-ink-900">
              <tr className="border-b border-ink-700">
                <th className="th px-2 py-2">Player</th>
                <th className="th px-2 py-2">Pos</th>
                <th className="th px-2 py-2">NFL</th>
                <th className="th px-2 py-2">Owner</th>
                <SortTh k="age" label="Age" />
                <SortTh k="value" label="Value" />
                <th className="th px-2 py-2">Type</th>
                <SortTh k="risk" label="Risk" />
                <SortTh k="snap_pct" label="Snap%" />
                <SortTh k="wopr" label="WOPR" />
                <SortTh k="ppg" label="'25 PPG" />
                <th className="th px-2 py-2 text-right">Signal</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => {
                const v = p.value;
                return (
                  <tr key={p.pid} className="border-b border-ink-800/60 hover:bg-ink-850/50">
                    <td className="px-2 py-1.5 font-medium" title={v?.dir_labels?.join(" · ")}>{p.name}</td>
                    <td className="px-2 py-1.5"><span className={clsx("pill text-[10px] font-semibold", POS_BG[p.pos] || "bg-ink-700 text-chalk-dim")}>{p.pos}</span></td>
                    <td className="px-2 py-1.5 text-chalk-faint">{p.real?.real_team || p.nfl_team || "—"}</td>
                    <td className="px-2 py-1.5">
                      <Link to={`/team/${p.roster_id}`} className="text-chalk-dim hover:text-gridiron">{teamName(p.roster_id).slice(0, 16)}</Link>
                    </td>
                    <td className="stat px-2 py-1.5 text-right text-chalk-dim">{p.age ?? "—"}</td>
                    <td className="px-2 py-1.5 text-right">
                      {v ? (
                        <HoverJustify content={playerValueWhy(p)}>
                          <span className={clsx("stat font-semibold", archetypeTone(v.grade, v.archetype))}>{fmt0(v.player_value)}</span>
                        </HoverJustify>
                      ) : "—"}
                    </td>
                    <td className="px-2 py-1.5">
                      {v ? (
                        <HoverJustify content={archetypeWhy(p)}>
                          <span className={clsx("text-xs", archetypeTone(v.grade, v.archetype))}>{v.archetype}</span>
                        </HoverJustify>
                      ) : <span className="text-xs text-chalk-dim">—</span>}
                    </td>
                    <td className={clsx("stat px-2 py-1.5 text-right text-xs", riskTone(v?.risk_score))}
                      title={v?.dir_labels?.includes("Injury-risk") ? "elevated durability risk" : ""}>
                      {v ? v.risk_score : "—"}
                    </td>
                    <td className="stat px-2 py-1.5 text-right text-chalk-dim">{p.real?.snap_pct != null ? fmt0(p.real.snap_pct) : "—"}</td>
                    <td className="stat px-2 py-1.5 text-right text-chalk-dim">{p.real?.wopr != null ? fmt(p.real.wopr, 2) : "—"}</td>
                    <td className="stat px-2 py-1.5 text-right text-chalk-faint">{fmt(p.ppg)}</td>
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
      </Card>
    </div>
  );
}

function FilterGroup({ value, onChange, options }: {
  value: string; onChange: (v: string) => void; options: string[];
}) {
  return (
    <div className="flex rounded-lg border border-ink-700 p-0.5 text-xs">
      {options.map((o) => (
        <button key={o} onClick={() => onChange(o)}
          className={clsx("rounded px-2 py-1 font-medium",
            value === o ? "bg-ink-700 text-chalk" : "text-chalk-faint hover:text-chalk")}>{o}</button>
      ))}
    </div>
  );
}

function BuySellBoard({ title, tone, rows, teamName, kind }: {
  title: string; tone: "good" | "bad"; rows: PlayerRow[];
  teamName: (rid: number) => string; kind: "buy" | "sell";
}) {
  return (
    <Card>
      <SectionTitle icon={kind === "buy" ? "▲" : "▼"}>{title}</SectionTitle>
      {rows.length ? (
        <div className="space-y-1.5">
          {rows.map((p) => (
            <div key={p.pid} className="flex items-center justify-between rounded-lg bg-ink-850/60 px-3 py-1.5">
              <div className="min-w-0">
                <span className="text-sm font-medium">{p.name}</span>
                <span className="ml-1 text-[11px] text-chalk-faint">{p.pos} · {teamName(p.roster_id).slice(0, 14)}</span>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-chalk-faint">
                <span>val {fmt0(p.value?.player_value)} · mkt {fmt0(p.value?.market_value)}</span>
                <HoverJustify content={playerSignalWhy(p)}>
                  <span className={clsx("stat font-semibold", tone === "good" ? "text-gridiron" : "text-rose")}>
                    {signed(p.value?.value_gap ?? 0, 0)}
                  </span>
                </HoverJustify>
              </div>
            </div>
          ))}
        </div>
      ) : <EmptyState>None flagged.</EmptyState>}
    </Card>
  );
}
