from typing import Dict, List


class HealthChecker:
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

    @classmethod
    def check_pod(cls, pod: Dict) -> Dict:
        status = pod.get("status", "")
        ready = pod.get("ready", "")
        restarts = pod.get("restarts", 0)

        if status in ("CrashLoopBackOff", "Error", "OOMKilled", "ImagePullBackOff"):
            return {"status": cls.UNHEALTHY, "issues": [f"Pod status: {status}"]}

        if status == "Running" and ready.startswith("1/"):
            if restarts > 3:
                return {"status": cls.DEGRADED, "issues": [f"High restart count: {restarts}"]}
            return {"status": cls.HEALTHY, "issues": []}

        if status == "Running" and ready.startswith("0/"):
            return {"status": cls.DEGRADED, "issues": [f"Container not ready: {ready}"]}

        if status in ("Pending", "Unknown"):
            return {"status": cls.UNKNOWN, "issues": [f"Pod status: {status}"]}

        return {"status": cls.HEALTHY, "issues": []}

    @classmethod
    def check_pod_list(cls, pods: List[Dict]) -> Dict:
        results = [cls.check_pod(p) for p in pods]
        healthy = sum(1 for r in results if r["status"] == cls.HEALTHY)
        unhealthy = sum(1 for r in results if r["status"] == cls.UNHEALTHY)
        degraded = sum(1 for r in results if r["status"] == cls.DEGRADED)
        return {
            "total": len(results),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "degraded": degraded,
            "items": results,
        }

    @classmethod
    def check_jvm(cls, dashboard_data: Dict) -> Dict:
        cpu = dashboard_data.get("cpu_percent", 0)
        memory = dashboard_data.get("memory_percent", 0)
        gc_pause = dashboard_data.get("gc_pause_ms", 0)

        issues = []
        if cpu > 90:
            issues.append(f"High CPU: {cpu}%")
        if memory > 90:
            issues.append(f"High memory: {memory}%")
        if gc_pause > 10000:
            issues.append(f"Long GC pause: {gc_pause}ms")

        if issues:
            return {"status": cls.UNHEALTHY, "issues": issues}
        if cpu > 70 or memory > 80:
            return {"status": cls.DEGRADED, "issues": [f"CPU: {cpu}%, Memory: {memory}%"]}
        return {"status": cls.HEALTHY, "issues": []}
