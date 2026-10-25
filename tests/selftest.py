#!/usr/bin/env python3
"""End-to-end smoke test for edu-dsh.

Runs every command in a throwaway workspace and checks the invariants we care
about: consent gates, monotonic session numbers, backup-on-forget, export,
fail-closed config.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "edu_dsh.py"

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print("PASS  %s" % name)
    else:
        failed += 1
        print("FAIL  %s  %s" % (name, detail))


def run(home: Path, *args: str):
    cmd = [sys.executable, str(SCRIPT), *args, "--home", str(home)]
    proc = subprocess.run(cmd, capture_output=True)
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", "replace"),
        proc.stderr.decode("utf-8", "replace"),
    )


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="edu-dsh-selftest-"))
    home = root / "home"
    try:
        code, out, _ = run(home, "init")
        check("init exits 0", code == 0, out)
        check("config created", (home / "config.json").exists())
        check("state created", (home / "learner" / "state.json").exists())
        check("profile created", (home / "learner" / "profile.md").exists())
        check("glossary created", (home / "learner" / "glossary.md").exists())
        check("notes dir created", (home / "notes").is_dir())

        code, out, _ = run(home, "doctor")
        check("doctor exits 0", code == 0, out)
        check("doctor reports retrieval", "retrieval" in out)

        code, out, _ = run(home, "goal", "--add", "做出一个能跑的心跳灯", "--consent", "outline")
        check("goal add", code == 0 and "goal added" in out, out)
        code, out, _ = run(home, "goal", "--list")
        check("goal listed", "心跳灯" in out, out)

        code, out, _ = run(
            home, "cap", "--add", "--statement", "能解释为什么连续要单独定义",
            "--basis", "自己举了可去间断点的例子", "--confidence", "medium",
            "--consent", "outline",
        )
        check("cap add", code == 0 and "capability added" in out, out)
        code, out, _ = run(home, "cap", "--list")
        check("cap listed", "连续" in out and "[c1]" in out, out)

        code, out, _ = run(home, "question", "--add", "为什么极限不要求函数在该点有定义",
                           "--consent", "outline")
        check("question add", code == 0 and "question added" in out, out)

        code, out, _ = run(
            home, "glossary", "--add", "--term", "ZPD",
            "--full", "Zone of Proximal Development，最近发展区",
            "--plain", "跳一跳够得着的那段难度区间",
            "--example", "在 ZPD 内练习", "--consent", "outline",
        )
        check("glossary add", code == 0 and "glossary added" in out, out)
        code, out, _ = run(
            home, "glossary", "--add", "--term", "ZPD",
            "--full", "Zone of Proximal Development，最近发展区",
            "--plain", "重复", "--consent", "outline",
        )
        check("glossary dedupe", code == 0 and "already recorded" in out, out)

        # consent=off must write nothing
        code, out, _ = run(home, "cap", "--add", "--statement", "不该被写入",
                           "--consent", "off")
        check("cap off blocked", code == 0 and "not recorded" in out, out)
        caps = json.loads((home / "learner" / "state.json").read_text(encoding="utf-8"))
        check("cap off wrote nothing", len(caps["capabilities"]) == 1, str(caps["capabilities"]))

        code, out, _ = run(home, "note", "--topic", "calculus/limits", "--summary", "不该写",
                           "--consent", "off")
        check("note off blocked", code == 0 and not list((home / "sessions").glob("*.md")), out)

        code, out, _ = run(
            home, "note", "--topic", "calculus/limits", "--summary",
            "用户自己说出极限是趋势而不是点", "--mode", "curiosity",
            "--next", "下次用 epsilon-N 复述", "--evidence", "「不该保存」",
            "--consent", "outline",
        )
        check("note outline", code == 0 and "session 0001" in out, out)
        first = home / "sessions" / sorted(p.name for p in (home / "sessions").glob("*.md"))[0]
        text = first.read_text(encoding="utf-8")
        check("outline has summary", "趋势而不是点" in text)
        check("outline drops evidence", "不该保存" not in text)

        code, out, _ = run(
            home, "note", "--topic", "calculus/derivative", "--summary", "用户说导数像放大镜",
            "--evidence", "「导数就是放大镜」", "--consent", "verbatim",
        )
        check("note verbatim", code == 0 and "session 0002" in out, out)
        files = sorted((home / "sessions").glob("*.md"))
        verbatim_text = [p.read_text(encoding="utf-8") for p in files if "derivative" in p.name][0]
        check("verbatim keeps evidence", "放大镜」" in verbatim_text)

        code, out, _ = run(
            home, "delta", "--learned", "能区分极限与函数值", "--did", "自己改了一个数列例子",
            "--want", "问了无穷小的定义", "--alone", "不看对话，自己把测试跑通了",
            "--verified", "pytest", "--consent", "outline",
        )
        check("delta recorded", code == 0 and "delta recorded" in out, out)
        rows = (home / "deltas.jsonl").read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(rows[0])
        check("delta jsonl", len(rows) == 1 and record["session"] == "0002", rows)
        check("delta alone field", record.get("alone", "").startswith("不看对话"), record)
        check("delta verified field", record.get("verified") == "pytest", record)
        code, out, _ = run(home, "state")
        check("state shows alone/verified", "独自" in out and "验证" in out, out)

        code, out, _ = run(home, "state", "--json")
        payload = json.loads(out)
        check("state json", code == 0 and payload["state"]["goals"], out[:200])
        check("state has caps", payload["state"]["capabilities"][0]["id"] == "c1")

        # knowledge map
        code, out, _ = run(home, "map", "--action", "new", "--topic", "calculus",
                           "--title", "微积分", "--goal", "理解变化与累积",
                           "--consent", "outline")
        check("map new", code == 0 and "map created" in out, out)
        check("map.json created", (home / "learner" / "map.json").exists())
        check("map.md created", (home / "map.md").exists())

        for node_id, title in (("functions", "函数"), ("limits", "极限"),
                               ("derivative", "导数")):
            code, out, _ = run(home, "map", "--action", "add", "--topic", "calculus",
                               "--node", node_id, "--title", title, "--consent", "outline")
            check("map add %s" % node_id, code == 0 and "node added" in out, out)

        code, out, _ = run(home, "map", "--action", "link", "--topic", "calculus",
                           "--from", "functions", "--to", "limits", "--consent", "outline")
        check("map link", code == 0 and "link added" in out, out)
        run(home, "map", "--action", "link", "--topic", "calculus",
            "--from", "limits", "--to", "derivative", "--consent", "outline")

        code, out, _ = run(home, "map", "--action", "status", "--topic", "calculus",
                           "--node", "limits", "--status", "practicing", "--consent", "outline")
        check("map status", code == 0 and "practicing" in out, out)

        code, out, _ = run(home, "map", "--action", "position", "--topic", "calculus",
                           "--node", "limits", "--why", "导数的入口",
                           "--next", "用 epsilon-N 说清楚", "--consent", "outline")
        check("map position", code == 0 and "position: limits" in out, out)

        code, out, _ = run(home, "map", "--action", "show")
        check("map show position", "你在这里" in out and "导数的入口" in out, out)
        check("map show no progress", "完成率" not in out and "剩余" not in out, out)

        code, out, _ = run(home, "map", "--action", "show", "--json")
        map_payload = json.loads(out)
        check("map show json",
              map_payload["maps"][0]["nodes"][1]["status"] == "practicing", out[:200])

        code, _, _ = run(home, "map", "--action", "add", "--topic", "calculus",
                         "--node", "limits", "--title", "重复", "--consent", "outline")
        check("map duplicate node rejected", code != 0)
        code, _, _ = run(home, "map", "--action", "link", "--topic", "calculus",
                         "--from", "limits", "--to", "nope", "--consent", "outline")
        check("map link unknown rejected", code != 0)
        code, _, _ = run(home, "map", "--action", "link", "--topic", "calculus",
                         "--from", "limits", "--to", "limits", "--consent", "outline")
        check("map self link rejected", code != 0)

        code, out, _ = run(home, "map", "--action", "status", "--topic", "calculus",
                           "--node", "limits", "--status", "can-do", "--consent", "off")
        check("map off blocked", code == 0 and "not recorded" in out, out)
        code, out, _ = run(home, "map", "--action", "show", "--json")
        still = json.loads(out)["maps"][0]["nodes"][1]["status"]
        check("map off wrote nothing", still == "practicing", still)

        code, out, _ = run(home, "note", "--topic", "calculus/limits", "--node", "limits",
                           "--summary", "地图节点记录", "--consent", "outline")
        check("note node", code == 0 and "session" in out, out)
        code, out, _ = run(home, "records", "--json")
        rows = json.loads(out)
        check("records node", any(row.get("node") == "limits" for row in rows), out[:200])

        code, out, _ = run(home, "question", "--add", "为什么极限不要求该点有定义？",
                           "--node", "limits", "--consent", "outline")
        check("question node", code == 0 and "question added" in out, out)
        code, out, _ = run(home, "map", "--action", "show")
        check("map shows question", "该点有定义" in out, out)

        code, out, _ = run(home, "state")
        check("state maps line", "maps:" in out and "微积分" in out, out)

        code, out, _ = run(home, "delta", "--learned", "x", "--asked", "为什么是极限？",
                           "--returned", "上次的连续问题", "--consent", "outline")
        check("delta curiosity fields", code == 0, out)
        last_row = json.loads(
            (home / "deltas.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
        check("delta asked stored", last_row.get("asked") == "为什么是极限？", last_row)
        code, out, _ = run(home, "state")
        check("state shows asked", "问:" in out and "回:" in out, out)

        archive = root / "backup.zip"
        code, out, _ = run(home, "export", "--to", str(archive))
        check("export exits 0", code == 0 and archive.exists(), out)
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
        check("export contents", "config.json" in names and "learner/state.json" in names
              and any(name.startswith("sessions/") for name in names), str(names))
        check("export map", "learner/map.json" in names and "map.md" in names, str(names))

        # forget: dry-run, then apply, then numbering must not be reused
        code, out, _ = run(home, "forget", "--session", "0001")
        check("forget dry-run", code == 0 and "dry-run" in out, out)
        check("forget dry-run keeps file", len(list((home / "sessions").glob("0001-*.md"))) == 1)

        code, out, _ = run(home, "forget", "--session", "0001", "--apply")
        check("forget apply", code == 0 and "done." in out, out)
        check("forget removed session", not list((home / "sessions").glob("0001-*.md")))
        check("forget made backup", any((home / "backup").iterdir()))

        code, out, _ = run(home, "note", "--topic", "calculus/integral", "--summary", "下一轮",
                           "--consent", "outline")
        match = re.search(r"session (\d{4})", out)
        check("session number not reused", bool(match) and int(match.group(1)) > 3, out)

        # config: bad value rejected, corrupt file fails closed
        code, _, _ = run(home, "config", "--set", "retrieval_mode=cloud")
        check("bad retrieval rejected", code != 0)

        cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
        cfg["retrieval_mode"] = "cloud"
        (home / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        code, out, err = run(home, "state")
        check("corrupt config does not crash", code == 0, err)
        fixed = json.loads((home / "config.json").read_text(encoding="utf-8"))
        check("corrupt config fails closed to local", fixed["retrieval_mode"] == "local", fixed)

        # forget all
        code, out, _ = run(home, "forget", "--all", "--apply")
        check("forget all", code == 0 and "done." in out, out)
        check("forget all cleared sessions", not list((home / "sessions").glob("*.md")))
        check("forget all kept config", (home / "config.json").exists())
        state = json.loads((home / "learner" / "state.json").read_text(encoding="utf-8"))
        check("forget all reset state", not state["goals"] and state["session_counter"] == 0)
        check("forget all removed map.md", not (home / "map.md").exists())
        maps = json.loads((home / "learner" / "map.json").read_text(encoding="utf-8"))
        check("forget all reset map", maps["maps"] == [])

        # hand-written / legacy state must not crash (plain strings, int session ids)
        manual = root / "manual"
        (manual / "learner").mkdir(parents=True)
        (manual / "sessions").mkdir()
        (manual / "learner" / "state.json").write_text(json.dumps({
            "version": 1,
            "session_counter": 1,
            "current_topic": "memory",
            "next_step": "画一张表",
            "goals": ["判断可行性"],
            "capabilities": ["能说清瓶颈在写入端"],
            "questions": ["名词还是动词"],
        }, ensure_ascii=False), encoding="utf-8")
        (manual / "deltas.jsonl").write_text(
            json.dumps({"ts": "2026-10-21", "session": 1, "learned": "x",
                        "did": "y", "want": "z"}) + "\n", encoding="utf-8")
        (manual / "sessions" / "0001-2026-10-21-memory.md").write_text(
            "# 0001 — 2026-10-21\n\n- mode: spark\n- consent: verbatim\n\n"
            "## 用户原话\n\n> 原话\n", encoding="utf-8")
        code, out, err = run(manual, "state")
        check("hand-written state does not crash", code == 0, err)
        check("hand-written goal shown", "判断可行性" in out, out)
        check("hand-written capability shown", "瓶颈在写入端" in out, out)
        code, out, _ = run(manual, "records")
        check("verbatim quotes detected", "yes" in out, out)

        # hand-written map (missing role / status / position) must not crash
        (manual / "learner" / "map.json").write_text(json.dumps({
            "version": 1,
            "maps": [{
                "id": "x", "title": "X",
                "nodes": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}],
                "edges": [{"from": "a", "to": "b"}],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        code, out, err = run(manual, "map", "--action", "show", "--json")
        check("hand-written map tolerated", code == 0, err)
        manual_map = json.loads(out)["maps"][0]
        check("hand-written map normalized",
              manual_map["nodes"][0]["status"] == "unseen"
              and manual_map["position"] == {}, out[:200])

        print("\n%d passed, %d failed" % (passed, failed))
        return 1 if failed else 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
