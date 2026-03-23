#!/usr/bin/env bash
# =============================================================================
# Arthas K8s 诊断台 — 主部署脚本
#
# 用法:
#   ./deploy.sh                              # 前台运行，默认 127.0.0.1:5001
#   ./deploy.sh --host 0.0.0.0              # 监听所有网卡（跳板机场景）
#   ./deploy.sh --port 8080                 # 自定义端口
#   ./deploy.sh --daemon                    # 后台运行（nohup）
#   ./deploy.sh --daemon --host 0.0.0.0    # 后台 + 开放外网
#   ./deploy.sh --systemd                   # 安装为 systemd 服务（需 root）
#   ./deploy.sh --stop                      # 停止后台运行的实例
#   ./deploy.sh --status                    # 查看运行状态
#   ./deploy.sh --restart                   # 重启（stop + daemon）
#   ./deploy.sh --install-arthas <ns> <pod> # 向 Pod 内安装 Arthas JAR
#   ./deploy.sh --uninstall-systemd         # 卸载 systemd 服务
#   ./deploy.sh --help                      # 显示帮助
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="arthas-k8s-tool"
DEFAULT_HOST="127.0.0.1"
DEFAULT_PORT="5001"
LOG_FILE="${SCRIPT_DIR}/arthas-tool.log"
PID_FILE="${SCRIPT_DIR}/arthas-tool.pid"
SERVICE_FILE="/etc/systemd/system/arthas-tool.service"
ARTHAS_JAR_URL="https://arthas.aliyun.com/arthas-boot.jar"
ARTHAS_DEFAULT_PATH="/app/arthas/arthas-boot.jar"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
success() { echo -e "${GREEN}[✓]${NC}    $*"; }
section() { echo -e "\n${BLUE}${BOLD}──── $* ────${NC}"; }
banner()  {
  echo -e "${CYAN}${BOLD}"
  echo "  ╔════════════════════════════════════════╗"
  echo "  ║     Arthas K8s 诊断台                  ║"
  echo "  ║     Java 性能诊断 · 零侵入 · 一站式     ║"
  echo "  ╚════════════════════════════════════════╝"
  echo -e "${NC}"
}

HOST="${DEFAULT_HOST}"; PORT="${DEFAULT_PORT}"
DAEMON=false; DO_SYSTEMD=false; DO_STOP=false; DO_STATUS=false
DO_RESTART=false; DO_UNINSTALL=false
INSTALL_ARTHAS_NS=""; INSTALL_ARTHAS_POD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)             HOST="$2";              shift 2 ;;
    --port)             PORT="$2";              shift 2 ;;
    --daemon|-d)        DAEMON=true;            shift   ;;
    --systemd)          DO_SYSTEMD=true;        shift   ;;
    --stop)             DO_STOP=true;           shift   ;;
    --status)           DO_STATUS=true;         shift   ;;
    --restart)          DO_RESTART=true;        shift   ;;
    --uninstall-systemd) DO_UNINSTALL=true;     shift   ;;
    --install-arthas)
      INSTALL_ARTHAS_NS="${2:-}"; INSTALL_ARTHAS_POD="${3:-}"
      [[ -z "$INSTALL_ARTHAS_NS" || -z "$INSTALL_ARTHAS_POD" ]] && {
        error "--install-arthas 需要 <namespace> <pod-name>"; exit 1; }
      shift 3 ;;
    -h|--help)
      banner
      echo "用法: $0 [选项]"
      echo ""
      echo "  --host <IP>                  监听地址（默认 127.0.0.1）"
      echo "  --port <PORT>                监听端口（默认 5001）"
      echo "  --daemon, -d                 后台运行（nohup）"
      echo "  --systemd                    安装为 systemd 服务（需 root）"
      echo "  --stop                       停止后台实例"
      echo "  --restart                    重启服务"
      echo "  --status                     查看运行状态"
      echo "  --uninstall-systemd          卸载 systemd 服务"
      echo "  --install-arthas <ns> <pod>  向 Pod 安装 Arthas JAR"
      echo "  --help                       显示帮助"
      echo ""
      echo "示例:"
      echo "  ./deploy.sh                                  本地前台启动"
      echo "  ./deploy.sh --daemon --host 0.0.0.0          跳板机后台部署"
      echo "  ./deploy.sh --install-arthas prod my-pod     安装 Arthas 到 Pod"
      exit 0 ;;
    *) error "未知参数: $1（使用 --help 查看帮助）"; exit 1 ;;
  esac
done

