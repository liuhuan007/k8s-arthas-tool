# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

K8s Arthas Tool is a Java performance diagnosis platform for Kubernetes Pods. It combines Alibaba Arthas and async-profiler with kubectl to enable zero-intrusion diagnostics without code changes or service restarts.

## Common Commands

### Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (default 127.0.0.1:5001)
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
  -p 5001:5001 \
  -v ~/.kube:/root/.kube:ro \
  -v $(pwd)/profiler_output:/app/profiler_output \
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

All outputs saved to `profiler_output/`.

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
- `profiler_output/` - Sampling outputs (auto-created)
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

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
