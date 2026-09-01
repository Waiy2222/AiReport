#!/bin/bash
# Start all modules for local development
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting all modules from $ROOT ..."

# Kill existing (Git Bash compatible — pkill doesn't work here)
echo "Killing old processes..."
for port in 8001 8002 8003 8004 8005 8006; do
  pid=$(netstat -ano 2>/dev/null | grep ":${port} " | grep LISTENING | awk '{print $NF}' | head -1)
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    taskkill //F //PID "$pid" 2>/dev/null && echo "  killed port $port (PID=$pid)"
  fi
done
sleep 1

# Start each module — must cd into each directory so internal imports work
(cd "$ROOT/module-a" && PYTHONPATH="..:../shared" DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news" python -m uvicorn main:app --host 0.0.0.0 --port 8001 --log-level warning) &
(cd "$ROOT/module-b" && PYTHONPATH="..:../shared" DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news" python -m uvicorn main:app --host 0.0.0.0 --port 8002 --log-level warning) &
(cd "$ROOT/module-c/backend" && PYTHONPATH="../..:../../shared" DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news" python -m uvicorn main:app --host 0.0.0.0 --port 8003 --log-level warning) &
(cd "$ROOT/module-d" && PYTHONPATH="..:../shared" DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news" python -m uvicorn main:app --host 0.0.0.0 --port 8004 --log-level warning) &
(cd "$ROOT/module-e" && PYTHONPATH="..:../shared" DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news" A_URL="http://localhost:8001/run" B_URL="http://localhost:8002/run-b" C_URL="http://localhost:8003/push" python -m uvicorn main:app --host 0.0.0.0 --port 8005 --log-level warning) &
(cd "$ROOT/module-f" && PYTHONPATH="..:../shared" DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news" python -m uvicorn main:app --host 0.0.0.0 --port 8006 --log-level warning) &

sleep 3

# Health check
echo ""
echo "=== Health Check ==="
for port in 8001 8002 8003 8004 8005 8006; do
  status=$(curl -s http://localhost:$port/health 2>/dev/null | python -c "import sys,json; print(json.load(sys.stdin).get('status','DOWN'))" 2>/dev/null || echo "DOWN")
  echo "  Port $port: $status"
done

echo ""
echo "All modules started. Dashboard: http://localhost:8005/dashboard"
