import { Link, useNavigate, useOutletContext } from "react-router-dom";
import type { LeagueBundle } from "../types";
import { useAsync } from "../lib/useAsync";
import { getTrends } from "../lib/data";
import { ARCH_TONE, fmt0, recordStr, signed, pct } from "../lib/ui";
import { Card, SectionTitle, Stat, TeamAvatar } from "../components/ui";
import { QuadrantScatter } from "../components/charts";

export default function Overview() {
  const league = useOutletContext<LeagueBundle>();
  const navigate = useNavigate();
  const { data: trends } = useAsync(getTrends, []);
  const teams = league.teams;

  const champ = teams.find((t) => t.champion);
  const byPf = [...teams].sort((a, b) => b.pf - a.pf);
  const byLuck = [...teams].sort((a, b) => a.luck - b.luck);
  const byEff = [...teams].sort((a, b) => b.efficiency - a.efficiency);
  const bySkill = [...teams].sort((a, b) => b.indices.skill - a.indices.skill);

  const quad = teams.map((t) => ({
    x: t.indices.skill, y: t.indices.luck, name: t.team_name,
    tone: t.archetype.tone, rid: t.roster_id,
  }));

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">{league.league.name}</h1>
          <p className="mt-1 text-sm text-chalk-dim">
            {league.latest_season} season · {league.n_teams}-team superflex dynasty · analyzed across{" "}
            {league.seasons.join("–")}
          </p>
        </div>
        {champ && (
          <Link to={`/team/${champ.roster_id}`}
            className="flex items-center gap-3 rounded-xl2 border border-amber/40 bg-amber/10 px-4 py-2">
            <span className="text-2xl">🏆</span>
            <div>
              <div className="text-[11px] uppercase tracking-wide text-amber">{league.latest_season} Champion</div>
              <div className="font-bold text-chalk">{champ.team_name}</div>
            </div>
          </Link>
        )}
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Most points" value={`${fmt0(byPf[0].pf)}`} sub={byPf[0].team_name} tone="good" />
        <Stat label="Luckiest" value={signed(byLuck[byLuck.length - 1].luck)}
          sub={byLuck[byLuck.length - 1].team_name} tone="neutral" />
        <Stat label="Unluckiest" value={signed(byLuck[0].luck)}
          sub={byLuck[0].team_name} tone="bad" />
        <Stat label="Best manager" value={pct(byEff[0].efficiency)}
          sub={byEff[0].team_name} tone="good" />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <SectionTitle icon="◇" hint="dot = team · click to open">Luck vs. Skill</SectionTitle>
          <p className="mb-1 text-xs text-chalk-faint">
            Right = scores like a contender. Up = wins more than the scoring justifies. Bottom-right = unlucky studs.
          </p>
          <QuadrantScatter points={quad} onSelect={(rid) => navigate(`/team/${rid}`)} />
        </Card>

        <Card>
          <SectionTitle icon="▲">Power ranking</SectionTitle>
          <p className="mb-2 text-xs text-chalk-faint">By underlying skill, not record.</p>
          <ol className="space-y-1.5">
            {bySkill.map((t, i) => {
              const tone = ARCH_TONE[t.archetype.tone] || ARCH_TONE.slate;
              return (
                <li key={t.roster_id}>
                  <Link to={`/team/${t.roster_id}`}
                    className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-ink-800">
                    <span className="w-5 text-center font-mono text-sm text-chalk-faint">{i + 1}</span>
                    <TeamAvatar url={t.avatar_url} name={t.team_name} size={26} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">{t.team_name}</div>
                      <div className={`text-[11px] ${tone.text}`}>{t.archetype.name}</div>
                    </div>
                    <div className="text-right">
                      <div className="stat text-sm">{recordStr(t.record)}</div>
                      <div className="stat text-[11px] text-chalk-faint">skill {signed(t.indices.skill, 2)}</div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ol>
        </Card>
      </div>

      {trends && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <SectionTitle icon="🏆">Championship lineage</SectionTitle>
            <div className="space-y-2">
              {[...trends.champions].reverse().map((c) => (
                <Link key={c.season} to={`/team/${c.champion_rid}`}
                  className="flex items-center justify-between rounded-lg px-2 py-2 hover:bg-ink-800">
                  <div className="flex items-center gap-3">
                    <span className="stat w-10 text-chalk-faint">{c.season}</span>
                    <span className="text-amber">🏆</span>
                    <span className="font-semibold">{c.champion}</span>
                  </div>
                  <span className="text-xs text-chalk-faint">def. {c.runner_up}</span>
                </Link>
              ))}
            </div>
          </Card>
          <Card>
            <SectionTitle icon="∿">Scoring environment</SectionTitle>
            <div className="space-y-3 pt-2">
              {trends.scoring.map((s) => (
                <div key={s.season} className="flex items-center gap-3">
                  <span className="stat w-12 text-chalk-faint">{s.season}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-700">
                    <div className="h-full rounded-full bg-gridiron"
                      style={{ width: `${(s.avg_weekly / 160) * 100}%` }} />
                  </div>
                  <span className="stat w-28 text-right text-sm">{s.avg_weekly} avg · {s.high} high</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
