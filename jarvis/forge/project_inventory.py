"""ProjectInventory — multi-project awareness for Project Forge.

Scans all of Andy's project directories and maintains a SQLite inventory of:
  - Projects (name, path, language, last_modified, status)
  - Tech stack detected per project
  - Active tasks sourced from ROADMAP.md / TODO files / git log
  - Cross-project insights (shared dependencies, similar patterns)

Default scan roots (override via env vars):
  FORGE_PROJECT_ROOTS — colon-separated list of directories to scan
  Defaults to: D:/AI-Lab, C:/AI-Lab (or /mnt/d/AI-Lab, /mnt/c/AI-Lab on WSL)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_ROOTS_WIN = ["D:/AI-Lab", "C:/AI-Lab"]
_DEFAULT_ROOTS_LINUX = ["/mnt/d/AI-Lab", "/mnt/c/AI-Lab", os.path.expanduser("~/projects")]

_DEFAULT_ROOTS = (
    _DEFAULT_ROOTS_WIN if os.name == "nt" else _DEFAULT_ROOTS_LINUX
)

_INVENTORY_DB = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "project_inventory.db"
)

_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    path            TEXT NOT NULL,
    language        TEXT,
    framework       TEXT,
    status          TEXT DEFAULT 'active',
    test_count      INTEGER DEFAULT 0,
    last_modified   TEXT,
    last_scanned    TEXT,
    description     TEXT,
    tech_stack      TEXT   -- JSON array
);

CREATE TABLE IF NOT EXISTS project_tasks (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    title           TEXT NOT NULL,
    source          TEXT,   -- roadmap | todo | git_log
    status          TEXT DEFAULT 'pending',
    priority        TEXT DEFAULT 'medium',
    scanned_at      TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS cross_insights (
    id              TEXT PRIMARY KEY,
    ts              TEXT NOT NULL,
    insight_type    TEXT NOT NULL,   -- shared_dep | similar_pattern | risk
    description     TEXT NOT NULL,
    projects        TEXT,            -- JSON array of project names
    severity        TEXT DEFAULT 'info'
);
"""

# File-based signals for language/framework detection
_LANG_SIGNALS: list[tuple[str, str, str]] = [
    ("requirements.txt", "Python", "FastAPI/Flask"),
    ("pyproject.toml",   "Python", ""),
    ("setup.py",         "Python", ""),
    ("package.json",     "JavaScript/TypeScript", "Node.js"),
    ("go.mod",           "Go", ""),
    ("Cargo.toml",       "Rust", ""),
    ("build.gradle",     "Kotlin/Java", "Android/Spring"),
    ("pom.xml",          "Java", "Maven"),
    ("*.csproj",         "C#", ".NET"),
    ("Gemfile",          "Ruby", "Rails"),
]

# Patterns to skip during scanning
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".pytest_cache", "dist", "build", ".idea", ".vscode",
    "static", "coverage", ".mypy_cache",
}


@dataclass
class ProjectInfo:
    """Snapshot of a single discovered project."""
    id: str
    name: str
    path: str
    language: str
    framework: str
    status: str
    test_count: int
    last_modified: str
    tech_stack: list[str]
    description: str
    tasks: list[dict] = field(default_factory=list)


@dataclass
class InventorySummary:
    """Result of a full inventory scan."""
    projects_found: int
    projects_updated: int
    total_tasks: int
    insights: list[str]
    scan_duration_ms: int
    scan_roots: list[str]


