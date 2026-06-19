"use client";
import { useState, useEffect, useRef } from "react";
import { analyze, getStatus, getRankings, type TeamRanking, type StatusResponse } from "@/lib/api";
import RankingTable from "@/components/RankingTable";

type Phase = "idle" | "loading" | "polling" | "done" | "error";

// 指数バックオフ: 2s, 3s, 5s, 8s, 13s ... 最大15s
const backoff = (n: number) => Math.min(2000 * Math.pow(1.5, n), 15000);
const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5分

export default function Home() {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [discordNotify, setDiscordNotify] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [statusInfo, setStatusInfo] = useState<StatusResponse | null>(null);
  const [rankings, setRankings] = useState<TeamRanking[]>([]);
  const [errorMsg, setErrorMsg] = useState("");

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedAt = useRef<number>(0);
  const pollCount = useRef(0);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  async function poll(id: string) {
    if (Date.now() - startedAt.current > POLL_TIMEOUT_MS) {
      setPhase("error");
      setErrorMsg("タイムアウト：5分以上経過しました。もう一度試してください。");
      return;
    }
    try {
      const status = await getStatus(id);
      setStatusInfo(status);
      if (status.status === "completed") {
        const data = await getRankings(id);
        setRankings(data);
        setPhase("done");
      } else if (status.status === "error") {
        setPhase("error");
        setErrorMsg(status.error_message ?? "不明なエラーが発生しました");
      } else {
        const delay = backoff(pollCount.current++);
        pollRef.current = setTimeout(() => poll(id), delay);
      }
    } catch {
      const delay = backoff(pollCount.current++);
      pollRef.current = setTimeout(() => poll(id), delay);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    if (pollRef.current) clearTimeout(pollRef.current);

    setPhase("loading");
    setErrorMsg("");
    setRankings([]);
    setStatusInfo(null);
    pollCount.current = 0;
    startedAt.current = Date.now();

    try {
      const res = await analyze(url.trim(), title.trim() || "スクリム結果", discordNotify);
      setPhase("polling");
      poll(res.id);
    } catch (err: unknown) {
      setPhase("error");
      setErrorMsg(err instanceof Error ? err.message : "エラーが発生しました");
    }
  }

  function reset() {
    if (pollRef.current) clearTimeout(pollRef.current);
    setPhase("idle");
    setUrl("");
    setTitle("");
    setRankings([]);
    setErrorMsg("");
    setStatusInfo(null);
  }

  const isProcessing = phase === "loading" || phase === "polling";

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 min-h-screen">
      {/* Header */}
      <header className="mb-10 text-center">
        <h1 className="text-5xl font-black tracking-tight mb-1">
          <span className="text-apex-orange">SCRIM</span>
          <span className="text-white">LENS</span>
        </h1>
        <p className="text-gray-500 text-sm">
          ESCL スクリム結果URLを貼るだけで自動集計
        </p>
      </header>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-3 mb-8">
        <div>
          <label className="block text-xs text-gray-500 mb-1.5 font-medium">
            Google Sheets URL
          </label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://docs.google.com/spreadsheets/d/..."
            className="w-full bg-apex-card border border-apex-border rounded-lg px-4 py-3 text-sm
                       focus:outline-none focus:border-apex-orange focus:ring-1 focus:ring-apex-orange/30
                       transition-all placeholder-gray-700 disabled:opacity-50"
            disabled={isProcessing}
            required
          />
        </div>

        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1.5 font-medium">
              タイトル <span className="text-gray-700">（任意）</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例: ESCL CL Scrims #276"
              className="w-full bg-apex-card border border-apex-border rounded-lg px-4 py-3 text-sm
                         focus:outline-none focus:border-apex-orange transition-all
                         placeholder-gray-700 disabled:opacity-50"
              disabled={isProcessing}
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer select-none pb-3">
            <input
              type="checkbox"
              checked={discordNotify}
              onChange={(e) => setDiscordNotify(e.target.checked)}
              className="accent-apex-orange w-4 h-4 cursor-pointer"
              disabled={isProcessing}
            />
            <span className="text-sm text-gray-400">Discord</span>
          </label>
        </div>

        <button
          type="submit"
          disabled={isProcessing || !url.trim()}
          className="w-full bg-apex-orange hover:bg-orange-500 active:bg-orange-700
                     disabled:opacity-40 disabled:cursor-not-allowed
                     text-white font-bold py-3 rounded-lg transition-colors text-sm tracking-wide"
        >
          {phase === "loading" ? "送信中..." : phase === "polling" ? "集計中..." : "集計する"}
        </button>
      </form>

      {/* Loading state */}
      {isProcessing && (
        <div className="text-center py-16">
          <div className="inline-block w-10 h-10 border-[3px] border-apex-orange border-t-transparent
                          rounded-full animate-spin mb-5" />
          <p className="text-gray-400 text-sm">
            {statusInfo?.status === "processing"
              ? "データ取得・集計中..."
              : "リクエスト送信中..."}
          </p>
          {statusInfo?.game_count != null && (
            <p className="text-gray-600 text-xs mt-1">
              {statusInfo.game_count} ゲーム検出
            </p>
          )}
        </div>
      )}

      {/* Error */}
      {phase === "error" && (
        <div className="rounded-xl border border-red-900 bg-red-950/40 p-5">
          <p className="font-bold text-red-400 mb-1 text-sm">エラー</p>
          <p className="text-red-300 text-sm leading-relaxed">{errorMsg}</p>
          <button
            onClick={reset}
            className="mt-4 text-xs text-gray-500 hover:text-white underline transition-colors"
          >
            もう一度試す
          </button>
        </div>
      )}

      {/* Results */}
      {phase === "done" && rankings.length > 0 && (
        <section>
          <div className="flex items-start justify-between mb-4 gap-2">
            <div>
              <h2 className="font-bold text-lg text-white leading-tight">
                {(statusInfo?.title ?? title) || "スクリム結果"}
              </h2>
              <p className="text-gray-600 text-xs mt-0.5">
                {rankings.length}チーム
                {statusInfo?.game_count ? ` · ${statusInfo.game_count}ゲーム` : ""}
              </p>
            </div>
            <button
              onClick={reset}
              className="shrink-0 text-xs text-gray-600 hover:text-white border border-apex-border
                         hover:border-gray-500 px-3 py-1.5 rounded-lg transition-all"
            >
              リセット
            </button>
          </div>
          <RankingTable rankings={rankings} />
        </section>
      )}
    </main>
  );
}
