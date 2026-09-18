"""SQLite 文档存储：每个项目一行 JSON。项目字段还在变，先不拆表。"""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .criteria import DECISIONS, L1, L1_VALUES, L2, blank_scores

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_projects.json"


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL)")

    @contextmanager
    def _conn(self):
        # sqlite3 的 with 只管事务不关连接；Windows 上不关会锁住文件
        conn = sqlite3.connect(self.path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def list(self):
        with self._conn() as c:
            rows = c.execute("SELECT data FROM projects ORDER BY rowid DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def get(self, pid):
        with self._conn() as c:
            row = c.execute("SELECT data FROM projects WHERE id = ?", (pid,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, p):
        p = validate(p)
        with self._conn() as c:
            c.execute(
                "INSERT INTO projects (id, data, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
                (p["id"], json.dumps(p, ensure_ascii=False), time.time()),
            )
        return p

    def delete(self, pid):
        with self._conn() as c:
            return c.execute("DELETE FROM projects WHERE id = ?", (pid,)).rowcount > 0

    def replace_all(self, projects):
        with self._conn() as c:
            c.execute("DELETE FROM projects")
        return [self.save(p) for p in reversed(projects)]

    def seed_if_empty(self):
        if not self.list() and SAMPLE.exists():
            self.replace_all(json.loads(SAMPLE.read_text(encoding="utf-8")))


def new_project(**fields):
    l1, l2 = blank_scores()
    p = {"id": uuid.uuid4().hex[:10], "name": "", "track": "", "stage": "", "contact": "",
         "date": time.strftime("%Y-%m-%d"), "pitch": "", "transcript": "", "l1": l1, "l2": l2, "decision": ""}
    p.update(fields)
    return validate(p)


def validate(p):
    """把外部输入（前端、导入文件）收敛成合法结构；非法值直接报错而不是静默修正。"""
    if not isinstance(p, dict):
        raise ValueError("项目必须是对象")
    l1d, l2d = blank_scores()
    out = {k: str(p.get(k, "") or "") for k in ("name", "track", "stage", "contact", "date", "pitch", "transcript")}
    out["id"] = str(p.get("id") or uuid.uuid4().hex[:10])
    out["example"] = bool(p.get("example", False))
    out["l1"], out["l2"] = {}, {}
    for c in L1:
        item = {**l1d[c["key"]], **(p.get("l1", {}).get(c["key"]) or {})}
        if item["v"] not in L1_VALUES:
            raise ValueError(f"{c['title']} 的取值必须是 {L1_VALUES} 之一")
        out["l1"][c["key"]] = {"v": item["v"], "e": str(item["e"] or "")}
    for c in L2:
        item = {**l2d[c["key"]], **(p.get("l2", {}).get(c["key"]) or {})}
        v = int(item["v"] or 0)
        if not 0 <= v <= 5:
            raise ValueError(f"{c['title']} 的分数必须在 0-5 之间（0 表示未打分）")
        out["l2"][c["key"]] = {"v": v, "e": str(item["e"] or "")}
    out["decision"] = p.get("decision") or ""
    if out["decision"] not in DECISIONS:
        raise ValueError(f"决定必须是 {DECISIONS} 之一")
    return out
