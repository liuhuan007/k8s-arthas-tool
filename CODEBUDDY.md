# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## Project Overview

K8s Arthas Tool is a Java performance diagnosis platform for Kubernetes Pods, combining Alibaba Arthas + async-profiler with kubectl to enable zero-intrusion diagnostics. It's a Flask-based web application with SQLite storage, supporting multi-user authentication (Flask-Login + bcrypt), RBAC (admin/user roles), audit logging, and per-user cluster isolation.

## Common Commands

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run local server (default 127.0.0.1:5001)
python server.py

# Custom port/host
python server.py --port 8080
python server.py --host 0.0.0.0

# Quick start (auto-deps + open browser)
./deploy.sh

# Background / systemd deployment
./deploy.sh --daemon --host 0.0.0.0
./deploy.sh --systemd

# Install Arthas JAR into a Pod
./deploy.sh --install-arthas <namespace> <pod-name>
```

### Docker

```bash
docker build -f Dockerfile -t arthas-k8s-tool:latest .
docker run -d --name arthas-tool -p 5001:5001 \
  -v ~/.kube:/root/.kube:ro \
  -v $(pwd)/profiler_output:/app/profiler_output \
  arthas-k8s-tool:latest
```

### Debugging Arthas Connection Issues

```bash
kubectl exec -n <ns> <pod> -- tail -30 /tmp/arthas_start.log
kubectl exec -n <ns> <pod> -- ls -la /app/arthas/
kubectl exec -n <ns> <pod> -- java -version
kubectl exec -n <ns> <pod> -- ss -tlnp | grep 8563
```

**Note:** This project has no test suite, linter configuration, or build pipeline beyond `pip install` and direct `python` execution.

## Architecture

### Three-Layer Backend

**`server.py`** (~2300 lines) — Flask REST API entry point. Handles all HTTP routing, authentication (Flask-Login session management), database initialization (SQLite), and serves static files. Key route groups:
- `/api/auth/*` — Login/logout/password change, user session
- `/api/users/*` — Admin-only user CRUD (create/update/delete/status)
- `/api/clusters/*` — Cluster CRUD, namespace/pod listing (filtered by user access)
- `/api/arthas/*` — Arthas HTTP API proxy (connect/exec/session)
- `/api/profile/*` — Async performance analysis tasks (profiler/JFR/dump)
- `/api/monitor/*` — Pod metrics collection (CPU/memory/network/processes)
- `/api/pod/*` — kubectl exec/file-browser/terminal WebSocket
- `/api/gc/*` — GC log detection & download
- `/api/audit-logs` — Audit log query (admin only)

**`auth.py`** — Authentication utilities: `hash_password()`, `verify_password()`, `@admin_required` decorator. User model (`UserMixin`) lives in `server.py`.

**`profiler_backend.py`** (~1750 lines) — Core diagnostic engine with **5-layer architecture**:
- **Layer 0**: Data models — `ClusterConfig`, `PodTarget` (pure dataclasses)
- **Layer 1**: `KubectlExecutor` — kubectl primitives (exec/cp/port-forward), no business logic
- **Layer 2**: `ArthasAgentManager` — Agent lifecycle in Pod: detect → cleanup stale → start → wait ready
- **Layer 3**: `ArthasHttpClient` — Arthas HTTP API wrapper (ping/exec/session/pull output)
- **Layer 4**: `ArthasConnection` — Connection orchestration with **short-circuit reuse**: (1) HTTP reachable → reuse directly; (2) Agent running → just port-forward; (3) Full setup → agent + port-forward + ping
- **Layer 5**: `ProfilerWorkflow` — Performance analysis tasks: async-profiler (cpu/alloc/lock/wall), JDK JFR, thread dump, heap dump

**`pod_monitor.py`** (~580 lines) — Pod metrics collection via kubectl commands: CPU/memory from cgroup, process list via ps, network from /proc/net, pod status from kubectl get. Uses in-memory `dict` keyed by `{cluster}/{ns}/{pod}` for polling threads; thread-safe via `threading.Lock`.

### Multi-User Authentication (Flask-Login + bcrypt)

- **Default admin**: username `admin`, password `admin123` (auto-created on DB init)
- **User roles**: `admin` / `user` — admin sees all data, regular users see only their assigned clusters
- **Session**: Flask-Login cookie-based sessions, credentials included in requests via `{credentials: 'include'}`
- **Pages**: `login.html` → `index.html`, admin-only `static/user-management.html`, admin-only `static/audit-logs.html`

### Frontend

- `index.html` — Main SPA entry point (references `static/`)
- `static/js/app-ui.js` (~154KB) — All UI logic: clusters/diagnosis panel (46 Arthas commands, 7 collapsible groups)/monitoring dashboards/performance analysis/file browser/history
- `static/js/app-terminal.js` (~19KB) — Embedded terminal: kubectl exec interaction with Tab completion and command history
- `login.html` + `static/js/login.js` + `static/css/login.css` — Login page
- `static/user-management.html` + `static/js/user-management.js` — Admin user management page
- `static/css/app.css` — Dark theme styles

### Database (SQLite: `arthas.db`)

Tables: `users` (username/password_hash/role/status), `user_clusters` (cluster-to-user assignment), `connections` (Arthas connection records, PK: `{cluster}/{namespace}/{pod}`, has `user_id`), `arthas_commands` (command history, has `user_id`), `profiler_tasks` (sampling task history, has `user_id`), `profiler_logs` (runtime logs linked to tasks), `audit_logs` (action/resource_type/timestamp).

### Key Conventions

- **Arthas JAR detection priority**: `/app/arthas/arthas-boot.jar` > `/opt/arthas/` > `/arthas/` > `/home/admin/`
- **Profiler output naming**: `{type}-{identifier}-{podName}-{YYYYMMDDHHmmss}.{ext}`, stored in `profiler_output/`
- **Default admin account**: username `admin`, password `admin123` (auto-created on first DB init)
- **All API endpoints require `@login_required`** except auth endpoints; admin endpoints use `@admin_required`
- **Data isolation**: Non-admin users see only their assigned clusters; all queries filter by `user_id`

## Known Technical Debt (from IMPLEMENTATION_SUMMARY.md)

1. **Connection state isolation** — `profiler_backend.py`'s `ArthasConnection` uses shared state that can cause issues when multiple users switch connections concurrently. Needs refactoring to per-user/connection state.
2. **ProfilerWorkflow isolation** — Task execution depends on in-memory state; should use DB-recorded connection info instead.
3. **Metrics polling isolation** — `start_metrics_polling()` needs per-connection independent threads.
4. **No automated tests** — No test suite exists.
5. **Frontend integration incomplete** — Login page created but full integration with app-ui.js (user info display, logout button, permission-based UI hiding) is pending.
6. **Password complexity enforcement** — Not implemented.
7. **HTTPS** — Recommended for production but not enforced.

## Dependencies

Python 3.10+, kubectl 1.20+, target Pod needs Java 8+ with Arthas JAR 3.7+. Python packages: flask>=3.0.0, flask-cors>=4.0.0, flask-login>=0.6.3, bcrypt>=4.0.0.

## File Locations Reference

| File | Purpose |
|------|---------|
| `clusters.json` | Cluster config (auto-generated on first use) |
| `arthas.db` | SQLite database (auto-created) |
| `profiler_output/` | Sampling outputs (auto-created) |
| `rbac.yaml` | Minimal kubectl RBAC permissions |
| `deploy.sh` | Main deployment script (daemon/systemd/stop/install-arthas) |
