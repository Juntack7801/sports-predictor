"""
kbo_collector.py
KBO 공식 사이트(koreabaseball.com)는 자바스크립트로 일정 표를 나중에 채우는 방식이라
requests만으로는 데이터를 가져올 수 없다 (직접 확인함 - 최초 HTML은 표가 비어있음).
그래서 Selenium으로 실제 브라우저처럼 페이지를 열고, 표가 채워질 때까지 기다린 다음
채워진 HTML을 파싱한다.

이 collector는 사용자가 직접 캡처해서 보내준 실제 렌더링된 HTML 구조를 근거로 작성했다
(2026-08-02 기준 실제 페이지 구조 확인됨). 표 구조:
    <table id="tblScheduleList">
      <tbody>
        <tr><td class="day" rowspan="5">08.01(토)</td><td class="time"><b>18:00</b></td>
            <td class="play"><span>LG</span><em><span class="same">2</span><span>vs</span><span class="same">2</span></em><span>두산</span></td>
            ...(게임센터, 하이라이트, TV, 라디오, 구장, 비고)...</tr>
        <tr><td class="time">...</td><td class="play">...</td>...</tr>  <!-- 같은 날짜의 다음 경기는 day 셀이 없음(rowspan) -->
      </tbody>
    </table>
플레이 셀의 첫 번째 span = 원정팀, 두 번째(마지막) span = 홈팀 (구장이 홈팀 기준인 것으로 확인됨).

*** 참고 ***
페이지에 접속하면 기본적으로 "이번 달" 일정이 표시된다. 그래서 이 collector는
기본적으로 오늘이 포함된 달의 전체 일정을 가져온 뒤, 그중 target_date에 해당하는
경기만 뽑아서 저장한다. 다른 달을 보려면 페이지의 년/월 선택 드롭다운을 자바스크립트로
조작해야 하는데, 이건 아직 구현하지 않았다 (당장은 "오늘" 수집이 목적이라 우선순위 낮음).

Selenium 사용을 위해 컴퓨터에 크롬(Chrome) 브라우저가 설치되어 있어야 한다.
드라이버는 Selenium 4.6+ 이 자동으로 관리해준다 (별도 설치 불필요).

사용법:
    python collectors/kbo_collector.py
    python collectors/kbo_collector.py --date 2026-08-02
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_connection, init_db, upsert_team, upsert_game

LEAGUE = "KBO"
SCHEDULE_URL = "https://www.koreabaseball.com/Schedule/Schedule.aspx"


def fetch_rendered_html(timeout: int = 20) -> str:
    """Selenium으로 실제 브라우저처럼 페이지를 열고, 표가 채워질 때까지 기다린 뒤 HTML을 반환."""
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1200,1600")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(SCHEDULE_URL)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table#tblScheduleList td.play"))
        )
        time.sleep(0.5)
        return driver.page_source
    finally:
        driver.quit()


def _team_id(name: str) -> str:
    return "kbo_" + name.replace(" ", "")


def parse_month_schedule(html: str, year: int) -> list[dict]:
    """월 전체 일정 표를 파싱해서 [{date, away, home, away_score, home_score, venue, status}, ...] 리스트로 반환."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table#tblScheduleList")
    if not table:
        return []

    tbody = table.find("tbody")
    if not tbody:
        return []

    games = []
    current_month_day = None  # "08.01" 형태

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        if "day" in (tds[0].get("class") or []):
            day_text = tds[0].get_text(strip=True)
            current_month_day = day_text.split("(")[0]
            rest = tds[1:]
        else:
            rest = tds

        if current_month_day is None or len(rest) < 7:
            continue

        time_td = rest[0]
        play_td = rest[1]
        venue_td = rest[6] if len(rest) > 6 else None
        remark_td = rest[7] if len(rest) > 7 else None

        time_text = time_td.get_text(strip=True) if time_td else ""  # 예: "18:00"

        top_spans = play_td.find_all("span", recursive=False)
        if len(top_spans) < 2:
            continue

        away_name = top_spans[0].get_text(strip=True)
        home_name = top_spans[-1].get_text(strip=True)

        em = play_td.find("em")
        away_score = home_score = None
        if em:
            em_spans = em.find_all("span")
            if len(em_spans) >= 3:
                try:
                    away_score = int(em_spans[0].get_text(strip=True))
                    home_score = int(em_spans[-1].get_text(strip=True))
                except ValueError:
                    pass

        venue = venue_td.get_text(strip=True) if venue_td else None
        remark = remark_td.get_text(strip=True) if remark_td else ""

        try:
            month, day = current_month_day.split(".")
            date_str = f"{year}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            continue

        # 시간순 정렬을 위한 필드 (한국시간 기준 그냥 문자열로, 같은 리그 안에서만 비교하므로 충분)
        game_datetime = f"{date_str} {time_text}:00" if time_text else None

        if remark and remark not in ("-", ""):
            status = remark
        elif away_score is not None:
            status = "Final"
        else:
            status = "Scheduled"

        games.append({
            "date": date_str,
            "away_name": away_name,
            "home_name": home_name,
            "away_score": away_score,
            "home_score": home_score,
            "venue": venue,
            "status": status,
            "game_datetime": game_datetime,
        })

    return games


def collect_and_store(target_date: str, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    year = int(target_date[:4])

    try:
        html = fetch_rendered_html()
    except Exception as e:
        print(f"[error] KBO 페이지 로딩 실패: {e}")
        print("[hint] 크롬 브라우저가 설치되어 있는지 확인하세요. 'pip install selenium'도 필요합니다.")
        return

    all_games = parse_month_schedule(html, year)
    if not all_games:
        print("[warn] KBO 일정 표를 파싱하지 못했습니다. 사이트 구조가 바뀌었을 수 있습니다.")
        return

    games_today = [g for g in all_games if g["date"] == target_date]
    if not games_today:
        print(f"[info] {target_date} KBO 경기가 없습니다 (해당 월 일정은 {len(all_games)}건 확인됨).")
        print("[hint] 이 collector는 '이번 달' 일정만 가져옵니다. target_date가 이번 달이 아니면 못 찾습니다.")
        return

    for i, g in enumerate(games_today):
        home_id = _team_id(g["home_name"])
        away_id = _team_id(g["away_name"])
        game_id = f"kbo_{target_date}_{i}"

        upsert_team(conn, home_id, LEAGUE, g["home_name"])
        upsert_team(conn, away_id, LEAGUE, g["away_name"])
        upsert_game(
            conn,
            game_id=game_id,
            league=LEAGUE,
            date=target_date,
            home_team_id=home_id,
            away_team_id=away_id,
            home_score=g["home_score"],
            away_score=g["away_score"],
            venue_name=g["venue"],
            status=g["status"],
            game_datetime_utc=g.get("game_datetime"),
        )
        print(f"[ok] {g['away_name']} @ {g['home_name']} 저장 완료 (상태: {g['status']})")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="KBO 오늘 경기 수집기 (Selenium)")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    collect_and_store(args.date, args.db)


if __name__ == "__main__":
    main()
