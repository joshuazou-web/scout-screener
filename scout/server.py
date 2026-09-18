"""零依赖 HTTP 服务：JSON API + 静态前端。

    python -m scout.server --port 8000 --db scout.db
"""

import argparse
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import criteria, engine, extract
from .store import Store, new_project, validate

WEB = Path(__file__).resolve().parent.parent / "web"


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        # ---- helpers ----
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def _route(self, method):
            path = self.path.split("?")[0]
            try:
                if not path.startswith("/api/"):
                    return self._static(path) if method == "GET" else self._send(405, {"error": "不支持"})
                for pattern, handlers in ROUTES:
                    m = re.fullmatch(pattern, path)
                    if m and method in handlers:
                        return handlers[method](self, *m.groups())
                self._send(404, {"error": "接口不存在"})
            except (ValueError, json.JSONDecodeError) as e:
                self._send(400, {"error": str(e)})

        def _static(self, path):
            f = (WEB / (path.lstrip("/") or "index.html")).resolve()
            if WEB not in f.parents or not f.is_file():
                return self._send(404, {"error": "文件不存在"})
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def do_PUT(self):
            self._route("PUT")

        def do_DELETE(self):
            self._route("DELETE")

        # ---- API ----
        def get_criteria(self):
            self._send(200, criteria.as_dict())

        def list_projects(self):
            self._send(200, [engine.annotate(p) for p in store.list()])

        def create_project(self):
            self._send(201, engine.annotate(store.save(new_project(**self._body()))))

        def update_project(self, pid):
            if not store.get(pid):
                return self._send(404, {"error": "项目不存在"})
            self._send(200, engine.annotate(store.save({**self._body(), "id": pid})))

        def delete_project(self, pid):
            self._send(200 if store.delete(pid) else 404, {"ok": True})

        def extract_evidence(self, pid):
            p = store.get(pid)
            if not p:
                return self._send(404, {"error": "项目不存在"})
            transcript = self._body().get("transcript", p.get("transcript", ""))
            store.save({**p, "transcript": transcript})
            self._send(200, extract.suggest(transcript))

        def report(self):
            ps = store.list()
            self._send(200, {**engine.summary(ps), "checklist": engine.checklist_markdown(ps)})

        def export_all(self):
            self._send(200, store.list())

        def import_all(self):
            items = self._body()
            if not isinstance(items, list):
                raise ValueError("导入内容必须是项目数组")
            self._send(200, {"count": len(store.replace_all([validate(p) for p in items]))})

        def reset_sample(self):
            store.replace_all([])
            store.seed_if_empty()
            self._send(200, {"count": len(store.list())})

    ROUTES = [
        (r"/api/criteria", {"GET": Handler.get_criteria}),
        (r"/api/projects", {"GET": Handler.list_projects, "POST": Handler.create_project}),
        (r"/api/projects/([\w-]+)", {"PUT": Handler.update_project, "DELETE": Handler.delete_project}),
        (r"/api/projects/([\w-]+)/extract", {"POST": Handler.extract_evidence}),
        (r"/api/report", {"GET": Handler.report}),
        (r"/api/export", {"GET": Handler.export_all}),
        (r"/api/import", {"POST": Handler.import_all}),
        (r"/api/reset-sample", {"POST": Handler.reset_sample}),
    ]
    return Handler


def main():
    ap = argparse.ArgumentParser(description="Scout 项目筛选台")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--db", default="scout.db")
    args = ap.parse_args()
    store = Store(args.db)
    store.seed_if_empty()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    print(f"Scout 筛选台已启动：http://127.0.0.1:{args.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
