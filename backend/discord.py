"""Discord Webhookへの結果投稿"""
import httpx
from scraper import TeamSummary


def build_embed(teams: list[TeamSummary], title: str = "スクリム結果") -> dict:
    top10 = teams[:10]
    rows = []
    for t in top10:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(t.rank, f"`{t.rank:2d}`")
        rows.append(f"{medal} **{t.name}** — {t.total_points}pt (K:{t.total_kills} D:{t.total_damage})")
    return {
        "title": f"📊 {title}",
        "description": "\n".join(rows),
        "color": 0xE8630A,
        "footer": {"text": "SCRIMLENS by ESCL"},
    }


async def post_results(webhook_url: str, teams: list[TeamSummary], title: str = "スクリム結果") -> None:
    if not webhook_url:
        return
    embed = build_embed(teams, title)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json={"embeds": [embed]})
        resp.raise_for_status()
