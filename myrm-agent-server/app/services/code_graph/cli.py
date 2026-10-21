"""
@input: 命令行参数（子命令与参数）
@output: 格式化的 JSON 结果，供 Agent 在沙箱或本地快速调用
@pos: 代码图谱 CLI 门面
"""

import argparse
import json
import os
from pathlib import Path

from app.services.code_graph.service import CodeGraphService


def get_default_db_path() -> Path:
    base = os.environ.get("MYRM_WORKSPACE_ROOT", ".")
    return Path(base) / ".myrm" / "cache" / "code_graph.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="Myrm Repo Call Graph CLI")
    parser.add_argument("--db", type=str, default=str(get_default_db_path()), help="Path to code_graph.db")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # index
    index_p = subparsers.add_parser("index")
    index_p.add_argument("--dir", type=str, default=".", help="Root directory to index")

    # reingest
    reingest_p = subparsers.add_parser("reingest")
    reingest_p.add_argument("--dir", type=str, default=".")
    reingest_p.add_argument("--file", type=str, required=True, help="Relative file path")

    # resolve
    resolve_p = subparsers.add_parser("resolve")
    resolve_p.add_argument("--target", type=str, required=True)

    # definition
    def_p = subparsers.add_parser("definition")
    def_p.add_argument("--symbol", type=str, required=True)

    # callers
    callers_p = subparsers.add_parser("callers")
    callers_p.add_argument("--callee", type=str, required=True)

    # callees
    callees_p = subparsers.add_parser("callees")
    callees_p.add_argument("--caller", type=str, required=True)

    # implementors
    imp_p = subparsers.add_parser("implementors")
    imp_p.add_argument("--type", type=str, required=True)

    # importers
    importers_p = subparsers.add_parser("importers")
    importers_p.add_argument("--module", type=str, required=True)

    # tests_reaching
    tests_p = subparsers.add_parser("tests_reaching")
    tests_p.add_argument("--target", type=str, required=True)

    args = parser.parse_args()
    service = CodeGraphService(args.db)

    if args.command == "index":
        stats = service.index_directory(args.dir)
        print(json.dumps(stats.to_dict(), indent=2, ensure_ascii=False))

    elif args.command == "reingest":
        res = service.reingest_file(args.dir, args.file)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "resolve":
        res = service.resolve(args.target)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "definition":
        res = service.definition(args.symbol)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "callers":
        res = service.callers(args.callee)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "callees":
        res = service.callees(args.caller)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "implementors":
        res = service.implementors(args.type)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "importers":
        res = service.importers(args.module)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "tests_reaching":
        res = service.tests_reaching(args.target)
        print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
