"""命令行：不开网页也能批量导入、出复盘报告。

    python -m scout.cli report            # 漏斗 + 未通过原因
    python -m scout.cli checklist         # 初筛清单 Markdown
    python -m scout.cli import data.json  # 覆盖导入
    python -m scout.cli export out.json
"""

import argparse
import json
import sys
from pathlib import Path

from . import engine
from .store import Store, validate


def main(argv=None):
    ap = argparse.ArgumentParser(prog="scout")
    ap.add_argument("--db", default="scout.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    sub.add_parser("checklist")
    sub.add_parser("import").add_argument("file")
    sub.add_parser("export").add_argument("file")
    args = ap.parse_args(argv)

    store = Store(args.db)
    if args.cmd == "import":
        items = json.loads(Path(args.file).read_text(encoding="utf-8"))
        n = len(store.replace_all([validate(p) for p in items]))
        print(f"已导入 {n} 个项目")
    elif args.cmd == "export":
        Path(args.file).write_text(json.dumps(store.list(), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已导出到 {args.file}")
    elif args.cmd == "checklist":
        sys.stdout.write(engine.checklist_markdown(store.list()))
    else:
        s = engine.summary(store.list())
        print("筛选漏斗")
        for name, n in s["funnel"]:
            print(f"  {name:<8}{n:>4}")
        print(f"未通过原因（共 {s['rejected']} 个项目）")
        for reason, n in s["reasons"]:
            print(f"  {reason:<14}{n:>4}")


if __name__ == "__main__":
    main()
