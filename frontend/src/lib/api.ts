const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AnalyzeResponse {
  id: string;
  status: string;
}

export interface StatusResponse {
  id: string;
  status: "pending" | "processing" | "completed" | "error";
  title?: string;
  game_count?: number;
  error_message?: string;
}

export interface TeamRanking {
  id: string;
  name: string;
  team_num: number;
  total_kills: number;
  total_placement: number;
  total_damage: number;
  total_points: number;
  rank: number;
}

export interface PlayerStat {
  id: string;
  team_id: string;
  player_name: string;
  character: string;
  placement: number;
  kills: number;
  assists: number;
  damage: number;
  survival_time: string;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function analyze(url: string, title: string, discordNotify: boolean) {
  return apiFetch<AnalyzeResponse>("/api/scrims/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, title, discord_notify: discordNotify }),
  });
}

export function getStatus(id: string) {
  return apiFetch<StatusResponse>(`/api/scrims/${id}/status`);
}

export async function getRankings(id: string): Promise<TeamRanking[]> {
  const data = await apiFetch<{ rankings: TeamRanking[] }>(`/api/scrims/${id}/rankings`);
  return data.rankings;
}

export async function getPlayerStats(id: string): Promise<PlayerStat[]> {
  const data = await apiFetch<{ player_stats: PlayerStat[] }>(`/api/scrims/${id}/games`);
  return data.player_stats;
}
