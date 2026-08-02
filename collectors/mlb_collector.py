"""
mlb_collector.py
MLB Stats API(공식, 키 불필요)에서 오늘(또는 지정한 날짜)의 경기 일정 +
프로베이블 선발투수 피처를 가져와 SQLite에 저장한다.

사용법:
    python collectors/mlb_collector.py                # 오늘 날짜
    python collectors/mlb_collector.py --date 2026-07-27
    python collectors/mlb_collector.py --db sports.db --date 2026-07-27

필요 패키지:
    pip install requests

주의:
    이 샌드박스 환경은 네트워크 아웃바운드가 화이트리스트 방식이라
    statsapi.mlb.com 호출을 여기서 직접 테스트하지는 못했다.
    로직은 MLB Stats API 공개 문서/스키마 기준으로 작성했으니,
    실제 사용 시 집 컴퓨터(또는 네트워크 제한 없는 환경)에서 먼저
    `--date` 를 최근 실제 경기가 있었던 날짜로 지정해 한 번 돌려보고
    응답 필드가 예상과 다르면 parse 함수들을 조정하면 된다.
"""

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

# db 모듈 import (프로젝트 루트 기준 실행을 가정: python collectors/mlb_collector.py)
sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_connection, init_db, upsert_team, upsert_game, upsert_probable_pitcher

BASE_URL = "https://statsapi.mlb.com/api/v1"
LEAGUE = "MLB"
SPORT_ID = 1  # MLB
REQUEST_TIMEOUT = 15
RETRY = 3
RETRY_BACKOFF_SEC = 2


def _get(path: str, params: Optional[dict] = None) -> dict:
    """공용 GET 요청 (간단한 재시도 포함)."""
    url = f"{BASE_URL}{path}"
    last_err = None
    for attempt in range(1, RETRY + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            last_err = e
            print(f"[warn] 요청 실패 ({attempt}/{RETRY}): {url} params={params} -> {e}")
            time.sleep(RETRY_BACKOFF_SEC * attempt)
    raise RuntimeError(f"MLB API 요청 최종 실패: {url} params={params}") from last_err


def fetch_schedule(target_date: str) -> dict:
    """
    오늘(또는 지정 날짜)의 MLB 일정을 프로베이블 투수/라인스코어/시리즈 상태와 함께 가져온다.
    hydrate 파라미터로 필요한 필드를 한 번에 확장 조회.
    """
    return _get(
        "/schedule",
        params={
            "sportId": SPORT_ID,
            "date": target_date,
            "hydrate": "team,linescore,probablePitcher,seriesStatus,venue",
        },
    )


def fetch_pitcher_game_log(pitcher_id: int, season: int) -> list[dict]:
    """
    선발투수의 시즌 경기별(pitching gameLog) 기록을 가져온다.
    최근 등판 3~5경기 ERA/WHIP, 등판 간격(days_rest) 계산에 사용.
    """
    data = _get(
        f"/people/{pitcher_id}/stats",
        params={"stats": "gameLog", "group": "pitching", "season": season},
    )
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError):
        return []
    # 날짜 오름차순으로 정렬되어 오지 않을 수 있으니 date 기준 정렬
    splits.sort(key=lambda s: s.get("date", ""))
    return splits


def fetch_pitcher_season_stats(pitcher_id: int, season: int) -> dict:
    """선발투수 시즌 통산 ERA/WHIP."""
    data = _get(
        f"/people/{pitcher_id}/stats",
        params={"stats": "season", "group": "pitching", "season": season},
    )
    try:
        stat = data["stats"][0]["splits"][0]["stat"]
        return {
            "era_season": float(stat.get("era")) if stat.get("era") not in (None, "-.--") else None,
            "whip_season": float(stat.get("whip")) if stat.get("whip") not in (None, "-.--") else None,
        }
    except (KeyError, IndexError, ValueError):
        return {"era_season": None, "whip_season": None}


def compute_recent_pitcher_features(pitcher_id: int, season: int, n_last: int = 5) -> dict:
    """
    최근 n_last경기(선발 등판) 기준 ERA/WHIP 근사치와, 마지막 등판일로부터의
    휴식일수(days_rest, target_date 기준은 호출부에서 별도 계산)를 반환.

    MLB gameLog는 등판별 세부 스탯(이닝, 자책점, 피안타, 사사구 등)을 담고 있어
    이를 합산해 근사 ERA/WHIP을 계산한다 (완전한 공식 누적 스탯 API가 최근 N경기만
    잘라주지는 않기 때문).
    """
    splits = fetch_pitcher_game_log(pitcher_id, season)
    starts = [s for s in splits if s.get("stat", {}).get("gamesStarted", 0) in (1, "1")]
    recent = starts[-n_last:] if starts else []

    if not recent:
        return {"era_last5": None, "whip_last5": None, "last_appearance_date": None}

    total_er = 0.0
    total_ip = 0.0
    total_bb = 0.0
    total_h = 0.0

    for s in recent:
        stat = s.get("stat", {})
        total_er += float(stat.get("earnedRuns", 0) or 0)
        # inningsPitched는 "6.1" 같은 문자열(1/3이닝 표기) 형식이라 변환 필요
        ip_raw = stat.get("inningsPitched", "0.0")
        total_ip += _parse_innings_pitched(ip_raw)
        total_bb += float(stat.get("baseOnBalls", 0) or 0)
        total_h += float(stat.get("hits", 0) or 0)

    era_last5 = round((total_er * 9) / total_ip, 2) if total_ip > 0 else None
    whip_last5 = round((total_bb + total_h) / total_ip, 2) if total_ip > 0 else None
    last_appearance_date = recent[-1].get("date")

    return {
        "era_last5": era_last5,
        "whip_last5": whip_last5,
        "last_appearance_date": last_appearance_date,
    }


