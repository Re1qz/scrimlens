import uuid
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from supabase import create_client, Client

from config import settings
from scraper import scrape
from discord import post_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
supabase: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

app = FastAPI(title="SCRIMLENS API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    url: str
    title: str = "スクリム結果"
    discord_notify: bool = False


class AnalyzeResponse(BaseModel):
    id: str
    status: str


class StatusResponse(BaseModel):
    id: str
    status: str
    title: str | None = None
    game_count: int | None = None
    error_message: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/scrims/analyze", response_model=AnalyzeResponse)
@limiter.limit("5/minute")
async def analyze(request: Request, body: AnalyzeRequest):
    if "docs.google.com/spreadsheets" not in body.url:
        raise HTTPException(400, detail="Google SheetsのURLを入力してください")

    scrim_id = str(uuid.uuid4())
    supabase.table("scrims").insert({
        "id": scrim_id,
        "url": body.url,
        "title": body.title,
        "status": "processing",
    }).execute()

    try:
        data = await scrape(body.url)

        team_id_map: dict[str, str] = {}
        for t in data.teams:
            row = supabase.table("teams").insert({
                "scrim_id": scrim_id,
                "name": t.name,
                "team_num": t.team_num,
                "total_kills": t.total_kills,
                "total_placement": t.total_placement_pts,
                "total_damage": t.total_damage,
                "total_points": t.total_points,
                "rank": t.rank,
            }).execute()
            team_id_map[t.name] = row.data[0]["id"]

        stats_rows = [
            {
                "scrim_id": scrim_id,
                "team_id": team_id_map.get(ps.team_name),
                "player_name": ps.player_name,
                "character": ps.character,
                "placement": ps.placement,
                "kills": ps.kills,
                "assists": ps.assists,
                "damage": ps.damage,
                "survival_time": ps.survival_time,
            }
            for ps in data.player_stats
        ]
        for i in range(0, len(stats_rows), 500):
            supabase.table("player_stats").insert(stats_rows[i:i+500]).execute()

        supabase.table("scrims").update({
            "status": "completed",
            "title": body.title,
            "game_count": data.game_count,
        }).eq("id", scrim_id).execute()

        logger.info(f"[{scrim_id}] 完了: {len(data.teams)}チーム / {data.game_count}ゲーム")

        if body.discord_notify and settings.discord_webhook_url:
            await post_results(settings.discord_webhook_url, data.teams, body.title)

        return AnalyzeResponse(id=scrim_id, status="completed")

    except Exception as e:
        logger.error(f"[{scrim_id}] エラー: {e}", exc_info=True)
        supabase.table("scrims").update({"status": "error", "error_message": str(e)[:500]}).eq("id", scrim_id).execute()
        raise HTTPException(500, detail=str(e)[:200])


@app.get("/api/scrims/{scrim_id}/status", response_model=StatusResponse)
def get_status(scrim_id: str):
    res = (
        supabase.table("scrims")
        .select("id,status,title,game_count,error_message")
        .eq("id", scrim_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        raise HTTPException(404, detail="Not found")
    return res.data


@app.get("/api/scrims/{scrim_id}/rankings")
def get_rankings(scrim_id: str):
    res = (
        supabase.table("scrims").select("id").eq("id", scrim_id).maybe_single().execute()
    )
    if not res.data:
        raise HTTPException(404, detail="Not found")
    res = (
        supabase.table("teams")
        .select("id,name,team_num,total_kills,total_placement,total_damage,total_points,rank")
        .eq("scrim_id", scrim_id)
        .order("rank")
        .execute()
    )
    return {"rankings": res.data}


@app.get("/api/scrims/{scrim_id}/games")
def get_games(scrim_id: str):
    res = (
        supabase.table("scrims").select("id").eq("id", scrim_id).maybe_single().execute()
    )
    if not res.data:
        raise HTTPException(404, detail="Not found")
    res = (
        supabase.table("player_stats")
        .select("*")
        .eq("scrim_id", scrim_id)
        .order("placement")
        .execute()
    )
    return {"player_stats": res.data}
