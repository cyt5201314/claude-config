#!/usr/bin/env python3
"""Read and write the personal Lark task board through lark-cli.

    board.py snapshot                 # open tasks as JSON, for duplicate / relation judgment
    board.py apply plan.json          # validate the whole plan, then write it
    board.py apply plan.json --dry-run

Config (not in this repo): ~/.claude/lark-task-board.json, or $LARK_TASK_BOARD_CONFIG.
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("LARK_TASK_BOARD_CONFIG", "~/.claude/lark-task-board.json")).expanduser()
OPS = ("create", "subtask", "append", "reparent", "move", "complete")


class BoardError(Exception):
    pass


def lark(*args, data=None, params=None):
    cmd = ["lark-cli", *args, "--as", "user"]
    if data is not None:
        cmd += ["--data", json.dumps(data, ensure_ascii=False)]
    if params is not None:
        cmd += ["--params", json.dumps(params, ensure_ascii=False)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise BoardError("lark-cli 不在 PATH 里：这台机器不能用任务面板")
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        raise BoardError(f"lark-cli {' '.join(args[:3])} 没有返回 JSON：{(proc.stdout or proc.stderr)[:300]}")
    if out.get("ok") is not True:
        raise BoardError(f"lark-cli {' '.join(args[:3])} 失败：{json.dumps(out.get('error', out), ensure_ascii=False)[:400]}")
    return out.get("data", {})


def task_api(guid, action, data):
    return lark("api", "POST", f"/open-apis/task/v2/tasks/{guid}/{action}", data=data)


def read_json(path, what):
    try:
        value = json.loads(Path(path).read_text())
    except OSError as error:
        raise BoardError(f"读不了{what} {path}：{error.strerror}")
    except ValueError as error:
        raise BoardError(f"{what} {path} 不是合法的 JSON：{error}")
    return value


def load_config():
    if not CONFIG_PATH.exists():
        raise BoardError(f"找不到配置 {CONFIG_PATH}，按 SKILL.md 的「配置」一节建")
    cfg = read_json(CONFIG_PATH, "配置")
    for key in ("tasklist_guid", "category_field", "project_field", "category_of"):
        if key not in cfg:
            raise BoardError(f"配置缺 {key}")
    return cfg


class Board:
    """Tasklist layout read from Lark on every run, so the config cannot drift from it."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.tasklist = cfg["tasklist_guid"]
        sections = lark("task", "sections", "list",
                        params={"resource_type": "tasklist", "resource_id": self.tasklist})
        self.sections = {s["name"]: s["guid"] for s in sections.get("items", []) if s.get("name")}
        fields = lark("task", "custom_fields", "list",
                      params={"resource_type": "tasklist", "resource_id": self.tasklist})
        by_name = {f["name"]: f for f in fields.get("items", [])}
        self.fields = {}
        for name in (cfg["category_field"], cfg["project_field"]):
            if name not in by_name:
                raise BoardError(f"清单里没有自定义字段「{name}」")
            options = by_name[name].get("single_select_setting", {}).get("options", [])
            self.fields[name] = {"guid": by_name[name]["guid"], "options": {o["name"]: o["guid"] for o in options}}
        projects = self.fields[cfg["project_field"]]["options"]
        categories = self.fields[cfg["category_field"]]["options"]
        for project, category in cfg["category_of"].items():
            if project not in projects:
                raise BoardError(f"配置里的项目「{project}」不是字段「{cfg['project_field']}」的选项")
            if category not in categories:
                raise BoardError(f"配置里的大类「{category}」不是字段「{cfg['category_field']}」的选项")

    def field_values(self, project):
        cfg = self.cfg
        category = cfg["category_of"][project]
        cat, prj = self.fields[cfg["category_field"]], self.fields[cfg["project_field"]]
        return [{"guid": cat["guid"], "single_select_value": cat["options"][category]},
                {"guid": prj["guid"], "single_select_value": prj["options"][project]}]

    def field_names(self, task):
        """{field name: option name} for the two board fields set on a task."""
        result = {}
        for value in task.get("custom_fields", []):
            for name, field in self.fields.items():
                if value.get("guid") == field["guid"]:
                    by_guid = {g: n for n, g in field["options"].items()}
                    result[name] = by_guid.get(value.get("single_select_value"))
        return result

    def section_name(self, task):
        by_guid = {g: n for n, g in self.sections.items()}
        for entry in task.get("tasklists", []):
            if entry.get("tasklist_guid") == self.tasklist:
                return by_guid.get(entry.get("section_guid"))
        return None


