// Static-bundle loaders. Each JSON file is fetched once and memoized.
import type {
  DraftBundle, LeagueBundle, PlayersBundle, Team, TradesBundle, TrendsBundle,
} from "../types";

const BASE = import.meta.env.BASE_URL || "/";
const cache = new Map<string, Promise<unknown>>();

function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(`${BASE}data/${path}`).then((r) => {
        if (!r.ok) throw new Error(`Failed to load ${path} (${r.status})`);
        return r.json();
      })
    );
  }
  return cache.get(path) as Promise<T>;
}

export const getLeague = () => load<LeagueBundle>("league.json");
export const getTeam = (rid: number | string) => load<Team>(`teams/${rid}.json`);
export const getPlayers = () => load<PlayersBundle>("players.json");
export const getTrades = () => load<TradesBundle>("trades.json");
export const getDraft = () => load<DraftBundle>("draft.json");
export const getTrends = () => load<TrendsBundle>("trends.json");
