#!/usr/bin/env python3
"""skills/ 下的中文版 pstack skill 是照哪一版原文译的。pstack 升级后原文变了就报错，提醒重译后更新这里的 hash。
跑法：python3 tests/test_pstack_zh.py（本机没装 pstack 时跳过）"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLED = Path.home() / ".claude/plugins/installed_plugins.json"
TRANSLATED_FROM = {
    "sharpen": ("0.15.48", "aac4f8e6a1ffd70e3763314db37d3c2eb0cfea08bc63e98907aca6dae0343031"),
    "reframe": ("0.15.48", "1e2e8a11da838c9169dae6fb71257041cf4e91d58862d1629354648b9bd458f3"),
}

entries = json.loads(INSTALLED.read_text())["plugins"].get("pstack@cursor-plugins") if INSTALLED.exists() else None
if not entries:
    print("skip: 本机没装 pstack")
    sys.exit(0)
install = Path(entries[0]["installPath"])
failed = 0
for name, (version, digest) in TRANSLATED_FROM.items():
    upstream = install / "skills" / name / "SKILL.md"
    ok = upstream.exists() and hashlib.sha256(upstream.read_bytes()).hexdigest() == digest
    zh = (ROOT / "skills" / name / "SKILL.md").read_text()
    ok_zh = f"name: {name}\n" in zh and "## 语言" in zh
    failed += not (ok and ok_zh)
    if ok and ok_zh:
        print(f"ok   {name}: 原文与译时（pstack {version}）一致")
    elif not ok:
        print(f"FAIL {name}: {upstream} 与译时（pstack {version}）不同——对照新原文重译 skills/{name}/SKILL.md，再更新本文件的版本和 hash")
    else:
        print(f"FAIL {name}: skills/{name}/SKILL.md 缺 name 或「## 语言」一节")
sys.exit(1 if failed else 0)