def due_payload(date_text):
    day = datetime.date.fromisoformat(date_text)
    midnight = datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc)
    return {"timestamp": str(int(midnight.timestamp() * 1000)), "is_all_day": True}


def due_text(task):
    due = task.get("due", {})
    stamp = due.get("timestamp")
    if not stamp or stamp == "0":
        return None
    zone = datetime.timezone.utc if due.get("is_all_day") else None
    return datetime.datetime.fromtimestamp(int(stamp) / 1000, zone).date().isoformat()


def open_top_level(tasklist):
    items, token = [], None
    while True:
        params = {"tasklist_guid": tasklist, "completed": False, "page_size": 100}
        if token:
            params["page_token"] = token
        page = lark("task", "tasklists", "tasks", params=params)
        items += page.get("items", [])
        token = page.get("page_token")
        if not page.get("has_more") or not token:
            return [item["guid"] for item in items]


def open_subtasks(guid):
    items, token = [], None
    while True:
        params = {"task_guid": guid, "page_size": 100}
        if token:
            params["page_token"] = token
        page = lark("task", "subtasks", "list", params=params)
        items += page.get("items", [])
        token = page.get("page_token")
        if not page.get("has_more") or not token:
            return [item for item in items if item.get("completed_at", "0") in ("0", "")]


def describe(board, task):
    node = {
        "guid": task["guid"],
        "summary": task.get("summary", ""),
        "section": board.section_name(task),
        "due": due_text(task),
        "description": task.get("description", ""),
        "blocked_by": [d["task_guid"] for d in task.get("dependencies", []) if d.get("type") == "prev"],
        "url": task.get("url"),
        "subtasks": [],
    }
    node.update(board.field_names(task))
    if task.get("subtask_count"):
        node["subtasks"] = [describe(board, sub) for sub in open_subtasks(task["guid"])]
    return node


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node["subtasks"])


def fingerprint(nodes):
    """Changes whenever an open task is added, removed, renamed or re-parented."""
    rows = sorted(f"{node['guid']}\t{node['summary']}\t{len(node['subtasks'])}" for node in walk(nodes))
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()[:16]


