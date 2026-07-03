# Load Tests

Locust-based load tests for the K8s Arthas Tool REST API.

## Performance Targets

| Metric | Target |
|--------|--------|
| P95 response time | < 2 s |
| P99 response time | < 5 s |
| Concurrent users | 50 |
| Error rate | < 1 % |
| Requests / second | >= 20 (health + reads) |

## Quick Start

```bash
# Install locust (once)
pip install locust

# Interactive mode (opens browser UI on http://localhost:8089)
locust -f tests/load/locustfile.py --config tests/load/locust.conf

# Headless mode (CLI, for CI or quick checks)
locust -f tests/load/locustfile.py --config tests/load/locust.conf --headless

# Or via Makefile (starts the server first if not running)
make loadtest
```

The server must be running on `http://127.0.0.1:5005` before starting the
test.  Start it with:

```bash
python server.py          # default: 127.0.0.1:5005
```

## User Mix

| User class | Weight | Think time | Operations |
|-----------|--------|------------|------------|
| RegularUser | 10 | 1-3 s | health, clusters, toolbox, knowledge, cache stats |
| AdminUser | 1 | 2-5 s | audit logs, cache clear, clusters |

This means ~91 % of simulated users are regular viewers and ~9 % are admins.

## Test Scenarios (by task weight)

| Endpoint | Method | Auth | Weight | Notes |
|----------|--------|------|--------|-------|
| `/api/health` | GET | No | 5 | Highest frequency |
| `/api/clusters` | GET | Yes | 3 | Cluster list |
| `/api/toolbox/capabilities` | GET | Yes | 3 | Toolbox browse |
| `/api/knowledge/cases` | GET | Yes | 2 | Knowledge base |
| `/api/arthas/connections/health` | GET | Yes | 2 | Connection status |
| `/api/cache/stats` | GET | Yes | 1 | Cache info |
| `/api/audit-logs` | GET | Yes | 3 (admin) | Audit log query |
| `/api/cache/clear` | POST | Yes | 1 (admin) | Cache maintenance |

All endpoints are **read-only or idempotent** -- no destructive mutations.

## Results

When run in headless mode, Locust writes CSV files to `tests/load/results/`:

- `results_stats.csv` -- aggregated per-endpoint stats
- `results_stats_history.csv` -- time-series (every second)
- `results_failures.csv` -- failed requests

Example analysis:

```bash
# Quick P95 check
awk -F',' 'NR>1 && $5!="" {print $1, "P95:", $7 "ms"}' tests/load/results_stats.csv
```

## Interpreting Results

**Pass criteria** (all must hold):

1. P95 latency < 2000 ms for all endpoints
2. Error rate < 1 %
3. No sustained increase in latency over the 2 min run (memory/connection leak)
4. `POST /api/auth/login` completes within 500 ms

**Common failure modes**:

- Login returns 401 -- server not running or DB not initialised
- High P95 on `/api/clusters` -- kubectl connectivity issues (expected in
  test environments without real clusters)
- Spikes on `/api/cache/clear` -- acceptable; it is infrequent and admin-only

## Configuration

Edit `locust.conf` to adjust:

| Option | Default | Description |
|--------|---------|-------------|
| `users` | 50 | Total simulated users |
| `spawn-rate` | 5 | Users spawned per second |
| `run-time` | 2m | Total test duration |
| `headless` | true | Set false for browser UI |
| `csv` | tests/load/results | CSV output prefix |
