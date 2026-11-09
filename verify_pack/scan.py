"""Run the pack and render the short report."""

from __future__ import annotations

import json
from pathlib import Path

from atif_scan import Engine, Status
from atif_scan.data.loader import TraceError, parse_trace

from verify_pack.claims import checks
from verify_pack.convert import load_atif

MEDIUM = 50


def scan_path(path: Path) -> dict:
    try:
        document = load_atif(path)
        trace = parse_trace(document)
    except TraceError as exc:
        raise ValueError(f"{path}: {exc}") from exc
    engine = Engine(checks())
    rows = []
    findings = []
    signals = []
    unknown = []
    numbers = trace.step_numbers() if callable(trace.step_numbers) else trace.step_numbers
    for assessment in engine.evaluate(trace):
        status = assessment.result.status
        if status == Status.NO_MATCH:
            continue
        evidence = [
            {
                "step_id": numbers[item.step] if item.step < len(numbers) else None,
                "channel": item.channel.value,
            }
            for item in assessment.result.evidence
        ]
        row = {
            "id": assessment.spec.id,
            "title": assessment.spec.title,
            "status": status.value,
            "severity": assessment.spec.severity.name.lower(),
            "score": int(assessment.spec.severity),
            "evidence": evidence,
        }
        rows.append(row)
        if assessment.spec.id.endswith("_unbacked"):
            if status == Status.MATCH:
                findings.append(row)
            elif status == Status.UNKNOWN:
                unknown.append(row)
        elif status == Status.MATCH:
            signals.append(row)
    score = max((row["score"] for row in findings), default=0)
    names = {25: "low", 50: "medium", 75: "high", 100: "critical"}
    return {
        "input": str(path),
        "score": score,
        "severity": names.get(score),
        "findings": findings,
        "unknown": unknown,
        "signals": signals,
    }


def format_report(reports: list[dict]) -> str:
    lines = ["verify-pack", ""]
    for report in reports:
        lines.append(_heading(report))
        for row in report["findings"]:
            where = _where(row)
            lines.append(f"  {row['severity']:<6}  {row['id']:<24}  {where}")
            lines.append(f"           {row['title']}")
        for row in report["unknown"]:
            where = _where(row)
            lines.append(f"  unknown  {row['id']:<24}  {where}")
            lines.append("           the backing command or its result could not be read")
        if report["findings"] or report["unknown"]:
            lines.append("")
    finding_count = sum(len(report["findings"]) for report in reports)
    unknown_count = sum(len(report["unknown"]) for report in reports)
    lines.append(
        f"{_count(len(reports), 'file')} · {_count(finding_count, 'finding')} · "
        f"{unknown_count} unknown. "
        "A finding is a review candidate. Unknown is not a pass."
    )
    return "\n".join(lines)


def exit_code(reports: list[dict], *, strict: bool) -> int:
    if any(report["findings"] for report in reports):
        return 1
    if strict and any(report["unknown"] for report in reports):
        return 1
    return 0


def _count(number: int, word: str) -> str:
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


def _heading(report: dict) -> str:
    name = Path(report["input"]).as_posix()
    if report["findings"]:
        return f"{name}  score {report['score']} ({report['severity']})"
    if report["unknown"]:
        return f"{name}  unknown"
    return f"{name}  no medium findings"


def _where(row: dict) -> str:
    if not row["evidence"]:
        return ""
    item = row["evidence"][0]
    return f"step {item['step_id']} {item['channel']}"


def dump(reports: list[dict]) -> str:
    payload: object = reports[0] if len(reports) == 1 else reports
    return json.dumps(payload, indent=2)
