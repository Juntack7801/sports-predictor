"""
check_accuracy.py
이미 끝난 경기(games.home_score/away_score가 채워진 경기)에 대해
predictions 테이블의 예측과 실제 결과를 비교해서 accuracy_log에 저장한다.

- 승/패 예측 적중 여부
- 오버/언더 예측 적중 여부 (배트맨 실배당 라인 기준이면 그 라인, 아니면 자체계산 라인 기준)

사용법:
    python check_accuracy.py --date 2026-07-31
    python check_accuracy.py --date 2026-07-31 --league KBO
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from db.db import get_connection, init_db, upsert_accuracy_log
from features.feature_builder import build_features


def _fmt_pct(value) -> str:
    return f"{value*100:.0f}%" if value is not None else "정보없음"


def generate_analysis(
    conn,
    game_id: str,
    season: int,
    predicted_winner: str | None,
    actual_winner: str | None,
    winner_correct: int | None,
    predicted_tier: str | None,
    win_prob_home: float | None,
    win_prob_away: float | None,
    predicted_ou: str | None,
    ou_correct: int | None,
    ou_line: float | None,
    actual_total: int | None,
) -> str:
    """예측이 왜 맞았는지/틀렸는지 실제로 사용한 피처값을 근거로 설명 문장을 만든다.
    지어낸 이유가 아니라 그 경기 예측에 실제로 쓰인 승률/최근폼 데이터를 근거로 삼는다."""
    try:
        f = build_features(conn, game_id, season)
    except Exception:
        f = {}

    parts = []

    # --- 승패 분석 ---
    if winner_correct is not None:
        home_pct = f.get("home_win_pct_season")
        away_pct = f.get("away_win_pct_season")
        home_last10 = f.get("home_last10_win_pct")
        away_last10 = f.get("away_last10_win_pct")
        confidence = max(win_prob_home or 0, win_prob_away or 0)

        if winner_correct == 1:
            parts.append("승패 예측 적중.")
            if home_pct is not None and away_pct is not None:
                gap = abs(home_pct - away_pct)
                if gap >= 0.05:
                    parts.append(f"시즌 승률 차이({_fmt_pct(home_pct)} vs {_fmt_pct(away_pct)})가 뚜렷했고 예측 방향과 실제 결과가 일치했습니다.")
                else:
                    parts.append(f"시즌 승률은 비슷했지만({_fmt_pct(home_pct)} vs {_fmt_pct(away_pct)}) 예측 방향이 맞았습니다.")
        else:
            parts.append("승패 예측 실패.")
            if confidence < 0.60:
                parts.append(f"애초에 확신도가 낮았던 경기(등급: {predicted_tier})라 결과가 뒤집힐 가능성이 있었습니다.")
            else:
                parts.append(f"확신도({_fmt_pct(confidence)})가 꽤 높았는데 결과가 반대로 나왔습니다 — 그날 선발투수 컨디션, 불펜 소모, 부상 등 저희 모델이 반영하지 못하는 변수의 영향일 수 있습니다.")
            if home_last10 is not None and away_last10 is not None and home_pct is not None and away_pct is not None:
                season_favors_home = home_pct >= away_pct
                form_favors_home = home_last10 >= away_last10
                if season_favors_home != form_favors_home:
                    parts.append("시즌 성적과 최근 폼이 서로 다른 팀을 가리키고 있어서 헷갈렸던 경기였을 수 있습니다.")

    # --- 오버/언더 분석 ---
    if ou_correct is not None and ou_line is not None and actual_total is not None:
        if ou_correct == 1:
            parts.append(f"오버/언더 적중 (기준 {ou_line}, 실제 총점 {actual_total}점).")
        else:
            diff = abs(actual_total - ou_line)
            parts.append(f"오버/언더 실패 (기준 {ou_line}, 실제 총점 {actual_total}점, 차이 {diff:.1f}점) — 팀 평균 득실 데이터만으로는 그날의 변수(선발 컨디션, 불펜, 날씨 등)까지 반영하기 어려웠습니다.")

    return " ".join(parts) if parts else "분석할 데이터가 부족합니다."


def check(target_date: str, league: str | None, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    query = """
        SELECT g.game_id, g.home_score, g.away_score,
               p.win_prob_home, p.win_prob_away, p.tier,
               p.ou_line, p.over_prob, p.under_prob
        FROM games g
        JOIN predictions p ON p.game_id = g.game_id
        WHERE g.date = ?
          AND g.home_score IS NOT NULL
          AND g.away_score IS NOT NULL
    """
    params = [target_date]
    if league:
        query += " AND g.league = ?"
        params.append(league)

    rows = conn.execute(query, params).fetchall()

    if not rows:
        print(f"[info] {target_date} 에 결과 확인할 (끝난 + 예측된) 경기가 없습니다.")
        return

    checked = 0
    for r in rows:
        home_score, away_score = r["home_score"], r["away_score"]
        if home_score == away_score:
            continue  # 야구는 무승부가 없다고 가정 (연장 등으로 데이터가 이상하면 스킵)

        actual_winner = "home" if home_score > away_score else "away"
        predicted_winner = None
        winner_correct = None
        if r["win_prob_home"] is not None and r["win_prob_away"] is not None:
            predicted_winner = "home" if r["win_prob_home"] >= r["win_prob_away"] else "away"
            winner_correct = int(predicted_winner == actual_winner)

        actual_total = home_score + away_score
        predicted_ou = None
        ou_correct = None
        if r["ou_line"] is not None and r["over_prob"] is not None and r["under_prob"] is not None:
            predicted_ou = "over" if r["over_prob"] >= r["under_prob"] else "under"
            if actual_total == r["ou_line"]:
                ou_correct = None  # 푸시(적중/실패 판정 불가)
            else:
                actual_ou = "over" if actual_total > r["ou_line"] else "under"
                ou_correct = int(predicted_ou == actual_ou)

        season = int(target_date[:4])
        analysis_note = generate_analysis(
            conn, r["game_id"], season,
            predicted_winner, actual_winner, winner_correct, r["tier"],
            r["win_prob_home"], r["win_prob_away"],
            predicted_ou, ou_correct, r["ou_line"], actual_total,
        )

        upsert_accuracy_log(
            conn,
            game_id=r["game_id"],
            predicted_tier=r["tier"],
            predicted_winner=predicted_winner,
            actual_winner=actual_winner,
            winner_correct=winner_correct,
            predicted_ou=predicted_ou,
            actual_total=actual_total,
            ou_correct=ou_correct,
            analysis_note=analysis_note,
        )
        checked += 1
        result_txt = "적중" if winner_correct else ("실패" if winner_correct == 0 else "판정불가")
        print(f"[ok] game_id={r['game_id']} 승패예측 {result_txt} — {analysis_note}")

    print(f"[info] 총 {checked}경기 결과 확인 완료")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="지난 경기 예측 적중 여부 확인")
    parser.add_argument("--date", default=(date.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
                         help="YYYY-MM-DD (기본값: 어제)")
    parser.add_argument("--league", default=None, help="MLB | KBO | NPB (생략하면 전체)")
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    check(args.date, args.league, args.db)


if __name__ == "__main__":
    main()
