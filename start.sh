#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   Amazon PPC Intelligence v2.0       ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Backend
echo "  [1/3] Installing backend dependencies..."
cd "$SCRIPT_DIR/backend"
pip install -r requirements.txt -q 2>/dev/null

echo "  [2/3] Starting FastAPI backend on :8000..."
uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level warning &
BACKEND_PID=$!

# Frontend
echo "  [3/3] Starting React frontend on :5173..."
cd "$SCRIPT_DIR/frontend"
npm install --silent 2>/dev/null
npm run dev &
FRONTEND_PID=$!

# Open browser
sleep 3
echo ""
echo "  Ready! Opening http://localhost:5173"
echo "  Press Ctrl+C to stop both servers."
echo ""

# Open browser (cross-platform)
if command -v xdg-open &>/dev/null; then
  xdg-open http://localhost:5173
elif command -v open &>/dev/null; then
  open http://localhost:5173
elif command -v start &>/dev/null; then
  start http://localhost:5173
fi

# Wait and cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
