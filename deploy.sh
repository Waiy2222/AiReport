#!/bin/bash
# ================================================================
# AI 资讯早报 — 腾讯云服务器一键部署脚本
# ================================================================
# 使用方法：
#   chmod +x deploy.sh
#   ./deploy.sh              # 首次部署
#   ./deploy.sh --update     # 更新代码并重启
#   ./deploy.sh --ssl        # 申请 SSL 证书
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 颜色输出 ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 检查 .env 文件 ──────────────────────────────────────────
check_env() {
    if [ ! -f ".env" ]; then
        error "缺少 .env 文件，请先创建: cp .env.example .env 并填入真实 API Key"
    fi

    # 检查关键环境变量
    source .env 2>/dev/null || true
    local missing=""
    [ -z "${DEEPSEEK_API_KEY:-}" ] && missing="$missing DEEPSEEK_API_KEY"

    if [ -n "$missing" ]; then
        warn "以下环境变量未设置:$missing"
        warn "部分功能可能无法正常工作"
    fi
    info ".env 文件检查完成"
}

# ── 安装 Docker ─────────────────────────────────────────────
install_docker() {
    if command -v docker &>/dev/null; then
        info "Docker 已安装: $(docker --version)"
    else
        info "正在安装 Docker..."
        curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
        sudo systemctl enable docker
        sudo systemctl start docker
        info "Docker 安装完成"
    fi

    # Docker 镜像加速（腾讯云）
    if [ ! -f /etc/docker/daemon.json ]; then
        info "配置 Docker 镜像加速..."
        sudo mkdir -p /etc/docker
        sudo tee /etc/docker/daemon.json > /dev/null <<'JSON'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
JSON
        sudo systemctl daemon-reload
        sudo systemctl restart docker
    fi
}

# ── 部署/更新应用 ──────────────────────────────────────────
deploy_app() {
    info "拉取最新代码..."
    git pull origin master 2>/dev/null || warn "git pull 失败，使用当前代码"

    info "构建并启动服务（不含视频模块）..."
    docker compose build --no-cache
    docker compose up -d postgres module-a module-b module-c module-d module-e nginx

    info "等待服务就绪..."
    sleep 10

    # 健康检查
    info "执行健康检查..."
    for mod in a b c d e; do
        if curl -sf http://localhost/health/$mod > /dev/null 2>&1; then
            info "模块 $mod: ✓"
        else
            warn "模块 $mod: ✗ (可能还在启动中)"
        fi
    done

    info "部署完成！"
    echo ""
    echo "  Dashboard:  http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')/dashboard"
    echo "  小程序 API: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP')/api/"
    echo ""
}

# ── 申请 SSL 证书 ──────────────────────────────────────────
setup_ssl() {
    local domain="${1:-}"
    if [ -z "$domain" ]; then
        error "请指定域名: ./deploy.sh --ssl your-domain.com"
    fi

    info "为 $domain 申请 SSL 证书..."

    # 先停掉占用 80 端口的 nginx（certbot 需要）
    docker compose stop nginx 2>/dev/null || true

    sudo apt install -y certbot
    sudo certbot certonly --standalone -d "$domain"

    if [ $? -eq 0 ]; then
        info "SSL 证书申请成功！"
        info "证书路径: /etc/letsencrypt/live/$domain/"
        echo ""
        warn "接下来需要手动操作："
        warn "1. 编辑 nginx.conf，取消 HTTPS server 块的注释"
        warn "2. 将 YOUR_DOMAIN 替换为 $domain"
        warn "3. 编辑 docker-compose.yml，取消 443 端口和 SSL 卷挂载的注释"
        warn "4. 执行: docker compose restart nginx"
    else
        error "SSL 证书申请失败，请检查域名 DNS 是否指向本服务器 IP"
    fi
}

# ── 备份数据库 ──────────────────────────────────────────────
backup_db() {
    local filename="backup_$(date +%Y%m%d_%H%M%S).sql"
    info "备份数据库到 $filename ..."
    docker compose exec -T postgres pg_dump -U postgres ai_news > "$filename"
    info "备份完成: $filename ($(du -h "$filename" | cut -f1))"
}

# ── 查看日志 ────────────────────────────────────────────────
show_logs() {
    docker compose logs -f --tail=100 "$@"
}

# ════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════
case "${1:-}" in
    --update)
        info "更新模式：拉代码 + 重新构建 + 重启"
        git pull origin master 2>/dev/null || warn "git pull 失败"
        docker compose build
        docker compose up -d postgres module-a module-b module-c module-d module-e nginx
        ;;
    --ssl)
        setup_ssl "${2:-}"
        ;;
    --backup)
        backup_db
        ;;
    --logs)
        shift
        show_logs "$@"
        ;;
    --status)
        docker compose ps
        ;;
    --help|-h)
        echo "用法: $0 [选项]"
        echo "  (无参数)    首次部署"
        echo "  --update    更新代码并重新构建"
        echo "  --ssl DOMAIN  申请 SSL 证书"
        echo "  --backup    备份数据库"
        echo "  --logs      查看服务日志"
        echo "  --status    查看服务状态"
        ;;
    *)
        check_env
        install_docker
        deploy_app
        ;;
esac
