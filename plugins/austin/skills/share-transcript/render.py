#!/usr/bin/env python3
"""Render the current Claude Code session transcript to shareable Markdown."""

import os
import re
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

PROJECTS = Path.home() / ".claude" / "projects"
OUT_DIR = Path.home() / ".claude" / "shared-transcripts"


def slugify(text, max_words=6, max_len=50):
    words = re.findall(r"[A-Za-z0-9]+", (text or "").lower())
    slug = "-".join(words[:max_words])[:max_len].strip("-")
    return slug or "session"


_WRAPPER_TAGS = (
    "system-reminder",
    "command-name",
    "command-message",
    "command-args",
    "local-command-stdout",
)


def strip_wrappers(text):
    if not text:
        return ""
    for tag in _WRAPPER_TAGS:
        text = re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL)
    return re.sub(r"[ \t]+", " ", text).strip()


_TOOL_FIELDS = {
    "Bash": ("description", "command"),
    "Read": ("file_path",),
    "Edit": ("file_path",),
    "Write": ("file_path",),
    "NotebookEdit": ("file_path",),
    "Skill": ("skill",),
    "TaskCreate": ("subject", "description"),
    "TaskUpdate": ("subject", "description"),
    "Agent": ("description",),
    "Glob": ("pattern",),
    "Grep": ("pattern", "query"),
    "ToolSearch": ("query",),
}


def _first_scalar(d):
    for v in d.values():
        if isinstance(v, (str, int, float, bool)):
            return str(v)
    return ""


def summarize_tool(name, tool_input):
    tool_input = tool_input or {}
    if name == "AskUserQuestion":
        headers = [q.get("header") or q.get("question", "")
                   for q in (tool_input.get("questions") or [])]
        salient = "; ".join(h for h in headers if h)
    else:
        salient = ""
        for field in _TOOL_FIELDS.get(name, ()):
            if tool_input.get(field):
                salient = str(tool_input[field])
                break
        if not salient:
            salient = _first_scalar(tool_input)
    salient = " ".join(salient.split())
    if len(salient) > 100:
        salient = salient[:99] + "…"
    return f"- {name}: {salient}" if salient else f"- {name}"


_SECRET_ASSIGN = re.compile(
    r"(?i)\b((?:SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY)\w*)"
    r"(\s*[:=]\s*)(\S+)"
)

_REDACTIONS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?:ghp|gho|ghs|ghr|pat)_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"glpat-[A-Za-z0-9_-]{16,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b[A-Fa-f0-9]{40,}\b"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
]


def redact(text):
    count = 0

    def _mask_assign(m):
        nonlocal count
        count += 1
        return f"{m.group(1)}{m.group(2)}[REDACTED]"

    text = _SECRET_ASSIGN.sub(_mask_assign, text)
    for pat in _REDACTIONS:
        text, n = pat.subn("[REDACTED]", text)
        count += n
    return text, count


def iter_events(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _tool_result_text(block):
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for item in c:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def parse_session(events):
    meta = {"project": None, "session": None, "first_prompt": None,
            "prompts": 0, "replies": 0, "start": None, "end": None}
    segments = []
    askq_ids = set()

    for ev in events:
        if ev.get("sessionId") and not meta["session"]:
            meta["session"] = ev["sessionId"]
        if ev.get("cwd") and not meta["project"]:
            meta["project"] = ev["cwd"]
        ts = ev.get("timestamp")
        if ts:
            if not meta["start"]:
                meta["start"] = ts
            meta["end"] = ts

        if ev.get("isSidechain"):
            continue
        etype = ev.get("type")
        if etype not in ("user", "assistant"):
            continue

        content = (ev.get("message") or {}).get("content")

        if etype == "user":
            if isinstance(content, str):
                text = strip_wrappers(content)
                if text:
                    segments.append(("user", text))
                    meta["prompts"] += 1
                    if not meta["first_prompt"]:
                        meta["first_prompt"] = text
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if (block.get("type") == "tool_result"
                            and block.get("tool_use_id") in askq_ids):
                        answer = strip_wrappers(_tool_result_text(block))
                        if answer:
                            segments.append(("user", answer))
                            meta["prompts"] += 1
            continue

        # assistant
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    segments.append(("claude", text))
                    meta["replies"] += 1
            elif btype == "tool_use":
                name = block.get("name", "tool")
                if name == "AskUserQuestion" and block.get("id"):
                    askq_ids.add(block["id"])
                segments.append(("tool", summarize_tool(name, block.get("input"))))
            # thinking dropped

    return meta, segments


def _format_when(meta):
    def fmt(ts):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError, TypeError):
            return None

    start, end = fmt(meta.get("start")), fmt(meta.get("end"))
    if start and end:
        if start[:10] == end[:10]:
            return f"{start} → {end[11:]}"
        return f"{start} → {end}"
    return start or end or "unknown"


def render_markdown(meta, segments):
    title = slugify(meta.get("first_prompt") or meta.get("session") or "session")
    lines = [
        f"# Session transcript — {title}",
        "",
        f"- Project: {meta.get('project') or 'unknown'}",
        f"- Session: {meta.get('session') or 'unknown'}",
        f"- When: {_format_when(meta)} · {meta['prompts']} prompts, {meta['replies']} replies",
        "",
        "> Generated by share-transcript. Thinking and tool output omitted; "
        "light secret-redaction applied — review before sharing.",
        "",
        "---",
        "",
    ]

    i, n = 0, len(segments)
    while i < n:
        role, content = segments[i]
        if role == "user":
            lines += ["**User**", "", content, ""]
            i += 1
        elif role == "claude":
            lines += ["**Claude**", "", content, ""]
            i += 1
        else:  # tool — group consecutive
            tools = []
            while i < n and segments[i][0] == "tool":
                tools.append(segments[i][1])
                i += 1
            lines += tools + [""]

    return "\n".join(lines).rstrip() + "\n"


def find_transcript(projects_dir=None, session_id=None):
    base = Path(projects_dir) if projects_dir else PROJECTS
    sid = session_id if session_id is not None else os.environ.get("CLAUDE_CODE_SESSION_ID")
    if sid:
        matches = sorted(base.glob(f"*/{sid}.jsonl"))
        if matches:
            return matches[0]
    all_jsonl = list(base.glob("*/*.jsonl"))
    if all_jsonl:
        return max(all_jsonl, key=lambda p: p.stat().st_mtime)
    return None


def copy_to_clipboard(text):
    pb = shutil.which("pbcopy")
    if not pb:
        return False
    try:
        subprocess.run([pb], input=text.encode("utf-8"), check=True)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def main():
    path = find_transcript()
    if not path or not path.exists():
        print("share-transcript: could not locate the current session transcript "
              "(CLAUDE_CODE_SESSION_ID unset and no transcripts found).", file=sys.stderr)
        return 1

    meta, segments = parse_session(iter_events(path))
    markdown = render_markdown(meta, segments)
    markdown, redactions = redact(markdown)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    slug = slugify(meta.get("first_prompt") or meta.get("session") or "session")
    out_path = OUT_DIR / f"{stamp}-{slug}.md"
    out_path.write_text(markdown, encoding="utf-8")

    copied = copy_to_clipboard(markdown)

    print(f"Wrote {out_path}")
    print(f"{redactions} potential secret(s) masked.")
    print("Clipboard: " + ("copied" if copied else "pbcopy unavailable, skipped"))
    print("Review before sharing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
