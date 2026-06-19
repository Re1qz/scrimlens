import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SCRIMLENS API 起動")
    yield
    logger.info("SCRIMLENS API 終了")


app = FastAPI(title="SCRIMLENS API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- Models ----------

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


# ---------- Background task ----------

async def process_scrim(scrim_id: str, url: str, title: str, discord_notify: bool) -> None:
    logger.info(f"[{scrim_id}] 処理開始: {url}")
    try:
        _update_status(scrim_id, "processing")
        data = await scrape(url)

        # チームを保存してIDマップを作る
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

        # プレイヤー統計を一括保存（最大500件ずつ）
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
            "title": title,
            "game_count": data.game_count,
        }).eq("id", scrim_id).execute()

        logger.info(f"[{scrim_id}] 完了: {len(data.teams)}チーム / {data.game_count}ゲーム")

        if discord_notify and settings.discord_webhook_url:
            await post_results(settings.discord_webhook_url, data.teams, title)

    except Exception as e:
        logger.error(f"[{scrim_id}] エラー: {e}", exc_info=True)
        _update_status(scrim_id, "error", error_message=str(e)[:500])


def _update_status(scrim_id: str, status: str, **kwargs) -> None:
    supabase.table("scrims").update({"status": status, **kwargs}).eq("id", scrim_id).execute()


# ---------- Endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/scrims/analyze", response_model=AnalyzeResponse)
@limiter.limit("5/minute")
async def analyze(request: Request, body: AnalyzeRequest, background_tasks: BackgroundTasks):
    if "docs.google.com/spreadsheets" not in body.url:
        raise HTTPException(400, detail="Google SheetsのURLを入力してください")

    scrim_id = str(uuid.uuid4())
    supabase.table("scrims").insert({
        "id": scrim_id,
        "url": body.url,
        "title": body.title,
        "status": "pending",
    }).execute()

    background_tasks.add_task(process_scrim, scrim_id, body.url, body.title, body.discord_notify)
    logger.info(f"[{scrim_id}] キュー追加: {body.url}")

    return AnalyzeResponse(id=scrim_id, status="pending")


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
    _assert_exists(scrim_id)
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
    _assert_exists(scrim_id)
    res = (
        supabase.table("player_stats")
        .select("*")
        .eq("scrim_id", scrim_id)
        .order("placement")
        .execute()
    )
    return {"player_stats": res.data}


def _assert_exists(scrim_id: str) -> None:
    res = supabase.table("scrims").select("id").eq("id", scrim_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, detail="Not found")
