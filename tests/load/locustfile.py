"""Load tests for K8s Arthas Tool API.

Run:
    locust -f tests/load/locustfile.py --config tests/load/locust.conf

Or headless (CI):
    locust -f tests/load/locustfile.py --config tests/load/locust.conf --headless
"""
from locust import HttpUser, task, between, events


class RegularUser(HttpUser):
    """Simulates a typical read-heavy user of the K8s Arthas Tool.

    Workflow: login -> browse clusters, view connections, check toolbox.
    """
    wait_time = between(1, 3)  # 1-3s think time between requests
    host = "http://127.0.0.1:5005"

    def on_start(self):
        """Login at session start. Flask-login sets a session cookie
        automatically; Locust's ``HttpUser`` sends it on subsequent requests."""
        with self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Login failed: {resp.status_code}")
            elif not resp.json().get("ok"):
                resp.failure("Login returned ok=false")

    # ------------------------------------------------------------------ #
    # Read-heavy tasks (highest weight)
    # ------------------------------------------------------------------ #

    @task(5)
    def health_check(self):
        """Health check - no auth, highest frequency."""
        self.client.get("/api/health", name="/api/health")

    @task(3)
    def list_clusters(self):
        """List clusters - core navigation."""
        self.client.get("/api/clusters", name="/api/clusters")

    @task(3)
    def toolbox_capabilities(self):
        """List toolbox capabilities - frequent browse."""
        self.client.get(
            "/api/toolbox/capabilities", name="/api/toolbox/capabilities"
        )

    @task(2)
    def knowledge_cases(self):
        """List knowledge cases."""
        self.client.get("/api/knowledge/cases", name="/api/knowledge/cases")

    @task(2)
    def arthas_connection_health(self):
        """Check Arthas connection health status."""
        self.client.get(
            "/api/arthas/connections/health",
            name="/api/arthas/connections/health",
        )

    @task(1)
    def cache_stats(self):
        """View cache statistics."""
        self.client.get("/api/cache/stats", name="/api/cache/stats")


class AdminUser(HttpUser):
    """Simulates admin operations (audit logs, cache management).

    Lower weight: fewer admins than regular users.
    """
    wait_time = between(2, 5)  # longer think time
    weight = 1                  # 1 admin per 10 regular users
    host = "http://127.0.0.1:5005"

    def on_start(self):
        with self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
            name="/api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Login failed: {resp.status_code}")

    @task(3)
    def list_audit_logs(self):
        """List audit logs - admin-only view."""
        self.client.get("/api/audit-logs", name="/api/audit-logs")

    @task(2)
    def cache_stats(self):
        """View cache stats."""
        self.client.get("/api/cache/stats", name="/api/cache/stats")

    @task(1)
    def clear_cache(self):
        """Clear cache (POST, but safe/idempotent)."""
        self.client.post("/api/cache/clear", name="/api/cache/clear")

    @task(2)
    def list_clusters(self):
        """List clusters (admin sees all)."""
        self.client.get("/api/clusters", name="/api/clusters")
