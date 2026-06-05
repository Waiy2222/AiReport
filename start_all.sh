#!/bin/bash
# Start all modules for local development
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT"

echo "Starting all modules from $ROOT ..."

# Kill existing
pkill -f "uvicorn.*module" 2>/dev/null
sleep 1

# Start each module
cd "$ROOT"
python -m uvicorn module-a.main:app --host 0.0.0.0 --port 8001 --log-level warning &
python -m uvicorn module-b.main:app --host 0.0.0.0 --port 8002 --log-level warning &
python -m uvicorn module-c.backend.main:app --host 0.0.0.0 --port 8003 --log-level warning &
python -m uvicorn module-d.main:app --host 0.0.0.0 --port 8004 --log-level warning &
python -m uvicorn module-e.main:app --host 0.0.0.0 --port 8005 --log-level warning &

sleep 3

# Health check
echo ""
echo "=== Health Check ==="
for port in 8001 8002 8003 8004 8005; do
  status=$(curl -s http://localhost:$port/health 2>/dev/null | python -c "import sys,json; print(json.load(sys.stdin).get('status','DOWN'))" 2>/dev/null || echo "DOWN")
  echo "  Port $port: $status"
done

echo ""
echo "All modules started. Dashboard: http://localhost:8005/dashboard"