# ── 检查依赖 ──────────────────────────────────────────────────────────────────
check_deps() {
  section "检查运行环境"
  local python_cmd=""
  for cmd in python3 python; do
    command -v "$cmd" &>/dev/null && { python_cmd="$cmd"; break; }
  done
  [[ -z "$python_cmd" ]] && { error "未找到 Python，请安装 Python >= 3.10"; exit 1; }
  local py_ver py_ok
  py_ver=$("$python_cmd" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  py_ok=$("$python_cmd" -c 'import sys; print(sys.version_info >= (3,10))')
  [[ "$py_ok" != "True" ]] && { error "Python 版本过低：$py_ver，需要 >= 3.10"; exit 1; }
  success "Python $py_ver ($python_cmd)"

  if ! command -v kubectl &>/dev/null; then
    error "未找到 kubectl，请安装并配置 kubeconfig"; exit 1; fi
  local kv
  kv=$(kubectl version --client --short 2>/dev/null | head -1 || echo "unknown")
  success "kubectl: $kv"

  kubectl cluster-info &>/dev/null 2>&1 \
    && success "kubeconfig 连接正常" \
    || warn "kubectl 暂时无法连接集群（可在界面中手动配置集群）"

  if ! "$python_cmd" -c "import flask, flask_cors" &>/dev/null 2>&1; then
    info "安装 Python 依赖..."
    "$python_cmd" -m pip install -r "${SCRIPT_DIR}/requirements.txt" -q || {
      error "依赖安装失败，请手动运行: pip install -r requirements.txt"; exit 1; }
    success "依赖安装完成"
  else
    success "Python 依赖已就绪"
  fi
  echo "$python_cmd"
}

# ── 停止服务 ──────────────────────────────────────────────────────────────────
do_stop() {
  section "停止服务"
  local stopped=false
  if [[ -f "$PID_FILE" ]]; then
    local pid; pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      info "停止进程 PID=$pid..."; kill "$pid"; sleep 2
      kill -0 "$pid" 2>/dev/null && kill -9 "$pid" || true
      stopped=true
    fi
    rm -f "$PID_FILE"
  fi
  local pids; pids=$(pgrep -f "python.*server.py" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    info "停止进程: $pids"
    echo "$pids" | xargs kill 2>/dev/null || true
    stopped=true
  fi
  $stopped && success "服务已停止" || info "未发现运行中的实例"
}

# ── 查看状态 ──────────────────────────────────────────────────────────────────
do_status() {
  section "服务状态"
  if [[ -f "$PID_FILE" ]]; then
    local pid; pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      success "运行中  PID=$pid"
      echo "  API:  http://${HOST}:${PORT}/api/health"
      echo "  日志: ${LOG_FILE}"
      echo ""; info "最近日志:"; tail -20 "$LOG_FILE" 2>/dev/null || echo "（无日志）"
    else
      warn "PID 文件存在但进程已退出"; rm -f "$PID_FILE"; fi
  else
    local pids; pids=$(pgrep -f "python.*server.py" 2>/dev/null || true)
    [[ -n "$pids" ]] && success "运行中 PID=$pids（无 PID 文件）" || info "未检测到运行中的实例"
  fi
  systemctl list-units --type=service 2>/dev/null | grep -q "$APP_NAME" && {
    echo ""; info "systemd 状态:"
    systemctl status "$APP_NAME" --no-pager -l 2>/dev/null || true; } || true
}

# ── systemd 服务 ─────────────────────────────────────────────────────────────
do_systemd() {
  section "安装 systemd 服务"
  [[ $EUID -ne 0 ]] && { error "需要 root 权限，请使用 sudo"; exit 1; }
  local pcmd; pcmd=$(check_deps | tail -1)
  cat > "$SERVICE_FILE" << UNIT
[Unit]
Description=Arthas K8s 诊断台
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${pcmd} ${SCRIPT_DIR}/server.py --host ${HOST} --port ${PORT}
Restart=always
RestartSec=10
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}
Environment="PATH=${PATH}"
Environment="HOME=${HOME}"

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable "$APP_NAME"
  systemctl start  "$APP_NAME"
  success "systemd 服务已安装并启动"
  echo "  sudo systemctl {start|stop|restart|status} ${APP_NAME}"
  echo "  sudo journalctl -u ${APP_NAME} -f"
}

do_uninstall_systemd() {
  section "卸载 systemd 服务"
  [[ $EUID -ne 0 ]] && { error "需要 root 权限"; exit 1; }
  systemctl stop    "$APP_NAME" 2>/dev/null || true
  systemctl disable "$APP_NAME" 2>/dev/null || true
  rm -f "$SERVICE_FILE"; systemctl daemon-reload
  success "systemd 服务已卸载"
}

# ── 安装 Arthas 到 Pod ────────────────────────────────────────────────────────
install_arthas() {
  local ns="$1" pod="$2"
  section "安装 Arthas JAR → ${ns}/${pod}"
  local phase
  phase=$(kubectl get pod -n "$ns" "$pod" -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
  [[ "$phase" != "Running" ]] && { error "Pod 状态: ${phase}，需要 Running"; exit 1; }
  success "Pod 状态: Running"

  info "下载 Arthas JAR（${ARTHAS_JAR_URL}）..."
  if kubectl exec -n "$ns" "$pod" -- bash -c "
    set -e; mkdir -p /app/arthas
    if command -v curl >/dev/null 2>&1; then
      curl -sSfL -o ${ARTHAS_DEFAULT_PATH} '${ARTHAS_JAR_URL}'
    elif command -v wget >/dev/null 2>&1; then
      wget -qO ${ARTHAS_DEFAULT_PATH} '${ARTHAS_JAR_URL}'
    else echo 'ERROR: no curl/wget' >&2; exit 1; fi
    ls -lh ${ARTHAS_DEFAULT_PATH}" 2>&1; then
    success "JAR 安装完成: ${ARTHAS_DEFAULT_PATH}"
  else
    warn "Pod 内网络下载失败，尝试 kubectl cp 上传..."
    local local_jar="${SCRIPT_DIR}/arthas-boot.jar"
    [[ ! -f "$local_jar" ]] && {
      info "本地下载..."; curl -sSfL -o "$local_jar" "${ARTHAS_JAR_URL}"; }
    kubectl exec -n "$ns" "$pod" -- mkdir -p /app/arthas
    kubectl cp "$local_jar" "${ns}/${pod}:${ARTHAS_DEFAULT_PATH}"
    success "kubectl cp 上传完成"
  fi
  kubectl exec -n "$ns" "$pod" -- java -jar "${ARTHAS_DEFAULT_PATH}" --version 2>/dev/null \
    && success "版本验证通过" || warn "JAR 已安装，版本验证跳过"
}

# ── 后台启动 ──────────────────────────────────────────────────────────────────
start_daemon() {
  local pcmd="$1"
  [[ -f "$PID_FILE" ]] && {
    local op; op=$(cat "$PID_FILE")
    kill -0 "$op" 2>/dev/null && { warn "停止已有实例 PID=$op"; kill "$op"; sleep 2; }
    rm -f "$PID_FILE"; }
  info "后台启动..."
  cd "${SCRIPT_DIR}" || true
  nohup "$pcmd" "${SCRIPT_DIR}/server.py" --host "$HOST" --port "$PORT" \
    >> "$LOG_FILE" 2>&1 &
  local pid=$!; echo "$pid" > "$PID_FILE"
  for i in $(seq 1 15); do
    sleep 1
    curl -sf "http://127.0.0.1:${PORT}/api/health" &>/dev/null && {
      success "服务已启动  PID=$pid"
      echo "  API:  http://${HOST}:${PORT}/api/health"
      echo "  日志: tail -f ${LOG_FILE}"
      [[ "$HOST" == "127.0.0.1" ]] \
        && echo "  前端: file://${SCRIPT_DIR}/index.html" \
        || echo "  前端: http://${HOST}:${PORT}/"
      return 0; }
  done
  error "启动超时，查看日志: tail -30 ${LOG_FILE}"; exit 1
}

# ── 前台启动 ──────────────────────────────────────────────────────────────────
start_foreground() {
  local pcmd="$1"
  echo "  API:  http://${HOST}:${PORT}/api/health"
  [[ "$HOST" == "127.0.0.1" ]] && {
    echo "  前端: file://${SCRIPT_DIR}/index.html"
    (sleep 1.5 && {
      command -v open    &>/dev/null && open    "file://${SCRIPT_DIR}/index.html"
      command -v xdg-open &>/dev/null && xdg-open "file://${SCRIPT_DIR}/index.html"
    } || true) &
  } || echo "  前端: http://${HOST}:${PORT}/"
  echo "  按 Ctrl+C 停止"
  echo "────────────────────────────────────────────"
  # 切换到项目目录再启动，确保相对路径（clusters.json 等）在正确位置
  cd "${SCRIPT_DIR}" || true
  exec "$pcmd" "${SCRIPT_DIR}/server.py" --host "$HOST" --port "$PORT"
}

# ═════════════════════════════════════════════════════════════════════════════
# 主流程
# ═════════════════════════════════════════════════════════════════════════════
[[ -n "$INSTALL_ARTHAS_NS" ]] && { install_arthas "$INSTALL_ARTHAS_NS" "$INSTALL_ARTHAS_POD"; exit 0; }
$DO_STOP      && { do_stop;               exit 0; }
$DO_STATUS    && { do_status;             exit 0; }
$DO_UNINSTALL && { do_uninstall_systemd;  exit 0; }
$DO_RESTART   && { do_stop; DAEMON=true;           }
$DO_SYSTEMD   && { do_systemd;            exit 0; }

banner
pcmd=$(check_deps | tail -1)
mkdir -p "${SCRIPT_DIR}/profiler_output"

if $DAEMON; then
  section "后台启动"
  start_daemon "$pcmd"
else
  section "前台启动"
  start_foreground "$pcmd"
fi
