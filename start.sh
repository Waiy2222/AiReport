#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# AI 新闻简报 — 一键启动脚本 v2.0
# 解决了所有历史踩坑: 端口占用 / pycache / 中文路径 / Docker域名
# ═══════════════════════════════════════════════════════════════
set -e

PROJECT_ROOT="/d/项目/ai报道后续修改/ai-news-briefing-agent"
DB_URL="postgresql://postgres:postgres@localhost:5432/ai_news"
LOG_DIR="/tmp"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── 1. 检查 Docker ──
log_info "检查 Docker..."
if ! docker info > /dev/null 2>&1; then
    log_error "Docker 未运行，请先启动 Docker Desktop"
    exit 1
fi
log_ok "Docker 运行中"

# ── 2. 确保 PostgreSQL 运行 ──
log_info "启动 PostgreSQL..."
cd "$PROJECT_ROOT"
docker compose up -d postgres 2>&1 | tail -1
sleep 3

# 等待 healthy
for i in $(seq 1 30); do
    STATUS=$(docker ps --filter "name=postgres" --format "{{.Status}}" 2>/dev/null || echo "")
    if echo "$STATUS" | grep -q "healthy"; then
        log_ok "PostgreSQL healthy"
        break
    fi
    if [ $i -eq 30 ]; then
        log_error "PostgreSQL 启动超时"
        exit 1
    fi
    sleep 1
done

# ── 3. 杀掉所有旧进程 ──
log_info "清理旧进程 (端口 8001-8005)..."
for port in 8001 8002 8003 8005; do
    PID=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $NF}' | head -1)
    if [ -n "$PID" ] && [ "$PID" != "0" ]; then
        taskkill //F //PID "$PID" 2>/dev/null && log_ok "Killed port $port (PID $PID)" || true
    fi
done
sleep 2

# ── 4. 清理所有 pycache ──
log_info "清理 Python 缓存..."
python -c "
import shutil, os
root = r'$PROJECT_ROOT'
for mod in ['module-a', 'module-b', 'module-c/backend', 'module-e']:
    d = os.path.join(root, mod)
    for r, ds, fs in os.walk(d):
        for dn in ds:
            if dn == '__pycache__':
                shutil.rmtree(os.path.join(r, dn), ignore_errors=True)
print('Cache cleared')
" 2>&1
log_ok "pycache 已清理"

# ── 5. 启动所有模块 ──
log_info "启动所有后端模块..."

start_module() {
    local name=$1 dir=$2 port=$3
    shift 3
    log_info "启动 $name (:$port)..."
    cd "$dir"
    PYTHONDONTWRITEBYTECODE=1 nohup python -m uvicorn main:app --host 0.0.0.0 --port "$port" --log-level warning \
        > "$LOG_DIR/module_${name}.log" 2>&1 &
    log_ok "$name PID: $!"
}

# Module A (抓取)
start_module "a" "$PROJECT_ROOT/module-a" 8001 &
PID_A=$!
sleep 2

# Module B (AI加工)
start_module "b" "$PROJECT_ROOT/module-b" 8002 &
PID_B=$!
sleep 2

# Module C (小程序后端)
start_module "c" "$PROJECT_ROOT/module-c/backend" 8003 &
PID_C=$!
sleep 2

# Module E (调度+Dashboard)
start_module "e" "$PROJECT_ROOT/module-e" 8005 &
PID_E=$!

# ── 6. 等待服务就绪 ──
log_info "等待服务就绪 (最多 90s)..."
check_health() {
    curl -s --max-time 3 "http://localhost:$1/health" 2>/dev/null | grep -q '"status":"ok"'
}

HEALTHY=0
for i in $(seq 1 45); do
    ALL_OK=true
    for port in 8001 8002 8003 8005; do
        if ! check_health "$port"; then
            ALL_OK=false
            break
        fi
    done
    if $ALL_OK; then
        HEALTHY=1
        break
    fi
    sleep 2
done

echo ""
if [ $HEALTHY -eq 1 ]; then
    log_ok "全部服务就绪 ✅"
    echo ""
    for port in 8001 8002 8003 8005; do
        RESP=$(curl -s "http://localhost:$port/health" 2>/dev/null)
        echo -e "  :$port  ${GREEN}$RESP${NC}"
    done
else
    log_error "部分服务启动失败！检查日志:"
    for port in 8001 8002 8003 8005; do
        if check_health "$port" 2>/dev/null; then
            echo -e "  :$port  ${GREEN}OK${NC}"
        else
            echo -e "  :$port  ${RED}FAILED${NC}"
        fi
    done
    log_warn "查看日志: tail -20 $LOG_DIR/module_*.log"
fi

echo ""
echo -e "${GREEN}══════════════════════════════════════${NC}"
echo -e "${GREEN}  启动完成！${NC}"
echo ""
echo -e "  Dashboard:  ${BLUE}http://localhost:8005/dashboard/${NC}"
echo -e "  API:        ${BLUE}http://localhost:8003/api/${NC}"
echo -e "  触发生成:   ${YELLOW}curl -X POST http://localhost:8005/admin/trigger?type=morning${NC}"
echo ""
echo -e "  历史补全:   ${YELLOW}curl -X POST \"http://localhost:8005/admin/trigger?type=morning&gen_date=YYYY-MM-DD\"${NC}"
echo -e "${GREEN}══════════════════════════════════════${NC}"
