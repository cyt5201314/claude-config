#!/usr/bin/env python3
"""Checks for skills/lark-task-board/scripts/board.py against a fake lark-cli, offline.

    python3 tests/test_lark_task_board.py
"""
import importlib.util
import os
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "lark-task-board" / "scripts" / "board.py"
spec = importlib.util.spec_from_file_location("board", SCRIPT)
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)

failures = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures.append(name)
        if detail:
            print(f"      {detail}")


def fake_board():
    fake = object.__new__(board.Board)
    fake.cfg = {"tasklist_guid": "TL", "category_field": "大类", "project_field": "项目",
                "category_of": {"甲系统": "开发", "乙培训": "培训"}}
    fake.tasklist = "TL"
    fake.sections = {"待整理": "S-inbox", "进行中": "S-doing"}
    fake.fields = {"大类": {"guid": "F-cat", "options": {"开发": "O-dev", "培训": "O-train"}},
                   "项目": {"guid": "F-prj", "options": {"甲系统": "O-a", "乙培训": "O-b"}}}
    return fake


def node(guid, summary, subtasks=()):
    return {"guid": guid, "summary": summary, "section": "待整理", "due": None, "description": "",
            "blocked_by": [], "url": f"https://example.test/{guid}", "subtasks": list(subtasks)}


def snap_of(nodes):
    return {"based_on": board.fingerprint(nodes), "tasks": nodes}


def rejected(fake, snap, ops, based_on=None):
    return board.validate(fake, snap, {"based_on": based_on or snap["based_on"], "ops": ops})


