from typing import List, Dict


class StructuredOutput:
    @staticmethod
    def parse_pod_list(raw: str) -> List[Dict]:
        if not raw.strip():
            return []
        lines = [l for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return []
        pods = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 5:
                pods.append({
                    "name": parts[0],
                    "ready": parts[1],
                    "status": parts[2],
                    "restarts": int(parts[3]) if parts[3].isdigit() else 0,
                    "age": parts[4],
                })
        return pods

    @staticmethod
    def parse_top_pods(raw: str) -> List[Dict]:
        if not raw.strip():
            return []
        lines = [l for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return []
        pods = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 3:
                pods.append({
                    "name": parts[0],
                    "cpu": parts[1],
                    "memory": parts[2],
                })
        return pods

    @staticmethod
    def parse_top_nodes(raw: str) -> List[Dict]:
        if not raw.strip():
            return []
        lines = [l for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return []
        nodes = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 5:
                nodes.append({
                    "name": parts[0],
                    "cpu_usage": parts[1],
                    "cpu_percent": parts[2],
                    "memory_usage": parts[3],
                    "memory_percent": parts[4],
                })
        return nodes

    @classmethod
    def parse_output(cls, raw: str, command: str) -> any:
        parsers = {
            "get_pods": cls.parse_pod_list,
            "top_pods": cls.parse_top_pods,
            "top_nodes": cls.parse_top_nodes,
        }
        parser = parsers.get(command)
        if parser:
            return parser(raw)
        return {"raw": raw}
