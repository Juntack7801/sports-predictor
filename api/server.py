"""
server.py
GET /api/today?league=MLB&date=YYYY-MM-DD
  -> 해당 날짜/리그의 경기 + 팀명 + 예측 결과(승리확률/오버언더/등급)를 JSON으로 반환

실행:
    cd sports-predictor
    python api/server.py
    # 기본적으로 http://localhost:8000 에서 뜸
    # 브라우저에서 http://localhost:8000/api/today?league=MLB 로 확인 가능
"""

import sys
import traceback
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_connection, init_db
from collectors.team_name_map import get_display_kr_name, get_display_kr_name_short

DB_PATH = str(Path(__file__).parent.parent / "sports.db")

app = FastAPI(title="sports-predictor API")

# 프론트엔드(web/)를 다른 포트나 file://로 열어도 호출 가능하게 CORS 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/today")
def get_today(
    league: str = Query(default="MLB"),
    target_date: str = Query(default=None, alias="date"),
):
    target_date = target_date or date.today().strftime("%Y-%m-%d")

    try:
        conn = get_connection(DB_PATH)
        # 옛날에 만들어진 sports.db에 새로 추가된 컬럼이 없을 수 있어서
        # 요청마다 안전하게 마이그레이션을 한 번 더 확인한다 (있으면 그냥 넘어감).
        init_db(conn)

        rows = conn.execute(
            """
            SELECT
                g.game_id, g.date, g.venue_name, g.series_game_no, g.status,
                g.home_score, g.away_score, g.game_datetime_utc,
                ht.name AS home_name, at_.name AS away_name,
                p.win_prob_home, p.win_prob_away, p.ou_line, p.ou_line_source,
                p.over_prob, p.under_prob, p.tier, p.model_version, p.created_at AS predicted_at,
                hp.pitcher_name AS home_pitcher, hp.era_season AS home_pitcher_era,
                ap.pitcher_name AS away_pitcher, ap.era_season AS away_pitcher_era,
                hts.win_pct AS home_win_pct, hts.last10_win_pct AS home_last10_win_pct,
                ats.win_pct AS away_win_pct, ats.last10_win_pct AS away_last10_win_pct,
                al.predicted_winner, al.actual_winner, al.winner_correct,
                al.predicted_ou, al.actual_total, al.ou_correct, al.analysis_note
            FROM games g
            JOIN teams ht ON ht.team_id = g.home_team_id
            JOIN teams at_ ON at_.team_id = g.away_team_id
            LEFT JOIN predictions p ON p.game_id = g.game_id
            LEFT JOIN probable_pitchers hp ON hp.game_id = g.game_id AND hp.side = 'home'
            LEFT JOIN probable_pitchers ap ON ap.game_id = g.game_id AND ap.side = 'away'
            LEFT JOIN team_season_stats hts ON hts.team_id = g.home_team_id
                AND hts.season = CAST(strftime('%Y', g.date) AS INTEGER)
            LEFT JOIN team_season_stats ats ON ats.team_id = g.away_team_id
                AND ats.season = CAST(strftime('%Y', g.date) AS INTEGER)
            LEFT JOIN accuracy_log al ON al.game_id = g.game_id
            WHERE g.date = ? AND g.league = ?
            ORDER BY g.game_datetime_utc ASC, g.game_id ASC
            """,
            (target_date, league),
        ).fetchall()
        conn.close()

        games = []
        for r in rows:
            g = dict(r)
            g["home_name_kr"] = get_display_kr_name(league, g["home_name"])
            g["away_name_kr"] = get_display_kr_name(league, g["away_name"])
            g["home_name_short"] = get_display_kr_name_short(league, g["home_name"])
            g["away_name_short"] = get_display_kr_name_short(league, g["away_name"])
            games.append(g)

        return {"date": target_date, "league": league, "count": len(games), "games": games, "error": None}

    except Exception as e:
        # 여기서 죽지 않고 항상 유효한 JSON을 돌려준다.
        # "서버가 꺼졌나요?" 같은 오해를 막기 위해 실제 오류 내용을 그대로 담아 보낸다.
        traceback.print_exc()
        return JSONResponse(
            status_code=200,
            content={
                "date": target_date,
                "league": league,
                "count": 0,
                "games": [],
                "error": f"{type(e).__name__}: {e}",
            },
        )


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