def main():
    fake = fake_board()
    snap = snap_of([node("T1", "退款申请", [node("T1a", "填写表单")]), node("T2", "培训资料")])
    create = {"op": "create", "summary": "新任务", "project": "甲系统", "section": "待整理"}

    check("a valid create passes", rejected(fake, snap, [create]) == [])
    check("a plan judged against an older board is rejected",
          any("重新 snapshot" in p for p in rejected(fake, snap, [create], based_on="stale")))
    check("adding a task changes the fingerprint",
          board.fingerprint(snap["tasks"]) != board.fingerprint(snap["tasks"] + [node("T3", "别的")]))
    check("renaming a task changes the fingerprint",
          board.fingerprint([node("T1", "a")]) != board.fingerprint([node("T1", "b")]))

    same = dict(create, summary=" 退款 申请 ")
    check("a new task titled like an open one is rejected", any("相同" in p for p in rejected(fake, snap, [same])))
    check("a new task titled like an open subtask is rejected",
          any("相同" in p for p in rejected(fake, snap, [dict(create, summary="填写表单")])))
    check("same_title_ok lets it through", rejected(fake, snap, [dict(same, same_title_ok=True)]) == [])
    check("two new tasks with one title in a single plan are rejected",
          any("相同" in p for p in rejected(fake, snap, [create, dict(create)])))

    check("unknown project is rejected", any("project" in p for p in rejected(fake, snap, [dict(create, project="丙")])))
    check("missing section is rejected",
          any("section" in p for p in rejected(fake, snap, [{k: v for k, v in create.items() if k != "section"}])))
    check("relative due is rejected", any("YYYY-MM-DD" in p for p in rejected(fake, snap, [dict(create, due="+2d")])))
    check("append to a task that is not open is rejected",
          any("不是面板里" in p for p in rejected(fake, snap, [{"op": "append", "task": "GONE", "text": "x"}])))
    check("reparent under its own subtask is rejected",
          any("自己的子任务" in p for p in rejected(fake, snap, [{"op": "reparent", "task": "T1", "parent": "T1a"}])))
    check("moving a subtask between sections is rejected",
          any("顶层" in p for p in rejected(fake, snap, [{"op": "move", "task": "T1a", "section": "进行中"}])))
    check("unknown op is rejected", any("op 只能是" in p for p in rejected(fake, snap, [{"op": "delete", "task": "T1"}])))
    many = rejected(fake, snap, [dict(create, project="丙"), {"op": "append", "task": "GONE", "text": "x"}])
    check("every problem is reported at once", len(many) == 2, str(many))

    for label, bad in (("plan that is a list", [create]), ("op that is a string", {"based_on": "x", "ops": ["create"]})):
        check(f"{label} is rejected, not a crash", board.validate(fake, snap, bad) != [])
    for label, patch in (("numeric due", {"due": 20261121}), ("numeric summary", {"summary": 5}),
                         ("blocked_by as a string", {"blocked_by": "T1"}), ("related as a string", {"related": "T1"}),
                         ("subtasks of strings", {"subtasks": ["x"]}), ("numeric description", {"description": 5})):
        check(f"{label} is rejected, not a crash", rejected(fake, snap, [dict(create, **patch)]) != [])
    check("numeric result is rejected before any write",
          any("result" in p for p in rejected(fake, snap, [{"op": "complete", "task": "T1", "result": 5}])))
    check("list parent is rejected, not a crash",
          rejected(fake, snap, [{"op": "subtask", "parent": ["T1"], "summary": "x"}]) != [])

    done_then = lambda later: rejected(fake, snap, [{"op": "complete", "task": "T2"}, later])
    check("append after complete in one plan is rejected",
          any("已经标完成" in p for p in done_then({"op": "append", "task": "T2", "text": "x"})))
    check("move after complete in one plan is rejected",
          any("已经标完成" in p for p in done_then({"op": "move", "task": "T2", "section": "进行中"})))
    check("completing twice in one plan is rejected",
          any("已经标完成" in p for p in done_then({"op": "complete", "task": "T2"})))
    check("move after reparent in one plan is rejected",
          any("顶层" in p for p in rejected(fake, snap, [{"op": "reparent", "task": "T2", "parent": "T1"},
                                                         {"op": "move", "task": "T2", "section": "进行中"}])))
    check("two reparents that form a loop are rejected",
          any("自己的子任务" in p for p in rejected(fake, snap, [{"op": "reparent", "task": "T2", "parent": "T1"},
                                                              {"op": "reparent", "task": "T1", "parent": "T2"}])))
    check("moving a subtask to another parent passes",
          rejected(fake, snap, [{"op": "reparent", "task": "T1a", "parent": "T2"}]) == [])

    check("same_title_ok given as a string does not switch the title check off",
          any("same_title_ok" in p for p in rejected(fake, snap, [dict(create, summary="退款申请", same_title_ok="false")])))
    check("same_title_ok given as a string on a subtask is rejected",
          any("same_title_ok" in p for p in rejected(fake, snap, [dict(create, subtasks=[{"summary": "子", "same_title_ok": 1}])])))
    for key in ("related", "blocked_by"):
        check(f"a guid listed twice in {key} is rejected",
              any("不止一次" in p for p in rejected(fake, snap, [dict(create, **{key: ["T2", "T2"]})])))
    check("reparenting one task twice in a plan is rejected",
          any("改挂过一次" in p for p in rejected(fake, snap, [{"op": "reparent", "task": "T1a", "parent": "T2"},
                                                            {"op": "reparent", "task": "T1a", "parent": "T1"}])))
    check("completing a task that has an open subtask is rejected",
          any("没完成的子任务（填写表单）" in p for p in rejected(fake, snap, [{"op": "complete", "task": "T1"}])))
    check("completing a task after hanging another task under it is rejected",
          any("没完成的子任务（培训资料）" in p for p in rejected(fake, snap, [{"op": "reparent", "task": "T2", "parent": "T1"},
                                                                         {"op": "complete", "task": "T1a"},
                                                                         {"op": "complete", "task": "T1"}])))
    check("completing a task after adding a subtask to it in the same plan is rejected",
          any("新加的子任务" in p for p in rejected(fake, snap, [{"op": "subtask", "parent": "T2", "summary": "新子"},
                                                           {"op": "complete", "task": "T2"}])))
    check("completing the subtasks first, then the parent, passes",
          rejected(fake, snap, [{"op": "complete", "task": "T1a"}, {"op": "complete", "task": "T1"}]) == [])
    check("completing a parent after its only subtask was moved elsewhere passes",
          rejected(fake, snap, [{"op": "reparent", "task": "T1a", "parent": "T2"}, {"op": "complete", "task": "T1"}]) == [])

    os.environ["TZ"] = "Asia/Tokyo"
    time.tzset()
    check("timed due is read in local time",
          board.due_text({"due": {"timestamp": "1795212000000", "is_all_day": False}}) == "2026-11-21")
    check("all-day due is read as the UTC day",
          board.due_text({"due": {"timestamp": "1795219200000", "is_all_day": True}}) == "2026-11-21")

    calls = []

    def fake_lark(*args, data=None, params=None):
        calls.append((args, data, params))
        if args[:3] == ("task", "tasks", "create"):
            return {"task": {"guid": "NEW", "summary": data["summary"], "url": "https://example.test/NEW"}}
        if args[:3] == ("task", "subtasks", "create"):
            return {"subtask": {"guid": "SUB", "summary": data["summary"]}}
        if args[:3] == ("task", "tasks", "get"):
            return {"task": {"guid": params["task_guid"], "description": "旧描述"}}
        return {}

    board.lark = fake_lark
    plan = {"ops": [dict(create, due="2026-11-21", subtasks=[{"summary": "子1"}], blocked_by=["T1"], related=["T2"]),
                    {"op": "reparent", "task": "T2", "parent": "T1"},
                    {"op": "append", "task": "T1", "text": "新信息"}]}
    done = []
    board.execute(fake, snap, plan, "ME", "2026-11-19", done)

    created = next(data for args, data, _ in calls if args[:3] == ("task", "tasks", "create"))
    check("created task lands in the named section",
          created["tasklists"] == [{"tasklist_guid": "TL", "section_guid": "S-inbox"}])
    check("created task carries project and the category the config maps it to",
          created["custom_fields"] == [{"guid": "F-cat", "single_select_value": "O-dev"},
                                       {"guid": "F-prj", "single_select_value": "O-a"}])
    check("due is an all-day UTC-midnight timestamp",
          created["due"] == {"timestamp": "1795219200000", "is_all_day": True})
    sub = next(data for args, data, _ in calls if args[:3] == ("task", "subtasks", "create"))
    check("subtask is not added to the tasklist", "tasklists" not in sub)
    paths = [args[2] for args, _, _ in calls if args[0] == "api"]
    check("blocked_by becomes a prev dependency", "/open-apis/task/v2/tasks/NEW/add_dependencies" in paths)
    check("reparented task leaves the tasklist", "/open-apis/task/v2/tasks/T2/remove_tasklist" in paths)
    patches = [(params["task_guid"], data["task"]["description"])
               for args, data, params in calls if args[:3] == ("task", "tasks", "patch")]
    check("related tasks link to each other",
          any(g == "NEW" and "培训资料" in d for g, d in patches) and any(g == "T2" and "新任务" in d for g, d in patches))
    check("append keeps the old description and dates the addition",
          ("T1", "旧描述\n\n[2026-11-19 补充] 新信息") in patches, str(patches))
    check("every op is reported, none left incomplete",
          [d["op"] for d in done] == ["create", "reparent", "append"] and not any("incomplete" in d for d in done))

    calls.clear()
    board.execute(fake, snap, {"ops": [{"op": "reparent", "task": "T1a", "parent": "T2"}]}, "ME", "2026-11-19", [])
    check("a task that was already a subtask is not removed from the tasklist again",
          not any(args[0] == "api" for args, _, _ in calls), str(calls))

    def moves_after(ops):
        calls.clear()
        done = []
        board.execute(fake, snap, {"ops": ops}, "ME", "2026-11-19", done)
        return [(args[2], data) for args, data, _ in calls if args[0] == "api"], done

    moves, _ = moves_after([{"op": "complete", "task": "T2"}])
    check("without done_section a completed task stays in its section", moves == [], str(moves))
    fake.cfg["done_section"] = "完成"
    fake.sections["完成"] = "S-done"
    moves, done = moves_after([{"op": "complete", "task": "T2"}])
    check("with done_section a completed task moves to that section",
          moves == [("/open-apis/task/v2/tasks/T2/add_tasklist", {"tasklist_guid": "TL", "section_guid": "S-done"})]
          and done[0].get("section") == "完成" and "incomplete" not in done[0], str(moves))
    order = [args[:2] if args[0] == "task" else args[2].rsplit("/", 1)[-1] for args, _, _ in calls]
    check("the task is completed before it is moved", order == [("task", "+complete"), "add_tasklist"], str(order))
    moves, _ = moves_after([{"op": "complete", "task": "T1a"}])
    check("a completed subtask is not added to the tasklist", moves == [], str(moves))

    def failing_move(*args, data=None, params=None):
        if args[0] == "api" and args[2].endswith("/add_tasklist"):
            raise board.BoardError("boom")
        return fake_lark(*args, data=data, params=params)

    board.lark = failing_move
    written = []
    try:
        board.execute(fake, snap, {"ops": [{"op": "complete", "task": "T2"}]}, "ME", "2026-11-19", written)
    except board.BoardError:
        pass
    check("a complete whose move fails is reported as incomplete",
          [(d["guid"], d.get("incomplete")) for d in written] == [("T2", True)], str(written))
    board.lark = fake_lark
    del fake.cfg["done_section"], fake.sections["完成"]

    def lark_failing_on(prefix):
        def failing(*args, data=None, params=None):
            if args[:len(prefix)] == prefix:
                raise board.BoardError("boom")
            return fake_lark(*args, data=data, params=params)
        return failing

    def partial(prefix, ops):
        board.lark = lark_failing_on(prefix)
        written = []
        try:
            board.execute(fake, snap, {"ops": ops}, "ME", "2026-11-19", written)
        except board.BoardError:
            pass
        return written

    written = partial(("task", "subtasks", "create"), [dict(create, subtasks=[{"summary": "子1"}])])
    check("a create that fails on its subtask still reports the task it made, as incomplete",
          [(d["guid"], d.get("incomplete")) for d in written] == [("NEW", True)], str(written))
    written = partial(("task", "+complete"), [{"op": "complete", "task": "T2", "result": "好了"}])
    check("a complete that fails after writing the result is reported as incomplete",
          [(d["guid"], d.get("incomplete")) for d in written] == [("T2", True)], str(written))
    board.lark = fake_lark

    def failing_lark(*args, data=None, params=None):
        if args[:2] == ("task", "+complete"):
            raise board.BoardError("boom")
        return fake_lark(*args, data=data, params=params)

    board.lark = failing_lark
    done = []
    try:
        board.execute(fake, snap, {"ops": [{"op": "append", "task": "T1", "text": "x"},
                                           {"op": "complete", "task": "T2"}]}, "ME", "2026-11-19", done)
        raised = False
    except board.BoardError:
        raised = True
    check("a failure midway still reports what was written", raised and [d["op"] for d in done] == ["append"])

    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all passed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
