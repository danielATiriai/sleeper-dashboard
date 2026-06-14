import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import clsx from "clsx";
import type { LeagueBundle, TeamSummary } from "../types";
import { ARCH_TONE, EXPLAIN, fmt0, pct, recordStr, signed } from "../lib/ui";
import { Card, Help, PodiumBadges, SectionTitle, TeamAvatar, ToneDot } from "../components/ui";

type SortKey = "strength" | "win_now" | "future" | "skill" | "record" | "pf" | "luck";

export default function PowerRankings() {
  const league = useOutletContext<LeagueBundle>();
  const [sort, setSort] = useState<SortKey>("strength");

  const val = (t: TeamSummary): number =>
    sort === "strength" ? t.strength ?? -1
      : sort === "win_now" ? t.win_now ?? -1
        : sort === "future" ? t.future ?? -1
          : sort === "skill" ? t.indices.skill
            : sort === "record" ? t.record.w + 0.5 * t.record.t
              : sort === "pf" ? t.pf
                : t.luck;
  const teams = [...league.teams].sort((a, b) => val(b) - val(a));

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight">Power Rankings</h1>
          <p className="text-sm text-chalk-dim">
            Forward-looking <b className="text-gridiron">roster strength</b> — current + future dynasty value
            of the roster (real football), not last year's results. Toggle to rank by other lenses.
          </p>
        </div>
        <div className="flex flex-wrap rounded-xl2 border border-ink-700 p-0.5 text-sm">
          {([["strength", "Strength"], ["win_now", "Win-now"], ["future", "Future"],
             ["skill", "Skill"], ["record", "Record"], ["luck", "Luck"]] as [SortKey, string][]).map(
            ([k, label]) => (
              <button key={k} onClick={() => setSort(k)}
                className={clsx("rounded-lg px-2.5 py-1 font-medium",
                  sort === k ? "bg-ink-700 text-chalk" : "text-chalk-faint hover:text-chalk")}>
                {label}
              </button>
            )
          )}
        </div>
      </header>

      <Card className="!p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink-700 bg-ink-850/60">
                <th className="th px-3 py-2.5">#</th>
                <th className="th px-3 py-2.5">Team</th>
                <th className="th px-3 py-2.5">Archetype</th>
                <th className="th px-3 py-2.5 text-right"><span className="inline-flex items-center gap-1">Strength<Help content={EXPLAIN.strength} /></span></th>
                <th className="th px-3 py-2.5 text-right">Win-now</th>
                <th className="th px-3 py-2.5 text-right">Future</th>
                <th className="th px-3 py-2.5 text-right">Record</th>
                <th className="th px-3 py-2.5 text-right">Skill</th>
                <th className="th px-3 py-2.5 text-right">Luck</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((t, i) => {
                const tone = ARCH_TONE[t.archetype.tone] || ARCH_TONE.slate;
                const sp = t.strength_pctile ?? 0;
                return (
                  <tr key={t.roster_id} className="border-b border-ink-800/60 hover:bg-ink-850/50">
                    <td className="stat px-3 py-2.5 text-chalk-faint">{i + 1}</td>
                    <td className="px-3 py-2.5">
                      <Link to={`/team/${t.roster_id}`} className="flex items-center gap-2.5 hover:text-gridiron">
                        <TeamAvatar url={t.avatar_url} name={t.team_name} size={28} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate font-semibold">{t.team_name}</span>
                            <PodiumBadges podiums={t.podiums} />
                          </div>
                          <div className="text-[11px] text-chalk-faint">{t.display_name}</div>
                        </div>
                      </Link>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={clsx("text-xs font-medium", tone.text)}>{t.archetype.name}</span>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-end gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-ink-700">
                          <div className={clsx("h-full rounded-full",
                            sp >= 0.66 ? "bg-gridiron" : sp >= 0.33 ? "bg-sky" : "bg-rose")}
                            style={{ width: `${Math.max(4, sp * 100)}%` }} />
                        </div>
                        <span className="stat w-9 text-right text-chalk-dim">{pct(sp)}</span>
                      </div>
                    </td>
                    <td className="stat px-3 py-2.5 text-right text-chalk-dim">{fmt0(t.win_now)}</td>
                    <td className="stat px-3 py-2.5 text-right text-chalk-dim">{fmt0(t.future)}</td>
                    <td className="stat px-3 py-2.5 text-right" title="all-time record">{recordStr(t.career_record ?? t.record)}</td>
                    <td className={clsx("stat px-3 py-2.5 text-right",
                      t.indices.skill >= 0 ? "text-gridiron" : "text-rose")}>{signed(t.indices.skill, 2)}</td>
                    <td className={clsx("stat px-3 py-2.5 text-right",
                      t.luck >= 0 ? "text-sky" : "text-amber")}>{signed(t.luck)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <SectionTitle icon="◆">How to read this</SectionTitle>
        <ul className="space-y-1.5 text-sm text-chalk-dim">
          <li><b className="text-gridiron">Strength</b> — forward-looking roster quality: the dynasty value of
            the best startable lineup, ranked vs the league. The default power ranking.</li>
          <li><b>Win-now</b> — starters' value × availability (this-year punch). <b>Future</b> — value tied up in
            age-≤25 players (where the roster is heading).</li>
          <li><b className="text-gridiron">Skill</b> — how the team actually played last year (results); <ToneDot tone="neutral" className="mx-1" /> <b className="text-sky">Luck</b> — wins above/below what the scores justified. Backward-looking context.</li>
        </ul>
      </Card>
    </div>
  );
}