def _parse_innings_pitched(ip_str: str) -> float:
    """MLB 표기법 '6.1' -> 6 + 1/3이닝(=6.333...) 변환. '6.2' -> 6 + 2/3."""
    try:
        whole, _, frac = str(ip_str).partition(".")
        whole_f = float(whole) if whole else 0.0
        frac_map = {"0": 0.0, "1": 1 / 3, "2": 2 / 3}
        return whole_f + frac_map.get(frac, 0.0)
    except (ValueError, TypeError):
        return 0.0


def _days_rest(target_date: str, last_appearance_date: Optional[str]) -> Optional[int]:
    if not last_appearance_date:
        return None
    try:
        d1 = datetime.strptime(target_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(last_appearance_date, "%Y-%m-%d").date()
        return (d1 - d2).days
    except ValueError:
        return None


def collect_and_store(target_date: str, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    schedule = fetch_schedule(target_date)
    season = int(target_date[:4])

    dates = schedule.get("dates", [])
    if not dates:
        print(f"[info] {target_date} 에 예정된 MLB 경기가 없습니다.")
        return

    games = dates[0].get("games", [])
    print(f"[info] {target_date} MLB 경기 {len(games)}건 발견")

    for g in games:
        game_id = str(g["gamePk"])
        status = g.get("status", {}).get("detailedState", "")
        venue_name = g.get("venue", {}).get("name")
        game_datetime_utc = g.get("gameDate")  # ISO8601 UTC

        home = g["teams"]["home"]
        away = g["teams"]["away"]
        home_team = home["team"]
        away_team = away["team"]

        # 팀 upsert
        upsert_team(
            conn,
            team_id=str(home_team["id"]),
            league=LEAGUE,
            name=home_team.get("name"),
            abbreviation=home_team.get("abbreviation"),
        )
        upsert_team(
            conn,
            team_id=str(away_team["id"]),
            league=LEAGUE,
            name=away_team.get("name"),
            abbreviation=away_team.get("abbreviation"),
        )

        # 시리즈 상황
        series_status = g.get("seriesStatus", {})
        series_game_no = series_status.get("gameNumberOfSeries")
        # seriesStatus는 홈/원정 구분이 명확치 않은 경우가 있어 result/shortName 텍스트를 그대로 보관
        series_record_before = series_status.get("result") or series_status.get("shortName")

        upsert_game(
            conn,
            game_id=game_id,
            league=LEAGUE,
            date=target_date,
            home_team_id=str(home_team["id"]),
            away_team_id=str(away_team["id"]),
            home_score=home.get("score"),
            away_score=away.get("score"),
            venue_name=venue_name,
            series_game_no=series_game_no,
            series_record_before=series_record_before,
            status=status,
            game_datetime_utc=game_datetime_utc,
        )

        # 프로베이블 선발투수 (아직 발표 전이면 없을 수 있음)
        for side, side_data in (("home", home), ("away", away)):
            prob_pitcher = side_data.get("probablePitcher")
            if not prob_pitcher:
                continue

            pitcher_id = prob_pitcher["id"]
            pitcher_name = prob_pitcher.get("fullName")

            season_stats = fetch_pitcher_season_stats(pitcher_id, season)
            recent = compute_recent_pitcher_features(pitcher_id, season, n_last=5)
            days_rest = _days_rest(target_date, recent.get("last_appearance_date"))

            team_id = str(side_data["team"]["id"])
            upsert_probable_pitcher(
                conn,
                game_id=game_id,
                team_id=team_id,
                side=side,
                pitcher_id=str(pitcher_id),
                pitcher_name=pitcher_name,
                era_last5=recent.get("era_last5"),
                whip_last5=recent.get("whip_last5"),
                days_rest=days_rest,
                era_season=season_stats.get("era_season"),
                whip_season=season_stats.get("whip_season"),
            )
            print(f"  - {side}: {pitcher_name} (ERA5={recent.get('era_last5')}, WHIP5={recent.get('whip_last5')}, rest={days_rest})")

        print(f"[ok] game_id={game_id} {away_team.get('name')} @ {home_team.get('name')} 저장 완료")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="MLB 오늘 경기 + 프로베이블 투수 수집기")
    parser.add_argument(
        "--date",
        default=date.today().strftime("%Y-%m-%d"),
        help="YYYY-MM-DD 형식 (기본값: 오늘)",
    )
    parser.add_argument(
        "--db",
        default="sports.db",
        help="SQLite DB 파일 경로 (기본값: ./sports.db)",
    )
    args = parser.parse_args()

    collect_and_store(args.date, args.db)


if __name__ == "__main__":
    main()
