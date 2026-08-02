"""
run_predictions.py
지정한 날짜의 games 테이블에 있는 모든 경기에 대해
feature_builder로 피처를 만들고 predictor_v1으로 예측한 뒤
predictions 테이블에 저장한다.

collector들을 먼저 돌려서 games/team_season_stats/probable_pitchers가
채워진 다음에 실행하는 게 정상적인 순서.

사용법:
    python run_predictions.py --date 2026-07-29 --season 2026
"""

import argparse
import sqlite3
from datetime import date

from db.db import get_connection, init_db, upsert_prediction
from features.feature_builder import build_features
from model.predictor_v1 import predict

LEAGUES = ("MLB", "KBO", "NPB")


def run(target_date: str, season: int, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    rows = conn.execute(
        "SELECT game_id, league FROM games WHERE date = ? AND league IN (?,?,?)",
        (target_date, *LEAGUES),
    ).fetchall()

    if not rows:
        print(f"[info] {target_date} games 테이블에 데이터가 없습니다. collector를 먼저 실행하세요.")
        return

    for row in rows:
        game_id = row["game_id"]
        try:
            features = build_features(conn, game_id, season)
            pred = predict(features)
            upsert_prediction(conn, **pred)
            print(f"[ok] [{row['league']}] game_id={game_id} 예측 저장 완료 (등급={pred['tier']})")
        except Exception as e:
            print(f"[warn] [{row['league']}] game_id={game_id} 예측 실패: {e}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="경기별 예측 계산 실행기")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"), help="YYYY-MM-DD (기본값: 오늘)")
    parser.add_argument("--season", type=int, default=date.today().year, help="기본값: 올해")
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    run(args.date, args.season, args.db)


if __name__ == "__main__":
    main()
