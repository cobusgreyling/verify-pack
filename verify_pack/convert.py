"""Session logs to a minimal ATIF trace.

Accepts an ATIF JSON file as-is, a claim-ledger JSONL file, a Grok
``chat_history.jsonl``, a Grok session directory, or a Claude Code session
JSONL. ``events.jsonl`` has no sentences and no commands.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_EXIT_HEADER = re.compile(r"\s*exit:\s*(-?\d+)\b", re.IGNORECASE)
_EXIT_CODE = re.compile(r"\bexit code:\s*(-?\d+)\b", re.IGNORECASE)

_NAMES = {
    "bash": "bash",
    "shell": "bash",
    "exec": "bash",
    "run_terminal_command": "bash",
    "write": "write",
    "edit": "edit",
    "strreplace": "search_replace",
    "search_replace": "search_replace",
    "apply_patch": "apply_patch",
    "read": "read_file",
    "read_file": "read_file",
}


def load_atif(path: Path) -> dict:
    """Return an ATIF document for ``path``."""
    path = resolve(path)
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("steps"), list):
            raise ValueError(f"{path}: expected an ATIF JSON object with steps")
        version = value.get("schema_version")
        if not isinstance(version, str) or not version.startswith("ATIF-"):
            raise ValueError(f"{path}: expected schema_version ATIF-...")
        return value
    return to_atif(_events(path))


def resolve(path: Path) -> Path:
    if path.is_dir():
        candidate = path / "chat_history.jsonl"
        if candidate.is_file():
            return candidate
        raise ValueError(f"{path}: directory has no chat_history.jsonl")
    if not path.is_file():
        raise ValueError(f"{path}: file not found")
    return path


def to_atif(events: list[dict]) -> dict:
    """One ATIF step per assistant turn. Tools after a sentence belong to it."""
    steps: list[dict] = []
    text: str | None = None
    tools: list[dict] = []

    def flush() -> None:
        nonlocal text, tools
        if text is None and not tools:
            return
        steps.append(_agent_step(len(steps) + 1, text or "", tools))
        text = None
        tools = []

    for event in events:
        kind = event.get("type")
        if kind == "user":
            flush()
            steps.append(
                {
                    "step_id": len(steps) + 1,
                    "source": "user",
                    "message": str(event.get("text") or ""),
                }
            )
            continue
        if kind == "assistant":
            flush()
            text = str(event.get("text") or "")
            continue
        if kind == "tool":
            tools.append(event)
    flush()
    if not steps:
        raise ValueError("transcript has no steps")
    return {"schema_version": "ATIF-v1.7", "steps": steps}


def _agent_step(step_id: int, message: str, tools: list[dict]) -> dict:
    step: dict = {"step_id": step_id, "source": "agent", "message": message}
    if not tools:
        return step
    calls = []
    results = []
    for index, tool in enumerate(tools, start=1):
        call_id = f"call-{step_id}-{index}"
        name = str(tool.get("name") or "bash")
        command = str(tool.get("command") or "")
        path = str(tool.get("path") or "")
        arguments = {"command": command} if command else {"path": path}
        calls.append(
            {"tool_call_id": call_id, "function_name": name, "arguments": arguments}
        )
        results.append({"source_call_id": call_id, "content": _result(tool)})
    step["tool_calls"] = calls
    step["observation"] = {"results": results}
    return step


def _result(tool: dict) -> str:
    output = str(tool.get("output") or "")
    code = tool.get("exit_code")
    if isinstance(code, bool) or not isinstance(code, int):
        return output
    if _EXIT_HEADER.match(output) or _EXIT_CODE.search(output):
        return output
    return f"exit: {code}\n{output}" if output else f"exit: {code}"


def _events(path: Path) -> list[dict]:
    raw = _read_jsonl(path)
    kind = _detect(path, raw)
    if kind == "native":
        return [_native(obj) for obj in raw if obj.get("type") in {"tool", "assistant", "user"}]
    if kind == "grok":
        return _from_grok(raw)
    return _from_claude(raw)


def _read_jsonl(path: Path) -> list[dict]:
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(event, dict):
            raise ValueError(f"{path}:{line_number}: each event needs to be an object")
        events.append(event)
    if not events:
        raise ValueError(f"{path}: empty transcript")
    return events


def _detect(path: Path, raw: list[dict]) -> str:
    for obj in raw[:80]:
        if obj.get("type") in {"tool_started", "tool_completed", "turn_started"}:
            raise ValueError(
                f"{path}: this is a Grok event log. Pass chat_history.jsonl from the same session."
            )
    saw_native = False
    for obj in raw:
        kind = obj.get("type")
        if kind == "tool_result" and "tool_call_id" in obj:
            return "grok"
        if kind == "assistant" and isinstance(obj.get("message"), dict):
            return "claude"
        if kind == "assistant" and "tool_calls" in obj:
            return "grok"
        if kind == "backend_tool_call":
            return "grok"
        if kind == "tool" and ("exit_code" in obj or "name" in obj):
            saw_native = True
        if kind == "assistant" and "text" in obj:
            saw_native = True
        if kind == "user" and "text" in obj:
            saw_native = True
    if saw_native:
        return "native"
    for obj in raw:
        if obj.get("type") == "assistant" and isinstance(obj.get("content"), str):
            return "grok"
    raise ValueError(
        f"{path}: unrecognised transcript "
        "(want ATIF JSON, claim-ledger JSONL, Grok chat_history.jsonl, or Claude Code JSONL)"
    )


def _native(obj: dict) -> dict:
    if obj.get("type") == "assistant":
        return {"type": "assistant", "text": str(obj.get("text") or "")}
    if obj.get("type") == "user":
        return {"type": "user", "text": str(obj.get("text") or "")}
    code = obj.get("exit_code")
    if isinstance(code, bool) or not isinstance(code, int):
        code = None
    return {
        "type": "tool",
        "name": _canon(str(obj.get("name") or "bash")),
        "command": str(obj.get("command") or ""),
        "path": str(obj.get("path") or ""),
        "exit_code": code,
        "output": str(obj.get("output") or ""),
    }


def _from_grok(raw: list[dict]) -> list[dict]:
    pending: dict[str, tuple[str, dict]] = {}
    events: list[dict] = []
    for obj in raw:
        kind = obj.get("type")
        if kind == "user" and isinstance(obj.get("content"), str):
            events.append({"type": "user", "text": obj["content"]})
            continue
        if kind == "assistant":
            text = obj.get("content")
            if isinstance(text, str) and text.strip():
                events.append({"type": "assistant", "text": text})
            for call in obj.get("tool_calls") or []:
                if not isinstance(call, dict) or not call.get("id"):
                    continue
                pending[str(call["id"])] = (_canon(str(call.get("name") or "")), _args(call))
            continue
        if kind != "tool_result":
            continue
        name, args = pending.pop(str(obj.get("tool_call_id") or ""), ("bash", {}))
        output = _text(obj.get("content"))
        events.append(_tool(name, args, output, _infer_exit(output)))
    return events


def _from_claude(raw: list[dict]) -> list[dict]:
    pending: dict[str, tuple[str, dict]] = {}
    events: list[dict] = []
    for obj in raw:
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        texts: list[str] = []
        if obj.get("type") == "user" and isinstance(content, str) and content.strip():
            events.append({"type": "user", "text": content})
        if obj.get("type") == "assistant" and isinstance(content, str) and content.strip():
            texts.append(content)
        calls: list[tuple[str, str, dict]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and obj.get("type") == "assistant":
                texts.append(str(block.get("text") or ""))
            elif block.get("type") == "tool_use" and block.get("id"):
                name = _canon(str(block.get("name") or ""))
                args = block.get("input") if isinstance(block.get("input"), dict) else {}
                calls.append((str(block["id"]), name, args))
            elif block.get("type") == "tool_result":
                name, args = pending.pop(str(block.get("tool_use_id") or ""), ("bash", {}))
                output = _text(block.get("content"))
                events.append(_tool(name, args, output, _infer_exit(output, block.get("is_error"))))
        if texts:
            joined = "\n".join(part for part in texts if part.strip())
            if joined.strip():
                events.append({"type": "assistant", "text": joined})
        for call_id, name, args in calls:
            pending[call_id] = (name, args)
    return events


def _tool(name: str, args: dict, output: str, exit_code: int) -> dict:
    command = args.get("command") if isinstance(args.get("command"), str) else ""
    return {
        "type": "tool",
        "name": name or "bash",
        "command": command,
        "path": _path_of(args),
        "exit_code": exit_code,
        "output": output,
    }


def _args(call: dict) -> dict:
    raw = call.get("arguments")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _path_of(args: dict) -> str:
    for key in ("file_path", "path", "target_file"):
        value = args.get(key)
        if isinstance(value, str):
            return value
    return ""


def _text(content: object) -> str:
    if isinstance(content, str):
        return content[:20000]
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
        return "\n".join(parts)[:20000]
    if content is None:
        return ""
    return str(content)[:20000]


def _canon(name: str) -> str:
    key = name.strip().lower().replace("-", "_")
    if key in {"bash", "shell", "exec", "run_terminal_command"}:
        return "bash"
    return _NAMES.get(key, name.strip() or "bash")


def _infer_exit(text: str, is_error: object = None) -> int:
    header = _EXIT_HEADER.match(text)
    if header:
        return int(header.group(1))
    if is_error is True:
        return 1
    if is_error is False:
        return 0
    coded = _EXIT_CODE.search(text)
    if coded:
        return int(coded.group(1))
    head = text.lstrip()[:300].lower()
    if head.startswith("error") or head.startswith("traceback (most recent call last)"):
        return 1
    return 0