def snapshot(board):
    guids = open_top_level(board.tasklist)

    def fetch(guid):
        return describe(board, lark("task", "tasks", "get", params={"task_guid": guid})["task"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        nodes = list(pool.map(fetch, guids))
    return {
        "based_on": fingerprint(nodes),
        "sections": list(board.sections),
        "projects": board.cfg["category_of"],
        "tasks": nodes,
    }


def normalized(title):
    return "".join(title.split()).lower()


TEXT_KEYS = ("op", "summary", "description", "due", "project", "section", "task", "parent", "text", "result")
GUID_LIST_KEYS = ("blocked_by", "related")


def shape_problems(plan):
    """Wrong JSON types, so the checks and writes after this never meet one."""
    if not isinstance(plan, dict):
        return ["plan 要是一个对象：{\"based_on\": …, \"ops\": […]}"]
    ops = plan.get("ops")
    if not isinstance(ops, list) or not ops:
        return ["plan 里没有 ops"]
    problems = []

    def check(where, item):
        for key in TEXT_KEYS:
            if key in item and not isinstance(item[key], str):
                problems.append(f"{where}：{key} 要是字符串")
        for key in GUID_LIST_KEYS:
            value = item.get(key, [])
            if not isinstance(value, list) or not all(isinstance(guid, str) for guid in value):
                problems.append(f"{where}：{key} 要是 guid 字符串的列表")
            elif len(set(value)) != len(value):
                problems.append(f"{where}：{key} 里同一个 guid 写了不止一次")
        if not isinstance(item.get("same_title_ok", False), bool):
            problems.append(f"{where}：same_title_ok 只能是 true / false")

    for index, op in enumerate(ops, 1):
        if not isinstance(op, dict):
            problems.append(f"第 {index} 条：要是一个对象")
            continue
        where = f"第 {index} 条 {op.get('op')}"
        check(where, op)
        subtasks = op.get("subtasks", [])
        if not isinstance(subtasks, list):
            problems.append(f"{where}：subtasks 要是列表")
            continue
        for sub_index, sub in enumerate(subtasks, 1):
            if isinstance(sub, dict):
                check(f"{where} 的子任务 {sub_index}", sub)
            else:
                problems.append(f"{where} 的子任务 {sub_index}：要是一个对象")
    return problems


def validate(board, snap, plan):
    """Every problem in the plan, found before anything is written."""
    problems = shape_problems(plan)
    if problems:
        return problems
    if plan.get("based_on") != snap["based_on"]:
        problems.append(f"面板在判定之后变了（plan 的 based_on={plan.get('based_on')}，现在是 {snap['based_on']}）："
                        "重新 snapshot，重新判重")
    known = {node["guid"]: node for node in walk(snap["tasks"])}
    titles = {normalized(node["summary"]): node["guid"] for node in known.values()}
    # State the earlier ops of this plan leave behind, so a later op is checked against it.
    top_level = {node["guid"] for node in snap["tasks"]}
    parent_of = {sub["guid"]: node["guid"] for node in known.values() for sub in node["subtasks"]}
    completed = set()
    reparented = set()
    new_subtasks = set()

    def need_task(where, guid):
        if guid not in known:
            problems.append(f"{where}：{guid} 不是面板里未完成的任务")
        elif guid in completed:
            problems.append(f"{where}：{guid} 在这份 plan 前面已经标完成")

    def need_due(where, item):
        if item.get("due"):
            try:
                datetime.date.fromisoformat(item["due"])
            except ValueError:
                problems.append(f"{where}：due 要写成 YYYY-MM-DD，现在是 {item['due']}")

    def need_new_title(where, item):
        summary = item.get("summary", "").strip()
        if not summary:
            problems.append(f"{where}：缺 summary")
            return
        key = normalized(summary)
        if key in titles and not item.get("same_title_ok"):
            problems.append(f"{where}：标题「{summary}」和已有任务 {titles[key]} 相同；"
                            "确实是另一件事就改标题，或在用户确认后写 same_title_ok")
        titles.setdefault(key, "本 plan 里的另一条")

    def need_section(where, op):
        if op.get("section") not in board.sections:
            problems.append(f"{where}：section 只能是 {' / '.join(board.sections)}")

    for index, op in enumerate(plan["ops"], 1):
        where = f"第 {index} 条 {op.get('op')}"
        kind = op.get("op")
        if kind not in OPS:
            problems.append(f"第 {index} 条：op 只能是 {' / '.join(OPS)}")
        elif kind == "create":
            need_new_title(where, op)
            need_due(where, op)
            if op.get("project") not in board.cfg["category_of"]:
                problems.append(f"{where}：project 只能是 {' / '.join(board.cfg['category_of'])}")
            need_section(where, op)
            for sub_index, sub in enumerate(op.get("subtasks", []), 1):
                need_new_title(f"{where} 的子任务 {sub_index}", sub)
                need_due(f"{where} 的子任务 {sub_index}", sub)
            for guid in op.get("blocked_by", []) + op.get("related", []):
                need_task(where, guid)
        elif kind == "subtask":
            need_task(where, op.get("parent"))
            need_new_title(where, op)
            need_due(where, op)
            new_subtasks.add(op.get("parent"))
        elif kind == "append":
            need_task(where, op.get("task"))
            if not op.get("text", "").strip():
                problems.append(f"{where}：缺 text")
        elif kind == "reparent":
            task, parent = op.get("task"), op.get("parent")
            need_task(where, task)
            need_task(where, parent)
            ancestor, seen = parent, set()
            while ancestor in parent_of and ancestor != task and ancestor not in seen:
                seen.add(ancestor)
                ancestor = parent_of[ancestor]
            if task == parent:
                problems.append(f"{where}：不能挂到自己下面")
            elif ancestor == task:
                problems.append(f"{where}：不能挂到自己的子任务下面")
            elif task in reparented:
                problems.append(f"{where}：{task} 在这份 plan 前面已经改挂过一次")
            elif task in known and parent in known:
                parent_of[task] = parent
                top_level.discard(task)
                reparented.add(task)
        elif kind == "move":
            if op.get("task") not in top_level:
                problems.append(f"{where}：只有清单里的顶层任务能换分组")
            elif op["task"] in completed:
                problems.append(f"{where}：{op['task']} 在这份 plan 前面已经标完成")
            need_section(where, op)
        elif kind == "complete":
            task = op.get("task")
            need_task(where, task)
            # Completing a parent hides its open subtasks from the board along with it.
            still_open = [child for child, parent in parent_of.items() if parent == task and child not in completed]
            if still_open or task in new_subtasks:
                names = "、".join(known[child]["summary"] for child in still_open) or "这份 plan 里新加的子任务"
                problems.append(f"{where}：它下面还有没完成的子任务（{names}）；先把子任务标完成或改挂到别处")
            completed.add(task)
    return problems


def append_description(guid, text):
    current = lark("task", "tasks", "get", params={"task_guid": guid})["task"].get("description", "")
    merged = f"{current}\n\n{text}".strip() if current else text
    lark("task", "tasks", "patch", params={"task_guid": guid},
         data={"task": {"description": merged}, "update_fields": ["description"]})


def new_task_body(me, item):
    body = {"summary": item["summary"].strip(), "members": [{"id": me, "type": "user", "role": "assignee"}]}
    if item.get("description"):
        body["description"] = item["description"]
    if item.get("due"):
        body["due"] = due_payload(item["due"])
    return body


def execute(board, snap, plan, me, today, done):
    """Runs the ops in order. `done` gets an entry as soon as an op has written anything; the entry
    keeps "incomplete" until the op's last write lands, so a failure midway shows what is on the board."""
    known = {node["guid"]: node for node in walk(snap["tasks"])}
    top_level = {node["guid"] for node in snap["tasks"]}

    def started(entry):
        entry["incomplete"] = True
        done.append(entry)
        return entry

    for op in plan["ops"]:
        kind = op["op"]
        if kind == "create":
            body = new_task_body(me, op)
            body["tasklists"] = [{"tasklist_guid": board.tasklist, "section_guid": board.sections[op["section"]]}]
            body["custom_fields"] = board.field_values(op["project"])
            task = lark("task", "tasks", "create", data=body)["task"]
            entry = started({"op": kind, "guid": task["guid"], "summary": task["summary"], "url": task.get("url")})
            for sub in op.get("subtasks", []):
                lark("task", "subtasks", "create", params={"task_guid": task["guid"]}, data=new_task_body(me, sub))
            if op.get("blocked_by"):
                task_api(task["guid"], "add_dependencies",
                         {"dependencies": [{"type": "prev", "task_guid": g} for g in op["blocked_by"]]})
            for guid in op.get("related", []):
                other = known[guid]
                append_description(task["guid"], f"关联：{other['summary']} {other['url']}")
                append_description(guid, f"关联：{task['summary']} {task['url']}")
        elif kind == "subtask":
            sub = lark("task", "subtasks", "create", params={"task_guid": op["parent"]},
                       data=new_task_body(me, op))["subtask"]
            entry = started({"op": kind, "guid": sub["guid"], "summary": sub["summary"], "parent": op["parent"]})
        elif kind == "append":
            append_description(op["task"], f"[{today} 补充] {op['text'].strip()}")
            entry = started({"op": kind, "guid": op["task"], "summary": known[op["task"]]["summary"]})
        elif kind == "reparent":
            lark("task", "+set-ancestor", "--task-id", op["task"], "--ancestor-id", op["parent"])
            entry = started({"op": kind, "guid": op["task"], "summary": known[op["task"]]["summary"],
                             "parent": op["parent"]})
            if op["task"] in top_level:
                # A subtask left in the tasklist shows up as a second card on the board.
                task_api(op["task"], "remove_tasklist", {"tasklist_guid": board.tasklist})
        elif kind == "move":
            task_api(op["task"], "add_tasklist",
                     {"tasklist_guid": board.tasklist, "section_guid": board.sections[op["section"]]})
            entry = started({"op": kind, "guid": op["task"], "summary": known[op["task"]]["summary"],
                             "section": op["section"]})
        elif kind == "complete":
            entry = {"op": kind, "guid": op["task"], "summary": known[op["task"]]["summary"]}
            if op.get("result"):
                append_description(op["task"], f"[{today} 结果] {op['result'].strip()}")
                started(entry)
            lark("task", "+complete", "--task-id", op["task"])
            if "incomplete" not in entry:
                started(entry)
        del entry["incomplete"]


def whoami():
    proc = subprocess.run(["lark-cli", "whoami"], capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)["onBehalfOf"]["openId"]
    except (ValueError, KeyError):
        raise BoardError("lark-cli whoami 没有返回登录用户：先 lark-cli auth login")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("snapshot")
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("plan")
    apply_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        board = Board(load_config())
        snap = snapshot(board)
        if args.command == "snapshot":
            print(json.dumps(snap, ensure_ascii=False, indent=1))
            return 0
        plan = read_json(args.plan, "plan")
        problems = validate(board, snap, plan)
        if problems:
            print("PLAN REJECTED，什么都没写：", file=sys.stderr)
            for problem in problems:
                print(f"- {problem}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(json.dumps({"ok": True, "dry_run": True, "ops": len(plan["ops"])}, ensure_ascii=False))
            return 0
        done = []
        try:
            execute(board, snap, plan, whoami(), datetime.date.today().isoformat(), done)
        finally:
            finished = len(done) == len(plan["ops"]) and not any(entry.get("incomplete") for entry in done)
            print(json.dumps({"ok": finished, "done": done}, ensure_ascii=False, indent=1))
        return 0
    except BoardError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
