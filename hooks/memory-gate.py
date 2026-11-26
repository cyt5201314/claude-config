#!/usr/bin/python3
"""记忆写入闸门：用户在当前这条消息里明确批准，才能改 ~/.claude/projects/*/memory/。

一个脚本接三个事件（~/.claude/settings.json 注册）：
- UserPromptSubmit：这条消息含批准词（记住 / 记下 / 记 1、3 / 批准记忆 / 改·删·忘掉…记忆）
  就给本会话发通行证，否则收回。通行证只活到下一条用户消息。
- PreToolUse(Write|Edit|MultiEdit|NotebookEdit|Bash)：要改记忆目录却没有通行证，exit 2，
  stderr 回给模型，让它把候选写进汇报等用户批准。Bash 只拦带写操作的命令，读不拦。
- PostToolUse(同上)：改了记忆目录就在本地记忆仓库 commit 一次，message 带会话 id 和批准原话，
  方便事后查来源、git revert 回滚。记忆仓库不存在时跳过。

来由：2026-11 自动记忆无规则写入，冗余和错误记忆每次开工都干扰，用户因此关了记忆功能。
记忆仓库只在本机、不设 remote：记忆里有公司和项目信息，claude-config 是公开仓库。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"
PASSES = HOME / ".claude" / "memory-gate"

APPROVE = re.compile(
    r"记住|记下|批准记忆|同意记|全部记|都记上|忘掉|(?:改|删|更新|合并|整理)\S{0,8}记忆"
    r"|记忆\S{0,8}(?:改|删|更新|合并)|^\s*记\s*[0-9０-９]"
)
NEGATE = re.compile(r"(?:不要|别|不用|不必|无需|不需要)\s*(?:记|写记忆)")

MEMORY_IN_COMMAND = re.compile(r"\.claude/projects\b.*?/memory(?:/|\b)(?!-)", re.S)
MEMORY_PATH = re.compile(r"/memory(?:/|\b)(?!-)")
SEGMENT_BREAK = re.compile(r"&&|\|\||[;|]")
HARMLESS_REDIRECT = re.compile(r"\d?>\s*/dev/null|\d?>&\d")
WRITES_IN_COMMAND = re.compile(
    r">|\btee\b|\bsed\s+(?:-\w+\s+)*-i|\bperl\s+-\w*i|\b(?:rm|mv|cp|touch|mkdir|ln|truncate|rsync)\b"
    r"|\b(?:python3?|node|ruby)\b"
    r"|\bgit\b(?:\s+-C\s+\S+)?\s+(?:checkout|reset|restore|revert|rm|mv|stash|clean|commit|apply|am)\b"
)
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def pass_file(session_id):
    return PASSES / f"{re.sub(r'[^A-Za-z0-9_-]', '_', session_id or 'unknown')}.json"


def in_memory_dir(path):
    if not path:
        return False
    resolved = Path(path).expanduser().resolve()
    try:
        relative = resolved.relative_to(PROJECTS.resolve())
    except ValueError:
        return False
    return len(relative.parts) >= 2 and relative.parts[1] == "memory"


def touches_memory(data):
    tool = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    if tool in FILE_TOOLS:
        return in_memory_dir(tool_input.get("file_path") or tool_input.get("notebook_path"))
    if tool == "Bash":
        command = tool_input.get("command") or ""
        if not MEMORY_IN_COMMAND.search(command):
            return False
        segments = SEGMENT_BREAK.split(HARMLESS_REDIRECT.sub("", command))
        return any(MEMORY_PATH.search(s) and WRITES_IN_COMMAND.search(s) for s in segments)
    return False


def on_prompt(data):
    prompt = data.get("prompt") or ""
    target = pass_file(data.get("session_id"))
    if APPROVE.search(prompt) and not NEGATE.search(prompt):
        PASSES.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"prompt": prompt[:500]}, ensure_ascii=False))
    elif target.exists():
        target.unlink()


def on_pre_tool(data):
    if not touches_memory(data) or pass_file(data.get("session_id")).exists():
        return
    print(
        "已拦截：用户没有在当前这条消息里批准改记忆（~/.claude/CLAUDE.md「记忆」）。"
        "不要写记忆文件。把候选列进本轮汇报的「需要你决定」：每条写拟记内容、作用域（项目 / 全局）、"
        "依据（用户原话，或标「推断」）。用户回「记 1、3」这类话之后再写。",
        file=sys.stderr,
    )
    sys.exit(2)


def on_post_tool(data):
    if not touches_memory(data) or not (PROJECTS / ".git").exists():
        return
    git = ["git", "-C", str(PROJECTS), "-c", "user.name=memory-gate", "-c", "user.email=memory-gate@localhost"]
    subprocess.run(git + ["add", "-A"], capture_output=True)
    if subprocess.run(git + ["diff", "--cached", "--quiet"]).returncode == 0:
        return
    approval = pass_file(data.get("session_id"))
    prompt = json.loads(approval.read_text())["prompt"] if approval.exists() else "(无)"
    tool_input = data.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("command") or ""
    message = (
        f"memory: {data.get('tool_name')} {target[:120]}\n\n"
        f"session: {data.get('session_id')}\n"
        f"cwd: {data.get('cwd')}\n"
        f"用户批准原话: {prompt}\n"
    )
    subprocess.run(git + ["commit", "-q", "-F", "-"], input=message, text=True, capture_output=True)


HANDLERS = {"UserPromptSubmit": on_prompt, "PreToolUse": on_pre_tool, "PostToolUse": on_post_tool}

if __name__ == "__main__":
    payload = json.load(sys.stdin)
    handler = HANDLERS.get(payload.get("hook_event_name"))
    if handler:
        handler(payload)
