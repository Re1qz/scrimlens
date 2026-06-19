"use client";
import type { TeamRanking } from "@/lib/api";

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

export default function RankingTable({ rankings }: { rankings: TeamRanking[] }) {
  const maxPts = rankings[0]?.total_points ?? 1;

  return (
    <div className="overflow-x-auto rounded-xl border border-apex-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-apex-card text-gray-400 text-left text-xs uppercase tracking-wider">
            <th className="px-4 py-3 w-10">#</th>
            <th className="px-4 py-3">チーム</th>
            <th className="px-4 py-3 text-right">Kill</th>
            <th className="px-4 py-3 text-right hidden sm:table-cell">Damage</th>
            <th className="px-4 py-3 text-right">Pts</th>
            <th className="px-4 py-3 w-32 hidden md:table-cell">バー</th>
          </tr>
        </thead>
        <tbody>
          {rankings.map((t, idx) => {
            const pct = maxPts > 0 ? Math.round((t.total_points / maxPts) * 100) : 0;
            const isTop3 = t.rank <= 3;
            return (
              <tr
                key={t.id}
                className={`border-t border-apex-border transition-colors ${
                  isTop3 ? "bg-apex-card/40" : "hover:bg-apex-card/30"
                }`}
              >
                <td className="px-4 py-3 text-center font-mono">
                  {MEDAL[t.rank] ?? (
                    <span className="text-gray-500 text-xs">{t.rank}</span>
                  )}
                </td>
                <td className="px-4 py-3 font-semibold">
                  <span className={isTop3 ? "text-white" : "text-gray-200"}>{t.name}</span>
                </td>
                <td className="px-4 py-3 text-right text-gray-300 font-mono">{t.total_kills}</td>
                <td className="px-4 py-3 text-right text-gray-400 font-mono hidden sm:table-cell">
                  {t.total_damage.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right font-bold font-mono">
                  <span className={isTop3 ? "text-apex-orange" : "text-gray-200"}>
                    {t.total_points}
                  </span>
                </td>
                <td className="px-4 py-3 hidden md:table-cell">
                  <div className="h-1.5 bg-apex-border rounded-full overflow-hidden">
                    <div
                      className="h-full bg-apex-orange rounded-full transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