class ProjectInventory:
    """Scans and maintains awareness of all projects in the homelab.

    Usage::

        inv = ProjectInventory()
        summary = inv.scan()
        print(summary.projects_found, summary.total_tasks)

        # Query stored projects
        projects = inv.get_projects()
        for p in projects:
            print(p.name, p.language, p.test_count)

        # Cross-project insights
        insights = inv.cross_insights()
    """

    def __init__(
        self,
        roots: list[str] | None = None,
        db_path: str | None = None,
    ):
        env_roots = os.getenv("FORGE_PROJECT_ROOTS", "")
        if env_roots:
            self._roots = [r.strip() for r in env_roots.split(":") if r.strip()]
        else:
            self._roots = roots or _DEFAULT_ROOTS

        self._db = db_path or _INVENTORY_DB
        self._init_db()

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def scan(self, max_depth: int = 2) -> InventorySummary:
        """Scan all roots, discover projects, persist to inventory DB.

        Args:
            max_depth: How many directory levels below root to search.

        Returns:
            InventorySummary with counts and cross-project insights.
        """
        start = time.monotonic()
        found = 0
        updated = 0
        total_tasks = 0

        for root in self._roots:
            if not os.path.isdir(root):
                logger.debug("ProjectInventory: root not found, skipping: %s", root)
                continue

            for project_path in self._discover_projects(root, max_depth):
                info = self._analyze_project(project_path)
                if info:
                    was_new = self._upsert_project(info)
                    found += 1
                    if was_new:
                        updated += 1
                    # Store tasks
                    self._upsert_tasks(info)
                    total_tasks += len(info.tasks)

        # Generate cross-project insights
        insights = self._generate_insights()

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "ProjectInventory scan: found=%d updated=%d tasks=%d insights=%d %.1fs",
            found, updated, total_tasks, len(insights), duration_ms / 1000,
        )
        return InventorySummary(
            projects_found=found,
            projects_updated=updated,
            total_tasks=total_tasks,
            insights=[i["description"] for i in insights],
            scan_duration_ms=duration_ms,
            scan_roots=self._roots,
        )

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def get_projects(self, status: str | None = None) -> list[ProjectInfo]:
        """Return all stored projects, optionally filtered by status."""
        conn = self._open()
        query = "SELECT * FROM projects"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY last_modified DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()

        result = []
        for row in rows:
            d = dict(row)
            tasks = self._get_tasks(d["id"])
            result.append(ProjectInfo(
                id=d["id"],
                name=d["name"],
                path=d["path"],
                language=d.get("language") or "",
                framework=d.get("framework") or "",
                status=d.get("status") or "active",
                test_count=d.get("test_count") or 0,
                last_modified=d.get("last_modified") or "",
                tech_stack=json.loads(d.get("tech_stack") or "[]"),
                description=d.get("description") or "",
                tasks=tasks,
            ))
        return result

    def get_project(self, name: str) -> ProjectInfo | None:
        """Get a single project by name."""
        all_projects = self.get_projects()
        for p in all_projects:
            if p.name.lower() == name.lower():
                return p
        return None

    def cross_insights(self) -> list[dict]:
        """Return stored cross-project insights."""
        conn = self._open()
        rows = conn.execute(
            "SELECT * FROM cross_insights ORDER BY ts DESC LIMIT 50"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def active_tasks_summary(self) -> list[dict]:
        """Return pending/in-progress tasks across all projects."""
        conn = self._open()
        rows = conn.execute(
            """
            SELECT pt.*, p.name as project_name
            FROM project_tasks pt
            JOIN projects p ON pt.project_id = p.id
            WHERE pt.status IN ('pending', 'in_progress')
            ORDER BY pt.priority DESC, p.name
            LIMIT 100
            """
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def inventory_as_dict(self) -> dict[str, Any]:
        """Return full inventory as a serializable dict (for blackboard/API)."""
        projects = self.get_projects()
        return {
            "projects": [
                {
                    "name": p.name,
                    "path": p.path,
                    "language": p.language,
                    "framework": p.framework,
                    "status": p.status,
                    "test_count": p.test_count,
                    "tech_stack": p.tech_stack,
                    "active_tasks": [t for t in p.tasks if t.get("status") == "pending"],
                }
                for p in projects
            ],
            "insights": self.cross_insights(),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Internals — discovery
    # ------------------------------------------------------------------

    def _discover_projects(self, root: str, max_depth: int) -> list[str]:
        """Find directories that look like project roots."""
        candidates = []
        root_path = Path(root)

        try:
            entries = list(root_path.iterdir())
        except PermissionError:
            return []

        for entry in entries:
            if not entry.is_dir() or entry.name in _SKIP_DIRS or entry.name.startswith("."):
                continue
            # A directory is a project if it has Python/JS/Go/etc. files
            if self._is_project_root(entry):
                candidates.append(str(entry))
            elif max_depth > 1:
                # One level deeper
                try:
                    for sub in entry.iterdir():
                        if sub.is_dir() and sub.name not in _SKIP_DIRS and not sub.name.startswith("."):
                            if self._is_project_root(sub):
                                candidates.append(str(sub))
                except PermissionError:
                    pass

        return candidates

    def _is_project_root(self, path: Path) -> bool:
        """True if directory looks like a project root."""
        signals = [
            "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
            "package.json", "go.mod", "Cargo.toml", "build.gradle",
            "pom.xml", "Makefile", "ROADMAP.md", "README.md",
        ]
        try:
            names = {f.name for f in path.iterdir() if f.is_file()}
        except PermissionError:
            return False
        return bool(names & set(signals))

    def _analyze_project(self, path: str) -> ProjectInfo | None:
        """Analyze a project directory and return a ProjectInfo."""
        p = Path(path)
        name = p.name

        language, framework = self._detect_language(p)
        tech_stack = self._detect_tech_stack(p)
        test_count = self._count_tests(p)
        description = self._read_description(p)
        last_modified = self._last_modified(p)
        tasks = self._extract_tasks(p)

        return ProjectInfo(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, path)),
            name=name,
            path=path,
            language=language,
            framework=framework,
            status="active",
            test_count=test_count,
            last_modified=last_modified,
            tech_stack=tech_stack,
            description=description,
            tasks=tasks,
        )

    def _detect_language(self, p: Path) -> tuple[str, str]:
        try:
            names = {f.name for f in p.iterdir() if f.is_file()}
        except PermissionError:
            return "", ""

        for signal, lang, fw in _LANG_SIGNALS:
            if "*" in signal:
                ext = signal.replace("*", "")
                if any(n.endswith(ext) for n in names):
                    return lang, fw
            elif signal in names:
                # Try to detect framework from requirements
                if lang == "Python" and "requirements.txt" in names:
                    try:
                        req_text = (p / "requirements.txt").read_text(errors="ignore").lower()
                        if "fastapi" in req_text:
                            fw = "FastAPI"
                        elif "flask" in req_text:
                            fw = "Flask"
                        elif "django" in req_text:
                            fw = "Django"
                    except Exception:
                        pass
                return lang, fw
        return "", ""

    def _detect_tech_stack(self, p: Path) -> list[str]:
        stack: set[str] = set()
        try:
            names = {f.name for f in p.iterdir() if f.is_file()}
        except PermissionError:
            return []

        if "requirements.txt" in names:
            try:
                text = (p / "requirements.txt").read_text(errors="ignore").lower()
                for pkg in ["fastapi", "flask", "django", "sqlalchemy", "redis", "celery",
                            "pytest", "pydantic", "httpx", "aiohttp", "anthropic", "ollama"]:
                    if pkg in text:
                        stack.add(pkg)
            except Exception:
                pass
        if "package.json" in names:
            try:
                data = json.loads((p / "package.json").read_text(errors="ignore"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for dep in ["react", "vue", "angular", "next", "vite", "tailwindcss"]:
                    if dep in deps:
                        stack.add(dep)
            except Exception:
                pass
        if "go.mod" in names:
            stack.add("go")
        if "Cargo.toml" in names:
            stack.add("rust")

        return sorted(stack)

    def _count_tests(self, p: Path) -> int:
        count = 0
        tests_dir = p / "tests"
        if tests_dir.is_dir():
            try:
                for f in tests_dir.rglob("test_*.py"):
                    try:
                        text = f.read_text(errors="ignore")
                        count += text.count("def test_")
                    except Exception:
                        pass
            except PermissionError:
                pass
        return count

    def _read_description(self, p: Path) -> str:
        for fname in ("README.md", "readme.md", "README.txt"):
            readme = p / fname
            if readme.exists():
                try:
                    text = readme.read_text(errors="ignore")
                    # First non-empty paragraph after headers
                    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
                    if lines:
                        return lines[0][:200]
                except Exception:
                    pass
        return ""

    def _last_modified(self, p: Path) -> str:
        try:
            mtime = max(
                f.stat().st_mtime
                for f in p.rglob("*.py")
                if ".git" not in str(f) and "__pycache__" not in str(f)
            )
            return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except (ValueError, PermissionError):
            try:
                return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
            except Exception:
                return ""

    def _extract_tasks(self, p: Path) -> list[dict]:
        tasks = []

        # From ROADMAP.md — look for incomplete phases
        roadmap = p / "ROADMAP.md"
        if roadmap.exists():
            try:
                text = roadmap.read_text(errors="ignore")
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("- [ ]") or ("PLANNED" in stripped and "░" in stripped):
                        title = re.sub(r"^[-*]\s*\[[ x]\]\s*", "", stripped)
                        if title:
                            tasks.append({
                                "title": title[:200],
                                "source": "roadmap",
                                "status": "pending",
                                "priority": "medium",
                            })
            except Exception:
                pass

        # From TODO/FIXME in source files (sample, not exhaustive)
        for pattern in ("TODO", "FIXME", "HACK"):
            try:
                for pyfile in list(p.rglob("*.py"))[:50]:
                    if ".git" in str(pyfile) or "__pycache__" in str(pyfile):
                        continue
                    try:
                        text = pyfile.read_text(errors="ignore")
                        for m in re.finditer(rf"{pattern}[:\s]+(.+)", text):
                            todo_text = m.group(1).strip()
                            if todo_text and len(todo_text) > 5:
                                tasks.append({
                                    "title": f"{pattern}: {todo_text[:150]}",
                                    "source": f"{pyfile.name}",
                                    "status": "pending",
                                    "priority": "high" if pattern == "FIXME" else "low",
                                })
                    except Exception:
                        pass
            except PermissionError:
                pass

        return tasks[:50]  # cap per project

    # ------------------------------------------------------------------
    # Internals — persistence
    # ------------------------------------------------------------------

    def _upsert_project(self, info: ProjectInfo) -> bool:
        """Upsert a project. Returns True if this was a new project."""
        conn = self._open()
        # Check by id OR name (name is unique, id is derived from path)
        existing = conn.execute(
            "SELECT id FROM projects WHERE id = ? OR name = ?", (info.id, info.name)
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()
        if existing:
            existing_id = existing[0]
            conn.execute(
                """
                UPDATE projects
                SET name=?, path=?, language=?, framework=?, test_count=?,
                    last_modified=?, last_scanned=?, description=?, tech_stack=?
                WHERE id=?
                """,
                (
                    info.name, info.path, info.language, info.framework,
                    info.test_count, info.last_modified, now,
                    info.description, json.dumps(info.tech_stack), existing_id,
                ),
            )
            conn.commit()
            conn.close()
            return False
        else:
            conn.execute(
                """
                INSERT INTO projects
                  (id, name, path, language, framework, test_count, last_modified,
                   last_scanned, description, tech_stack)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    info.id, info.name, info.path, info.language, info.framework,
                    info.test_count, info.last_modified, now,
                    info.description, json.dumps(info.tech_stack),
                ),
            )
            conn.commit()
            conn.close()
            return True

    def _upsert_tasks(self, info: ProjectInfo) -> None:
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat()
        # Delete old tasks for this project, re-insert fresh
        conn.execute("DELETE FROM project_tasks WHERE project_id = ?", (info.id,))
        for task in info.tasks:
            conn.execute(
                "INSERT INTO project_tasks (id, project_id, title, source, status, priority, scanned_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), info.id,
                    task["title"], task.get("source", ""),
                    task.get("status", "pending"), task.get("priority", "medium"),
                    now,
                ),
            )
        conn.commit()
        conn.close()

    def _get_tasks(self, project_id: str) -> list[dict]:
        conn = self._open()
        rows = conn.execute(
            "SELECT * FROM project_tasks WHERE project_id = ? ORDER BY priority DESC LIMIT 20",
            (project_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _generate_insights(self) -> list[dict]:
        """Generate cross-project insights and persist them."""
        projects = self.get_projects()
        insights: list[dict] = []

        # Shared dependencies
        dep_map: dict[str, list[str]] = {}
        for p in projects:
            for dep in p.tech_stack:
                dep_map.setdefault(dep, []).append(p.name)

        for dep, proj_names in dep_map.items():
            if len(proj_names) >= 2:
                description = f"Shared dependency '{dep}' in: {', '.join(proj_names)}"
                insights.append({
                    "type": "shared_dep",
                    "description": description,
                    "projects": proj_names,
                    "severity": "info",
                })

        # Projects with zero tests
        no_tests = [p.name for p in projects if p.test_count == 0 and p.language]
        if no_tests:
            insights.append({
                "type": "risk",
                "description": f"Projects with no tests: {', '.join(no_tests)}",
                "projects": no_tests,
                "severity": "warning",
            })

        # Persist
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat()
        for ins in insights[:20]:
            conn.execute(
                "INSERT OR IGNORE INTO cross_insights (id, ts, insight_type, description, projects, severity)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid5(uuid.NAMESPACE_URL, ins["description"])),
                    now, ins["type"], ins["description"],
                    json.dumps(ins.get("projects", [])), ins.get("severity", "info"),
                ),
            )
        conn.commit()
        conn.close()

        return insights

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self._db), exist_ok=True)
        conn = self._open()
        conn.executescript(_DDL)
        conn.commit()
        conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
