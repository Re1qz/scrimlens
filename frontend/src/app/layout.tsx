import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SCRIMLENS",
  description: "ESCL Apex Legends スクリム結果自動集計",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-apex-dark text-white">{children}</body>
    </html>
  );
}
