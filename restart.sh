#!/bin/bash
# ================================================================
# AI新闻简报 — 本地启动/重启脚本 (一站式)
# ================================================================
# 用法:
#   bash restart.sh          — 重启所有模块 (A/B/C/E)
#   bash restart.sh a        — 只重启模块A
#   bash restart.sh b        — 只重启模块B
#   bash restart.sh c        — 只重启模块C
#   bash restart.sh e        — 只重启模块E
#
# 前置条件:
#   1. Docker Desktop 必须运行
#   2. PostgreSQL 容器: docker compose up -d postgres
#
# 触发简报:
#   curl -X POST "http://localhost:8005/admin/trigger?type=morning"
#   curl -X POST "http://localhost:8005/admin/trigger?type=evening"
#
# 历史补全:
#   curl -X POST "http://localhost:8005/admin/trigger?type=morning&gen_date=2026-06-14"
#
# ================================================================
# 已知问题 & 注意事项 (踩坑记录)
# ================================================================
#
# 1. [致命] taskkill 必须在 cmd //c 下执行
#    错误: taskkill //F //PID xxx (bash会把//解析为路径)
#    正确: cmd //c "taskkill /F /PID xxx"
#
# 2. [致命] 修改Python代码后必须删 __pycache__ + 杀旧进程
#    否则: 旧字节码继续运行，修改不生效
#    本脚本已自动处理
#
# 3. [重要] 不能从项目根目录 python -m uvicorn module-a.main:app
#    错误: ModuleNotFoundError: No module named 'db'
#    必须: cd 到模块目录后 python -m uvicorn main:app
#
# 4. [重要] 模块C路径是 module-c/backend 不是 module-c
#
# 5. [重要] 模块E必须设置 A_URL/B_URL 等为 localhost
#    否则: 默认用Docker内部域名 module-a:8001 → 502
#
# 6. [修复] Section tag字段缺失 → module-c/backend/main.py _normalize_sections()
#    旧数据只有 section_title 没有 tag，API层自动补齐
#
# 7. [修复] 政治敏感过滤 → module-a/scrapers/filters.py
#    40+强关键词直接拦截，30+弱关键词组合拦截
#
# 8. [修复] 英文标题翻译 → module-b/pipeline.py _translate_items()
#    自动检测英文标题并调用DeepSeek翻译为中文
#
# 9. [修复] 辩论功能 → 原始代码正确，需确保.env加载 + 进程正确重启
#
# 10. [待修复] 标签匹配不准 → module-b/ai/summarizer.py _KEYWORD_MAP
#     "代理"等宽泛词会误匹配Agent标签
#
# ================================================================

set -e
ROOT="/d/项目/ai报道后续修改/ai-news-briefing-agent"
export PYTHONPATH="$ROOT"
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ai_news"

# ── Docker PostgreSQL ──────────────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q "postgres"; then
  echo ">>> PostgreSQL not running, starting..."
  cd "$ROOT"
  docker compose up -d postgres
  sleep 3
fi
echo "PostgreSQL: OK"

# ── 工具函数 ────────────────────────────────────────────────────
kill_port() {
  local port=$1
  local pid=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $NF}' | head -1)
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    echo "  Kill PID $pid (port $port)"
    cmd //c "taskkill /F /PID $pid" 2>/dev/null || true
    sleep 2
  fi
}

clear_pycache() {
  local dir=$1
  python -c "
import shutil, os
for root, ds, fs in os.walk(r'$dir'):
    for d in list(ds):
        if d == '__pycache__':
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
" 2>/dev/null
}

start_mod() {
  local name=$1 dir=$2 port=$3
  echo "[$name] :$port"
  kill_port $port
  clear_pycache "$dir"
  cd "$dir"
  nohup python -m uvicorn main:app --host 0.0.0.0 --port $port --log-level warning \
    > /tmp/module_${name}.log 2>&1 &
  cd "$ROOT"
}

# ── 启动模块 ────────────────────────────────────────────────────
case "${1:-all}" in
  a|all) start_mod "A" "$ROOT/module-a" 8001 ;;&
  b|all) start_mod "B" "$ROOT/module-b" 8002 ;;&
  c|all) start_mod "C" "$ROOT/module-c/backend" 8003 ;;&
  e|all)
    echo "[E] :8005 (with inter-module URLs)"
    kill_port 8005
    clear_pycache "$ROOT/module-e"
    cd "$ROOT/module-e"
    A_URL="http://localhost:8001/run" \
    B_URL="http://localhost:8002/run-b" \
    C_URL="http://localhost:8003/push" \
    D_URL="http://localhost:8004/publish" \
    F_URL="http://localhost:8006/generate" \
    nohup python -m uvicorn main:app --host 0.0.0.0 --port 8005 --log-level warning \
      > /tmp/module_E.log 2>&1 &
    cd "$ROOT"
    ;;
esac

sleep 8
echo ""
echo "=== Health ==="
for p in 8001 8002 8003 8005; do
  s=$(curl -s http://localhost:$p/health 2>/dev/null || echo 'DOWN')
  echo "  :$p $s"
done
echo ""
echo "Trigger: curl -X POST http://localhost:8005/admin/trigger?type=morning"
