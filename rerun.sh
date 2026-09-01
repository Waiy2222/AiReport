#!/bin/bash
# ═══════════════════════════════════════════════════════════
# 代码修改后重跑 — 保证用最新代码生成早晚报
# 用法: bash rerun.sh [morning|evening|both]
# ═══════════════════════════════════════════════════════════
set -e
PROJECT="/d/项目/ai报道后续修改/ai-news-briefing-agent"
TYPE="${1:-both}"

echo "=== 强制重启模块B (最新代码) ==="

# 1. 杀B
PID=$(netstat -ano 2>/dev/null | grep ":8002 " | grep LISTENING | awk '{print $NF}' | head -1)
[ -n "$PID" ] && [ "$PID" != "0" ] && taskkill //F //PID "$PID" 2>/dev/null && echo "killed B PID=$PID"
sleep 1

# 2. 清缓存 (PYTHONDONTWRITEBYTECODE=1 已设，但清理存量)
cd "$PROJECT/module-b"
python -c "import shutil,os;[shutil.rmtree(os.path.join(r,d),ignore_errors=True) for r,ds,fs in os.walk('.') for d in ds if d=='__pycache__']"
echo "cache cleared"

# 3. 启B (不生成pyc, 每次import都是最新)
PYTHONDONTWRITEBYTECODE=1 nohup python -m uvicorn main:app --host 0.0.0.0 --port 8002 --log-level error > /dev/null 2>&1 &
sleep 4

# 4. 健康检查
if ! curl -s --max-time 3 http://localhost:8002/health | grep -q '"status":"ok"'; then
    echo "ERROR: B 启动失败!"
    exit 1
fi
echo "B OK (新鲜代码)"

# 5. 触发
if [ "$TYPE" = "both" ] || [ "$TYPE" = "morning" ]; then
    echo -n "早报... "
    curl -s -X POST "http://localhost:8005/admin/trigger?type=morning" | python -c "import sys,json;d=json.load(sys.stdin);print(d['steps']['process']['stats']['final_count'],'条')" 2>/dev/null || echo "FAIL"
fi
if [ "$TYPE" = "both" ] || [ "$TYPE" = "evening" ]; then
    echo -n "晚报... "
    curl -s -X POST "http://localhost:8005/admin/trigger?type=evening" | python -c "import sys,json;d=json.load(sys.stdin);print(d['steps']['process']['stats']['final_count'],'条')" 2>/dev/null || echo "FAIL"
fi

echo "=== 完成 ==="
