#! /usr/bin/env python3
"""SkillMarketplace 服务 - 市场源管理、同步、安装、版本更新"""
import json
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from models.db import get_db
from services.skill_registry import get_skill_registry

log = logging.getLogger(__name__)


class SkillMarketplace:
    """Skill 市场管理"""

    def __init__(self):
        self.db = get_db()
        self._sync_tasks: Dict[int, dict] = {}
        self._lock = threading.Lock()

    # ── 来源管理 ────────────────────────────────────────────────────────────

    def add_source(self, name: str, repo_url: str, branch: str = "main") -> int:
        return self.db.insert("skill_marketplace", {
            "name": name, "repo_url": repo_url, "branch": branch
        })

    def update_source(self, source_id: int, name: str = None, repo_url: str = None, branch: str = None) -> bool:
        updates = {}
        if name is not None:
            updates["name"] = name
        if repo_url is not None:
            updates["repo_url"] = repo_url
        if branch is not None:
            updates["branch"] = branch
        if not updates:
            return False
        self.db.execute(
            f"UPDATE skill_marketplace SET {', '.join(f'{k}=?' for k in updates)} WHERE id = ?",
            tuple(updates.values()) + (source_id,)
        )
        return True

    def remove_source(self, source_id: int) -> bool:
        self.db.execute("DELETE FROM skill_marketplace WHERE id = ?", (source_id,))
        self.db.execute(
            "UPDATE skill_registry SET marketplace_id = NULL WHERE marketplace_id = ?",
            (source_id,)
        )
        return True

    def list_sources(self) -> List[Dict]:
        rows = self.db.fetch_all("SELECT * FROM skill_marketplace ORDER BY name")
        for r in rows:
            try:
                r["skill_count"] = len(json.loads(r.get("skills_cache") or "[]"))
            except (json.JSONDecodeError, TypeError):
                r["skill_count"] = 0
        return rows

    def get_source(self, source_id: int) -> Optional[Dict]:
        return self.db.fetch_one("SELECT * FROM skill_marketplace WHERE id = ?", (source_id,))

    # ── 同步 ────────────────────────────────────────────────────────────────

    def sync_source(self, source_id: int) -> dict:
        source = self.get_source(source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="skill_mkt_")
            repo_url = source["repo_url"]
            branch = source.get("branch", "main")

            result = subprocess.run(
                ["git", "clone", "--depth", "1", "-b", branch, repo_url, temp_dir],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

            skills = self._scan_repo(temp_dir)

            self.db.execute(
                "UPDATE skill_marketplace SET skills_cache = ?, last_sync_at = ? WHERE id = ?",
                (json.dumps(skills), datetime.now().isoformat(), source_id)
            )

            return {"skill_count": len(skills), "skills": skills}

        finally:
            if temp_dir and os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ── 异步同步 ──────────────────────────────────────────────────────────

    def sync_source_async(self, source_id: int) -> dict:
        """启动后台同步，立即返回状态"""
        with self._lock:
            if source_id in self._sync_tasks and self._sync_tasks[source_id].get("status") in ("running",):
                return {"status": "running", "message": "同步正在进行中"}
            self._sync_tasks[source_id] = {"status": "running", "message": "同步中..."}

        def _run():
            try:
                result = self.sync_source(source_id)
                with self._lock:
                    self._sync_tasks[source_id] = {
                        "status": "done",
                        "message": f"同步成功，发现 {result['skill_count']} 个技能",
                        "result": result,
                    }
            except Exception as e:
                log.error("Async sync source %s failed: %s", source_id, e)
                with self._lock:
                    self._sync_tasks[source_id] = {
                        "status": "error",
                        "message": f"同步失败: {e}",
                    }

        t = threading.Thread(target=_run, daemon=True, name=f"sync-source-{source_id}")
        t.start()
        return {"status": "started", "message": "同步已启动"}

    def get_sync_status(self, source_id: int) -> dict:
        """查询同步状态"""
        with self._lock:
            status = self._sync_tasks.get(source_id)
            if not status:
                return {"status": "idle", "message": "无同步任务"}
            return dict(status)

    def _scan_repo(self, repo_path: str) -> List[Dict]:
        skills = []

        index_file = Path(repo_path) / "marketplace.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for s in data:
                        s.setdefault("path", s.get("name", ""))
                    return data
                if isinstance(data, dict) and "plugins" in data:
                    for plugin in data["plugins"]:
                        source = plugin.get("source", "").lstrip("./")
                        plugin_dir = Path(repo_path) / source
                        if plugin_dir.is_dir():
                            plugin_skills = self._scan_plugin_dir(plugin_dir, source)
                            skills.extend(plugin_skills)
                    return skills
            except (json.JSONDecodeError, IOError):
                log.warning("marketplace.json parse failed, fallback to dir scan")

        for subdir in sorted(Path(repo_path).iterdir()):
            if not subdir.is_dir() or subdir.name.startswith("."):
                continue
            skill = self._scan_subdir(subdir)
            if skill:
                skills.append(skill)
            else:
                plugin_skills = self._scan_plugin_dir(subdir, subdir.name)
                skills.extend(plugin_skills)

        return skills

    def _scan_plugin_dir(self, plugin_dir: Path, prefix: str = "") -> List[Dict]:
        """Scan Claude Code plugin directory for skills in commands/ and skills/ subdirs."""
        skills = []
        for sub_name in ("commands", "skills"):
            sub_path = plugin_dir / sub_name
            if not sub_path.is_dir():
                continue
            for entry in sorted(sub_path.iterdir()):
                if entry.is_file() and entry.suffix == ".md":
                    meta = self._parse_markdown_meta(entry.read_text(encoding="utf-8"))
                    if meta is not None:
                        if not meta.get("name"):
                            meta["name"] = entry.stem
                        meta["path"] = f"{prefix}/{sub_name}/{entry.name}"
                        skills.append(meta)
                elif entry.is_dir():
                    skill = self._scan_subdir(entry)
                    if skill:
                        skill["path"] = f"{prefix}/{sub_name}/{entry.name}"
                        skills.append(skill)
        return skills

    def _scan_subdir(self, subdir: Path) -> Optional[Dict]:
        for pattern in ["SKILL.md", "skill.json", "skill.yaml", "skill.yml"]:
            fp = subdir / pattern
            if fp.exists():
                content = fp.read_text(encoding="utf-8")
                meta = self._parse_skill_meta(content, fp.suffix)
                if meta and meta.get("name"):
                    meta["path"] = subdir.name
                    return meta

        import glob
        for pattern in ["*.skill.json", "*.skill.yaml", "*.skill.yml"]:
            matches = list(subdir.glob(pattern))
            if matches:
                fp = matches[0]
                content = fp.read_text(encoding="utf-8")
                meta = self._parse_skill_meta(content, fp.suffix)
                if meta and meta.get("name"):
                    meta["path"] = subdir.name
                    return meta

        return None

    def _parse_skill_meta(self, content: str, suffix: str) -> Optional[Dict]:
        try:
            if suffix in (".yaml", ".yml"):
                import yaml
                return yaml.safe_load(content)
            elif suffix == ".json":
                return json.loads(content)
            elif suffix == ".md":
                return self._parse_markdown_meta(content)
        except Exception:
            return None

    def _parse_markdown_meta(self, content: str) -> Optional[Dict]:
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                meta = {}
                for line in content[3:end].strip().splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        meta[k.strip()] = v.strip().strip('"').strip("'")
                return meta
        return {}

    # ── 浏览 ────────────────────────────────────────────────────────────────

    def browse(self, source_id: int = None, keyword: str = None, category: str = None) -> List[Dict]:
        if source_id:
            sources = [self.get_source(source_id)]
        else:
            sources = self.list_sources()

        # Pre-fetch installed skills from registry for status matching
        installed = self.db.fetch_all(
            "SELECT name, version, marketplace_id, id AS skill_id FROM skill_registry WHERE marketplace_id IS NOT NULL"
        )
        installed_map = {}
        for sk in installed:
            key = (sk["marketplace_id"], sk["name"])
            installed_map[key] = {"skill_id": sk["skill_id"], "version": sk["version"]}

        results = []
        for src in sources:
            if not src or not src.get("skills_cache"):
                continue
            try:
                skills = json.loads(src["skills_cache"])
            except (json.JSONDecodeError, TypeError):
                continue
            for s in skills:
                s["source_id"] = src["id"]
                s["source_name"] = src["name"]
                s["installed"] = False
                s["latest"] = None
                s["skill_id"] = None
                key = (src["id"], s.get("name"))
                if key in installed_map:
                    installed_skill = installed_map[key]
                    s["installed"] = True
                    s["skill_id"] = installed_skill["skill_id"]
                    if s.get("version") and installed_skill["version"] != s["version"]:
                        s["current"] = installed_skill["version"]
                        s["latest"] = s["version"]
                        s["version"] = installed_skill["version"]
                if keyword:
                    kw = keyword.lower()
                    if kw not in (s.get("name") or "").lower() and kw not in (s.get("description") or "").lower():
                        continue
                if category and s.get("category") != category:
                    continue
                results.append(s)

        return results

    # ── 安装 ────────────────────────────────────────────────────────────────

    def install(self, source_id: int, skill_name: str, created_by: int = None) -> int:
        source = self.get_source(source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        skills_cache = json.loads(source["skills_cache"] or "[]")
        entry = next((s for s in skills_cache if s.get("name") == skill_name), None)
        if not entry:
            raise ValueError(f"Skill '{skill_name}' not found in source {source_id}")

        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="skill_inst_")
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "-b", source["branch"], source["repo_url"], temp_dir],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

            skill_dir = Path(temp_dir) / entry["path"]
            skill_data = self._load_skill_file(skill_dir)
            if not skill_data:
                raise ValueError(f"No skill definition found in {skill_dir}")

            skill_data["source"] = "marketplace"
            skill_data["marketplace_id"] = source_id

            registry = get_skill_registry()
            return registry.import_skill(skill_data, created_by)

        finally:
            if temp_dir and os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _load_skill_file(self, skill_dir: Path) -> Optional[Dict]:
        if skill_dir.is_file() and skill_dir.suffix == ".md":
            content = skill_dir.read_text(encoding="utf-8")
            meta = self._parse_markdown_meta(content)
            if meta is not None:
                if not meta.get("name"):
                    meta["name"] = skill_dir.stem
                return meta
        if not skill_dir.is_dir():
            skill_dir = skill_dir.parent
        for pattern in ["SKILL.md", "skill.json", "skill.yaml", "skill.yml"]:
            fp = skill_dir / pattern
            if fp.exists():
                content = fp.read_text(encoding="utf-8")
                return self._parse_skill_meta(content, fp.suffix)
        import glob as _glob
        for pattern in ["*.skill.json", "*.skill.yaml", "*.skill.yml"]:
            matches = list(skill_dir.glob(pattern))
            if matches:
                content = matches[0].read_text(encoding="utf-8")
                return self._parse_skill_meta(content, matches[0].suffix)
        return None

    # ── 版本更新 ────────────────────────────────────────────────────────────

    def check_updates(self) -> List[Dict]:
        updates = []
        installed = self.db.fetch_all(
            "SELECT id, name, version, marketplace_id FROM skill_registry WHERE marketplace_id IS NOT NULL"
        )
        for skill in installed:
            src = self.get_source(skill["marketplace_id"])
            if not src or not src.get("skills_cache"):
                continue
            try:
                cache = json.loads(src["skills_cache"])
            except (json.JSONDecodeError, TypeError):
                continue
            entry = next((s for s in cache if s.get("name") == skill["name"]), None)
            if entry and entry.get("version") and entry["version"] != skill["version"]:
                updates.append({
                    "skill_id": skill["id"],
                    "name": skill["name"],
                    "current_version": skill["version"],
                    "latest_version": entry["version"],
                    "source_id": skill["marketplace_id"],
                    "source_name": src["name"],
                })
        return updates

    def update_skill(self, skill_id: int, created_by: int = None) -> int:
        skill = self.db.fetch_one("SELECT * FROM skill_registry WHERE id = ?", (skill_id,))
        if not skill:
            raise ValueError(f"Skill {skill_id} not found")
        if not skill.get("marketplace_id"):
            raise ValueError(f"Skill {skill_id} is not from marketplace")

        return self.install(skill["marketplace_id"], skill["name"], created_by)


# 全局实例
_marketplace: Optional[SkillMarketplace] = None


def get_skill_marketplace() -> SkillMarketplace:
    global _marketplace
    if _marketplace is None:
        _marketplace = SkillMarketplace()
    return _marketplace
