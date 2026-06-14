import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import clsx from "clsx";
import type { LeagueBundle, Trade } from "../types";
import { useAsync } from "../lib/useAsync";
import { getTrades } from "../lib/data";
import { fmt0, pct, signed } from "../lib/ui";
import { Card, EmptyState, ErrorState, Loading, SectionTitle } from "../components/ui";

export default function Trades() {
  const league = useOutletContext<LeagueBundle>();
  const { data, error, loading } = useAsync(getTrades, []);
  const [season, setSeason] = useState<string | null>(null);

  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} />;
  if (!data) return null;
  const activeSeason = season || league.latest_season;
  const sd = data.seasons[activeSeason] || { trades: [], activity: [] };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Trades &amp; Transactions</h1>
          <p className="text-sm text-chalk-dim">Realized rest-of-season value per side. Who won the deal?</p>
        </div>
        <div className="flex rounded-xl2 border border-ink-700 p-0.5 text-sm">
          {league.seasons.map((s) => (
            <button key={s} onClick={() => setSeason(s)}
              className={clsx("rounded-lg px-3 py-1 font-medium",
                s === activeSeason ? "bg-ink-700 text-chalk" : "text-chalk-faint hover:text-chalk")}>{s}</button>
          ))}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-3">
          <SectionTitle icon="⇄" hint={`${sd.trades.length} trades`}>Trade ledger</SectionTitle>
          {sd.trades.length ? sd.trades.map((t, i) => <TradeCard key={i} t={t} />)
            : <EmptyState>No trades this season.</EmptyState>}
        </div>

        <div>
          <SectionTitle icon="▤">Activity leaderboard</SectionTitle>
          <Card className="!p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink-700 bg-ink-850/60">
                  <th className="th px-3 py-2">Team</th>
                  <th className="th px-3 py-2 text-right">Adds</th>
                  <th className="th px-3 py-2 text-right">FAAB</th>
                  <th className="th px-3 py-2 text-right">Trades</th>
                  <th className="th px-3 py-2 text-right">Hit%</th>
                </tr>
              </thead>
              <tbody>
                {sd.activity.map((a) => (
                  <tr key={a.roster_id} className="border-b border-ink-800/60">
                    <td className="px-3 py-2 truncate">{a.team_name}</td>
                    <td className="stat px-3 py-2 text-right">{a.adds}</td>
                    <td className="stat px-3 py-2 text-right text-chalk-dim">${a.faab_used}</td>
                    <td className="stat px-3 py-2 text-right text-chalk-dim">{a.trades}</td>
                    <td className="stat px-3 py-2 text-right text-chalk-dim">{pct(a.waiver_hit_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>
    </div>
  );
}

function TradeCard({ t }: { t: Trade }) {
  const rids = t.roster_ids;
  return (
    <Card>
      <div className="mb-2 flex items-center justify-between text-xs text-chalk-faint">
        <span>Week {t.week}</span>
        {t.pending
          ? <span className="pill border border-amber/30 bg-amber/10 text-amber text-[10px]">◔ pending — future picks unrealized</span>
          : <span className="pill border border-ink-600 bg-ink-800 text-chalk-dim text-[10px]">graded</span>}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {rids.map((rid) => {
          const side = t.sides[String(rid)];
          const roi = side?.roi ?? 0;
          return (
            <div key={rid} className="rounded-xl2 border border-ink-700/60 bg-ink-850/50 p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="truncate text-sm font-semibold">{t.team_names[String(rid)]}</span>
                {t.pending
                  ? <span className="stat text-[11px] text-amber">TBD</span>
                  : <span className={clsx("stat text-xs font-semibold",
                    roi > 1 ? "text-gridiron" : roi < -1 ? "text-rose" : "text-chalk-faint")}>
                    {roi > 1 ? "▲ won " : roi < -1 ? "▼ lost " : ""}{signed(roi, 0)}
                  </span>}
              </div>
              <div className="space-y-1">
                {(side?.received || []).map((p, j) => (
                  <div key={j} className="flex items-center justify-between text-sm">
                    <span>
                      <span className="text-chalk-faint">{p.pos}</span> {p.name}
                      {p.ongoing && <span className="ml-1 text-[10px] text-gridiron" title="still on roster — value still accruing">●</span>}
                    </span>
                    <span className="stat text-xs text-chalk-faint">{p.tenure_points} pts</span>
                  </div>
                ))}
                {(side?.realized_picks || []).map((a, j) => (
                  <div key={`rp${j}`} className="flex items-center justify-between text-sm">
                    <span className="text-chalk-dim">
                      ✦ {a.season} R{a.round} → <span className="text-chalk">{a.name}</span>
                      {a.held
                        ? <span className="ml-1 text-[10px] text-gridiron" title="still rostered">●</span>
                        : <span className="ml-1 text-[10px] text-chalk-faint">flipped</span>}
                    </span>
                    <span className="stat text-[11px] text-chalk-faint">{a.value != null ? `val ${a.value}` : "pick"}</span>
                  </div>
                ))}
                {(side?.future_picks || []).map((p, j) => (
                  <div key={`fp${j}`} className="flex items-center justify-between text-sm">
                    <span className="text-chalk-faint">✦ {p.season} R{p.round} pick</span>
                    <span className="stat text-[11px] text-amber">future</span>
                  </div>
                ))}
                {!side?.received?.length && !side?.realized_picks?.length && !side?.future_picks?.length && (
                  <div className="text-xs text-chalk-faint">FAAB only</div>
                )}
              </div>
              {!t.pending && (side?.realized_pts !== undefined) && (
                <div className="mt-1.5 border-t border-ink-800 pt-1 text-[10px] text-chalk-faint">
                  produced {signed(side.realized_pts ?? 0, 0)} · still holds {fmt0(side.held_value)} dynasty value
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-chalk-faint">
        {t.pending
          ? "Verdict withheld: includes future draft picks, which can't be graded until they become players."
          : "Won/lost blends realized production over each player's full tenure with the remaining DYNASTY value of still-held players (● = held). Picks are graded by the rookie they became."}
      </p>
    </Card>
  );
}
