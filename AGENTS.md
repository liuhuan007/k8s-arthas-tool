# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

K8s Arthas Tool is a Java performance diagnosis platform for Kubernetes Pods. It combines Alibaba Arthas and async-profiler with kubectl to enable zero-intrusion diagnostics without code changes or service restarts.

## Common Commands

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (default 127.0.0.1:5005)
python server.py

# Run with custom port/host
python server.py --port 8080
python server.py --host 0.0.0.0
```

### Deployment

```bash
# Quick start (auto-deps + open browser)
./deploy.sh

# Background mode
./deploy.sh --daemon

# Daemon with external access (jump server)
./deploy.sh --daemon --host 0.0.0.0

# Install as systemd service
./deploy.sh --systemd

# Stop service
./deploy.sh --stop

# Check status
./deploy.sh --status

# Install Arthas JAR to Pod
./deploy.sh --install-arthas <namespace> <pod-name>
```

### Docker

```bash
# Build image
docker build -f deploy/Dockerfile -t arthas-k8s-tool:latest .

# Run with kubeconfig mounted
docker run -d \
  --name arthas-tool \
  -p 5005:5005 \
  -v ~/.kube:/root/.kube:ro \
  -v $(pwd)/data/profiler:/app/data/profiler \
  arthas-k8s-tool:latest
```

## Architecture

### Three-Layer Backend

1. **server.py** (Flask REST API, ~850 lines)
   - `/api/clusters/*` - Cluster management
   - `/api/arthas/*` - Arthas HTTP API proxy
   - `/api/profile/*` - Performance analysis tasks (async)
   - `/api/monitor/*` - Pod metrics collection
   - `/api/pod/*` - exec/files/terminal
   - `/api/gc/*` - GC log detection & download
   - `/api/files` - Local sampling files

2. **profiler_backend.py** (Core backend, 5-layer architecture, ~1050 lines)
   - Layer 1: `KubectlExecutor` - kubectl primitives (exec/cp/port-forward)
   - Layer 2: `ArthasAgentManager` - Agent lifecycle (detect/cleanup/start/wait)
   - Layer 3: `ArthasHttpClient` - Arthas HTTP API wrapper
   - Layer 4: `ArthasConnection` - Connection orchestration with short-circuit reuse
   - Layer 5: `ProfilerWorkflow` - Performance analysis (profiler/jfr/threaddump/heapdump)

3. **pod_monitor.py** (Pod metrics, ~580 lines)
   - `KubectlRunner` - kubectl command execution
   - `collect_pod_snapshot()` - One-time snapshot collection
   - `start_metrics_polling()` - Real-time metrics polling
   - Metrics: CPU/memory (cgroup), process list (ps), network (proc/net), Pod status

### Frontend Structure

- `index.html` - Main entry, references `static/` directory
- `static/js/app-ui.js` (~1600+ lines) - Main UI: clusters/diagnosis/monitoring/analysis
- `static/js/app-terminal.js` (~490 lines) - Terminal: kubectl exec/Tab completion/history
- `static/css/app.css` (~340 lines) - Dark theme styles

### Database (SQLite: `arthas.db`)

- **connections** - Arthas connection records (PK: `{cluster}/{namespace}/{pod}`)
- **arthas_commands** - Command execution history
- **profiler_tasks** - Sampling task history (CPU/JFR/Dump)
- **profiler_logs** - Profiling runtime logs

See `docs/database-schema.md` for full schema.

## Key Concepts

### ArthasConnection Short-Circuit Reuse

```
① HTTP reachable → reuse directly, no port-forward rebuild
② Agent already running → only establish port-forward
③ Fresh connection → agent + port-forward + HTTP ping
```

### Profiler Output Naming

Format: `{type}-{identifier}-{podName}-{YYYYMMDDHHmmss}.{ext}`

Examples:
- `profiler-cpu-udc-7cc5-20260322153847.html`
- `heap-udc-7cc5-20260322153847.hprof`
- `threaddump-udc-7cc5-20260322153847.txt`

All outputs saved to `data/profiler/`.

### Arthas JAR Detection Priority

```
/app/arthas/arthas-boot.jar     ← Recommended
/opt/arthas/arthas-boot.jar
/arthas/arthas-boot.jar
/home/admin/arthas-boot.jar
```

## Dependencies

- Python 3.10+
- kubectl 1.20+
- Target Pod: Java 8+ with exec permissions
- Arthas JAR 3.7+

Python packages: `flask>=3.0.0`, `flask-cors>=4.0.0`

## File Locations

- `clusters.json` - Cluster configuration (auto-generated)
- `arthas.db` - SQLite database
- `data/profiler/` - Sampling outputs (auto-created)
- `deploy/rbac.yaml` - Minimal kubectl RBAC permissions

## Testing Arthas Connection

```bash
# Check Arthas startup log
kubectl exec -n <ns> <pod> -- tail -30 /tmp/arthas_start.log

# Verify JAR exists
kubectl exec -n <ns> <pod> -- ls -la /app/arthas/

# Check Java version
kubectl exec -n <ns> <pod> -- java -version

# Check port availability
kubectl exec -n <ns> <pod> -- ss -tlnp | grep 8563
```

## kubectl RBAC Requirements

See `deploy/rbac.yaml` for minimal permissions:
- `pods` (get, list)
- `pods/exec` (create)
- `pods/portforward` (create)
- `pods/log` (get)
- `namespaces` (list)

## Multi-User Authentication

- **Default admin**: username `admin`, password `admin123` (auto-created on first DB init)
- **Database tables**: `users`, `user_clusters`, `audit_logs` (multi-account system)
- **User roles**: `admin` / `user` — admin sees all data, regular users see only their assigned clusters
- **Data isolation**: All queries filter by `user_id` except admin
- **Login flow**: `login.html` → authenticate → redirect to `index.html`
- **Admin pages**: `static/user-management.html` (user CRUD), `static/audit-logs.html` (audit logs)
- **Frontend**: Include `{credentials: 'include'}` in fetch calls to send session cookie

## Skill 调度规则 (using-superpowers)

收到任何消息后，在回复/行动前必须：
1. 检查是否有 skill 适用（哪怕 1% 可能也要调用）
2. 调用 skill 后再行动，不跳过

优先级：
- Process skills（brainstorming, debugging）先于 Implementation skills
- 用户指令 > skill 指令 > 系统默认

前端页面功能触发规则：
- 涉及前端页面/组件/UI功能时，必须调用 `ui-ux-pro-max` skill
- 涉及前端设计/样式/交互时，必须调用 `frontend-design` skill
- 必要时给出可运行的 demo HTML 交互页面，供用户预览确认后再正式实现。demo 需遵循项目规范：原生 JavaScript（不用框架）、暗色主题、CSS 变量、与现有 static/ 结构一致。统一入口：`http://127.0.0.1:5005/demo.html`，demo 文件存放于 `static/demo/`
