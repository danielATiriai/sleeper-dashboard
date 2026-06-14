import clsx from "clsx";
import { NavLink, Outlet, useParams } from "react-router-dom";
import { useAsync } from "../lib/useAsync";
import { getLeague } from "../lib/data";
import { ARCH_TONE } from "../lib/ui";
import { Loading, ErrorState, TeamAvatar } from "../components/ui";

const NAV = [
  { to: "/", label: "Overview", icon: "◎", end: true },
  { to: "/power", label: "Power Rankings", icon: "▲" },
  { to: "/history", label: "History & Trends", icon: "↺" },
  { to: "/trades", label: "Trades", icon: "⇄" },
  { to: "/draft", label: "Draft", icon: "✦" },
  { to: "/players", label: "Players", icon: "◍" },
];

export default function AppShell() {
  const { data: league, error, loading } = useAsync(getLeague, []);
  const { rid } = useParams();

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-ink-800 bg-ink-900/60 px-3 py-4 lg:flex">
        <div className="flex items-center gap-2.5 px-2 pb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl2 bg-gridiron/15 text-gridiron ring-1 ring-gridiron/30">
            <span className="text-lg">🏈</span>
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-bold text-chalk">{league?.league.name || "League"}</div>
            <div className="text-[11px] text-chalk-faint">
              {league ? `${league.seasons[0]}–${league.latest_season} · ${league.n_teams} teams` : "Dynasty"}
            </div>
          </div>
        </div>

        <nav className="flex flex-col gap-0.5">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => clsx("nav-link", isActive && "nav-link-active")}>
              <span aria-hidden className="w-4 text-center text-chalk-faint">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-5 px-2 text-[11px] font-semibold uppercase tracking-wider text-chalk-faint">Teams</div>
        <div className="mt-1 flex flex-1 flex-col gap-0.5 overflow-y-auto pr-1">
          {league?.teams.map((t) => {
            const tone = ARCH_TONE[t.archetype.tone] || ARCH_TONE.slate;
            return (
              <NavLink key={t.roster_id} to={`/team/${t.roster_id}`}
                className={({ isActive }) => clsx("nav-link !py-1.5",
                  (isActive || String(t.roster_id) === rid) && "nav-link-active")}>
                <TeamAvatar url={t.avatar_url} name={t.team_name} size={22} />
                <span className="min-w-0 flex-1 truncate">{t.team_name}</span>
                <span className={clsx("h-2 w-2 shrink-0 rounded-full", tone.bar)}
                  title={t.archetype.name} />
              </NavLink>
            );
          })}
        </div>
        <div className="px-2 pt-3 text-[10px] leading-relaxed text-chalk-faint">
          Data: Sleeper API · nflverse (CC-BY-4.0)
        </div>
      </aside>

      <main className="min-w-0">
        {/* mobile top bar */}
        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-ink-800 bg-ink-950/90 px-4 py-3 backdrop-blur lg:hidden">
          <span className="text-lg">🏈</span>
          <span className="font-bold">{league?.league.name || "League"}</span>
        </div>
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
          {loading && <Loading />}
          {error && <ErrorState error={error} />}
          {league && <Outlet context={league} />}
        </div>
      </main>
    </div>
  );
}
