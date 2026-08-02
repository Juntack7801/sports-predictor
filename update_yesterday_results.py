"""
update_yesterday_results.py
"어제" 탭에 아무 것도 안 뜨는 가장 흔한 이유는, 애초에 그 앱을 어제는 쓰지 않아서
어제 경기/예측 자체가 DB에 없기 때문이다. 이 스크립트는:
  1) 각 리그 collector를 "어제 날짜"로 다시 돌려서 경기 목록 + 최종 스코어를 채우고
     (이미 있으면 최종 스코어로 갱신, 없으면 새로 만듦)
  2) 그 경기들에 대해 예측이 아직 없으면 예측도 계산해서 채운다
     (주의: 이 경우 "그날의" 팀 컨디션이 아니라 "오늘 기준" 팀 성적으로 계산되므로
      완벽한 사후예측은 아니지만, 처음 쓰는 날 어제 탭이 비어 보이는 것보다는 낫다)
  3) 이미 예측이 있던 경기(이 앱을 계속 써온 경우)는 예측을 다시 계산하지 않는다
     — "그때 그 예측이 맞았는지"를 확인하는 게 목적이므로 나중에 덮어쓰면 안 됨.

daily_refresh.bat에서 자동으로 실행된다. 수동 실행도 가능:
    python update_yesterday_results.py
    python update_yesterday_results.py --date 2026-08-01
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from collectors import mlb_collector
from collectors import kbo_collector
from db.db import get_connection, init_db
from features.feature_builder import build_features
from model.predictor_v1 import predict
from db.db import upsert_prediction

try:
    from collectors import npb_collector
    HAS_NPB = True
except ImportError:
    HAS_NPB = False


def fill_missing_predictions(target_date: str, season: int, db_path: str) -> None:
    """target_date의 경기 중 아직 예측이 없는 것만 골라서 예측을 채운다."""
    conn = get_connection(db_path)
    init_db(conn)

    rows = conn.execute(
        """
        SELECT g.game_id, g.league FROM games g
        LEFT JOIN predictions p ON p.game_id = g.game_id
        WHERE g.date = ? AND p.game_id IS NULL
        """,
        (target_date,),
    ).fetchall()

    if not rows:
        print(f"[info] {target_date} 예측이 필요한 경기 없음 (이미 다 있거나 경기가 없음)")
        conn.close()
        return

    for row in rows:
        game_id = row["game_id"]
        try:
            features = build_features(conn, game_id, season)
            pred = predict(features)
            upsert_prediction(conn, **pred)
            print(f"[ok] [{row['league']}] game_id={game_id} 사후 예측 생성 완료 (등급={pred['tier']})")
        except Exception as e:
            print(f"[warn] [{row['league']}] game_id={game_id} 예측 생성 실패: {e}")

    conn.close()


def run(target_date: str, season: int, db_path: str) -> None:
    print(f"[info] {target_date} 경기 결과 최신화 시작")

    print("--- MLB ---")
    try:
        mlb_collector.collect_and_store(target_date, db_path)
    except Exception as e:
        print(f"[warn] MLB 결과 갱신 실패: {e}")

    print("--- KBO ---")
    try:
        kbo_collector.collect_and_store(target_date, db_path)
    except Exception as e:
        print(f"[warn] KBO 결과 갱신 실패: {e}")

    if HAS_NPB:
        print("--- NPB ---")
        try:
            npb_collector.collect_and_store(target_date, db_path)
        except Exception as e:
            print(f"[warn] NPB 결과 갱신 실패: {e}")

    print("--- 빠진 예측 채우기 ---")
    try:
        fill_missing_predictions(target_date, season, db_path)
    except Exception as e:
        print(f"[warn] 예측 채우기 실패: {e}")

    print(f"[info] {target_date} 결과 최신화 완료")


def main():
    parser = argparse.ArgumentParser(description="어제 경기 결과(최종 스코어) 최신화")
    parser.add_argument("--date", default=(date.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
                         help="YYYY-MM-DD (기본값: 어제)")
    parser.add_argument("--season", type=int, default=date.today().year)
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    run(args.date, args.season, args.db)


if __name__ == "__main__":
    main()
