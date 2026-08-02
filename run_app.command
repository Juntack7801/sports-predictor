#!/bin/bash
# 더블클릭으로 실행하는 런처 (맥)
# 1) API 서버를 백그라운드로 켜고
# 2) 잠깐 기다렸다가 웹 화면을 기본 브라우저로 자동으로 연다.

cd "$(dirname "$0")"

echo "서버를 켜는 중..."
python3 -m uvicorn api.server:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!

sleep 2

echo "화면을 여는 중..."
open "web/index.html"

echo ""
echo "다 켜졌습니다. 이 창은 닫지 말고 그대로 두세요 (서버가 여기서 돌아갑니다)."
echo "끄려면 이 창에서 Ctrl+C 를 누르세요."

wait $SERVER_PID
