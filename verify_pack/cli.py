"""CLI: python -m verify_pack scan SESSION"""

from __future__ import annotations

import sys
from pathlib import Path

from verify_pack.scan import dump, exit_code, format_report, scan_path

_FLAGS = {"--json", "--strict", "--help", "-h", "scan"}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(arg.startswith("-") and arg not in _FLAGS for arg in args):
        unknown = next(arg for arg in args if arg.startswith("-") and arg not in _FLAGS)
        print(f"unknown flag: {unknown}", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    if "--help" in args or "-h" in args or not args:
        print(_usage(), file=sys.stdout if args else sys.stderr)
        return 0 if args else 2
    as_json = "--json" in args
    strict = "--strict" in args
    paths = [Path(arg) for arg in args if arg not in _FLAGS]
    if not paths:
        print(_usage(), file=sys.stderr)
        return 2
    try:
        reports = [scan_path(path) for path in paths]
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(dump(reports) if as_json else format_report(reports))
    return exit_code(reports, strict=strict)


def _usage() -> str:
    return """verify-pack scan PATH...

Check completion claims against earlier tool commands. Exit 1 when a claim
has no earlier successful command. --strict also exits 1 when a claim check
is unknown. --json prints one object, or a list for several paths.

  verify-pack scan examples/unbacked.json
  verify-pack scan examples/backed.json --json
  python3 -m verify_pack scan session.jsonl --strict

PATH may be ATIF JSON, claim-ledger JSONL, Grok chat_history.jsonl, a Grok
session directory, or Claude Code session JSONL.
"""
