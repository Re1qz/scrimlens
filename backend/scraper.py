"""
Google SheetsのCSVを全シート取得してパースする。
ESCLは1スクリムセッション = 複数ゲーム（シート）構成。
"""
import re
import io
import csv
import json
import logging
from dataclasses import dataclass, field
from collections import defaultdict

import httpx

logger = logging.getLogger(__name__)

EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
GVIZ_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:json"

# ESCLの順位ポイント（1ゲームあたり）
PLACEMENT_POINTS = {1: 12, 2: 9, 3: 7, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}


@dataclass
class PlayerStat:
    player_name: str
    character: str
    placement: int
    kills: int
    assists: int
    damage: int
    survival_time: str
    team_name: str
    team_num: int
    game_num: int


@dataclass
class TeamSummary:
    name: str
    team_num: int
    total_kills: int = 0
    total_placement_pts: int = 0
    total_damage: int = 0
    total_points: int = 0
    rank: int = 0
    games_played: int = 0


@dataclass
class ScrimData:
    player_stats: list[PlayerStat] = field(default_factory=list)
    teams: list[TeamSummary] = field(default_factory=list)
    game_count: int = 0
    title: str = ""


def extract_sheet_id(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        raise ValueError(f"Google SheetsのURLが無効です: {url}")
    return m.group(1)


def extract_gid(url: str) -> str | None:
    m = re.search(r"[?&#]gid=(\d+)", url)
    return m.group(1) if m else None


async def fetch_all_sheet_gids(sheet_id: str) -> list[tuple[int, str]]:
    """全シートの(gid, name)リストを返す。失敗したら[(0, 'Sheet1')]を返す。"""
    gviz_url = GVIZ_URL.format(sheet_id=sheet_id)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            resp = await client.get(gviz_url)
            resp.raise_for_status()
            # レスポンスは `/*O_o*/\ngoogle.visualization.Query.setResponse({...});` 形式
            text = resp.text
            m = re.search(r"google\.visualization\.Query\.setResponse\((.*)\);?\s*$", text, re.DOTALL)
            if not m:
                return [(0, "Game1")]
            data = json.loads(m.group(1))
            sheets = []
            for s in data.get("table", {}).get("cols", []):
                pass  # colsにはシート情報はない
            # sheetsはsig/versionに入っていないので別の方法で取得
            # gvizのJSONにはシート情報が入らないので、HTMLから取得する
    except Exception as e:
        logger.warning(f"シート一覧の取得失敗: {e}")

    return await _fetch_sheet_ids_from_html(sheet_id)


async def _fetch_sheet_ids_from_html(sheet_id: str) -> list[tuple[int, str]]:
    """スプレッドシートのHTMLからシートIDを抽出する。"""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            html = resp.text
        # "gid":NNNN,"name":"SheetName" 形式を探す
        matches = re.findall(r'"sheetId":(\d+),"title":"([^"]+)"', html)
        if matches:
            return [(int(gid), name) for gid, name in matches]
        # 別のフォーマット
        matches = re.findall(r'\["([^"]+)",null,(\d+)\]', html)
        if matches:
            return [(int(gid), name) for name, gid in matches if gid.isdigit()]
    except Exception as e:
        logger.warning(f"HTMLからシートID取得失敗: {e}")
    return [(0, "Game1")]


async def fetch_csv(sheet_id: str, gid: str | int) -> str:
    url = EXPORT_URL.format(sheet_id=sheet_id, gid=gid)
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def parse_game_csv(csv_text: str, game_num: int) -> list[PlayerStat]:
    """1ゲーム分のCSVをパースしてPlayerStatのリストを返す。"""
    reader = csv.DictReader(io.StringIO(csv_text))
    stats = []
    for row in reader:
        team = row.get("Team", "").strip()
        player = row.get("Player", "").strip()
        if not team or not player or team == "Team":
            continue
        try:
            stats.append(PlayerStat(
                player_name=player,
                character=row.get("Character", "").strip(),
                placement=_int(row.get("Placement")),
                kills=_int(row.get("Kills")),
                assists=_int(row.get("Assists")),
                damage=_int(row.get("Damage")),
                survival_time=row.get("Surv. Time", "").strip(),
                team_name=team,
                team_num=_int(row.get("Team Num")),
                game_num=game_num,
            ))
        except Exception as e:
            logger.debug(f"行スキップ: {e}, row={row}")
    return stats


def _int(val: str | None) -> int:
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return 0


def aggregate_teams(all_stats: list[PlayerStat]) -> list[TeamSummary]:
    """全ゲームのプレイヤー統計からチーム集計を行う。"""
    teams: dict[str, TeamSummary] = {}

    for ps in all_stats:
        key = ps.team_name
        if key not in teams:
            teams[key] = TeamSummary(name=ps.team_name, team_num=ps.team_num)
        t = teams[key]
        t.total_kills += ps.kills
        t.total_damage += ps.damage

    # ゲームごとにplacementポイントを集計（チーム内3人は同じplacementなので1人分だけ）
    # game_num × team_name でユニークなplacementを取得
    game_placements: dict[tuple[int, str], int] = {}
    for ps in all_stats:
        key = (ps.game_num, ps.team_name)
        if key not in game_placements and ps.placement > 0:
            game_placements[key] = ps.placement

    for (game_num, team_name), placement in game_placements.items():
        if team_name in teams:
            teams[team_name].total_placement_pts += PLACEMENT_POINTS.get(placement, 0)
            teams[team_name].games_played += 1

    for t in teams.values():
        t.total_points = t.total_kills + t.total_placement_pts

    sorted_teams = sorted(teams.values(), key=lambda t: (-t.total_points, -t.total_kills))
    for i, t in enumerate(sorted_teams, 1):
        t.rank = i
    return sorted_teams


async def scrape(url: str) -> ScrimData:
    sheet_id = extract_sheet_id(url)
    specified_gid = extract_gid(url)

    if specified_gid:
        # URLにgidが指定されている場合は単一シート
        sheets = [(int(specified_gid), "Game1")]
    else:
        # 全シートを取得
        sheets = await fetch_all_sheet_gids(sheet_id)
        logger.info(f"検出シート数: {len(sheets)} — {[name for _, name in sheets]}")

    all_stats: list[PlayerStat] = []
    valid_games = 0

    for game_num, sheet_name in sheets:
        try:
            csv_text = await fetch_csv(sheet_id, game_num)
            stats = parse_game_csv(csv_text, game_num=valid_games + 1)
            if stats:
                all_stats.extend(stats)
                valid_games += 1
                logger.info(f"ゲーム{valid_games}({sheet_name}): {len(stats)}行取得")
        except Exception as e:
            logger.warning(f"シート{game_num}({sheet_name})の取得失敗: {e}")

    if not all_stats:
        raise ValueError(
            "データが取得できませんでした。"
            "シートが公開されているか、URLが正しいか確認してください。"
        )

    teams = aggregate_teams(all_stats)
    return ScrimData(player_stats=all_stats, teams=teams, game_count=valid_games)
