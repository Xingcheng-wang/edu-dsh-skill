#!/usr/bin/env python3
"""edu-dsh workspace CLI.

Only the deterministic parts live here: memory, consent, ownership.
Teaching belongs to the model.

Commands: init, doctor, state, records, goal, cap, question, glossary,
          note, delta, export, forget, config
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

VERSION = "0.5.0"
MIN_PYTHON = (3, 10)

CONSENT_LEVELS = ("off", "outline", "verbatim")
RETRIEVAL_MODES = ("local", "web", "ask", "auto")
CONFIDENCE_LEVELS = ("low", "medium", "high")
SESSION_MODES = ("curiosity", "systematic", "skill", "read", "spark")
MAP_STATUSES = ("unseen", "touched", "practicing", "can-do")
MAP_KINDS = ("concept", "skill", "method", "problem")
MAP_ROLES = ("trunk", "branch")
MAP_RELATIONS = ("prereq", "part-of", "contrast")
MAP_MARKS = {"can-do": "[x]", "practicing": "[~]", "touched": "[.]", "unseen": "[ ]"}

DEFAULT_CONFIG = {
    "version": 1,
    "language": "auto",
    "retrieval_mode": "ask",
    "consent_default": "outline",
    "context_window": 1000000,
    "multimodal": False,
}

DEFAULT_STATE = {
    "version": 1,
    "updated": "",
    "session_counter": 0,
    "current_topic": "",
    "next_step": "",
    "goals": [],
    "capabilities": [],
    "questions": [],
}

PROFILE_TEMPLATE = """# Learner Profile

- 称呼：
- 想做出什么：
- 现在能做什么：
- 卡在哪：
- 喜欢怎么学：
- 不喜欢怎么学：
- 备注：
"""

GLOSSARY_HEADER = (
    "# Glossary\n\n"
    "| term | 全称 | 白话 | 例子 | 首次 |\n"
    "|---|---|---|---|---|\n"
)


# --------------------------------------------------------------------- utils


def today_str() -> str:
    return date.today().isoformat()


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def slugify(text: str, maxlen: int = 48) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^\w一-鿿.-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    return (text or "item")[:maxlen]


def home_of(args) -> Path:
    raw = args.home or os.environ.get("EDU_HOME") or str(Path.home() / ".edu-dsh")
    return Path(raw).expanduser().resolve()


def load_json(path: Path, default):
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit("cannot read %s: %s" % (path, exc))


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(str(tmp), str(path))


def print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def normalize_config(cfg: dict):
    """Fill defaults; fail closed on bad values."""
    cfg = dict(cfg or {})
    changed = False
    for key, value in DEFAULT_CONFIG.items():
        if key not in cfg:
            cfg[key] = value
            changed = True
    if cfg.get("version") != DEFAULT_CONFIG["version"]:
        cfg["version"] = DEFAULT_CONFIG["version"]
        changed = True
    if cfg.get("retrieval_mode") not in RETRIEVAL_MODES:
        cfg["retrieval_mode"] = "local"
        changed = True
        eprint("warning: invalid retrieval_mode; fell back to 'local'")
    if cfg.get("consent_default") not in CONSENT_LEVELS:
        cfg["consent_default"] = "outline"
        changed = True
    return cfg, changed


def _max_session(home: Path) -> int:
    highest = 0
    for path in (home / "sessions").glob("*.md"):
        match = re.match(r"(\d{4})-", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def ensure_home(home: Path, lang: str = "auto") -> Path:
    for rel in ("learner", "sessions", "notes"):
        (home / rel).mkdir(parents=True, exist_ok=True)

    cfg_path = home / "config.json"
    if not cfg_path.exists():
        cfg = dict(DEFAULT_CONFIG)
        cfg["language"] = lang
        save_json(cfg_path, cfg)
    else:
        cfg, changed = normalize_config(load_json(cfg_path, DEFAULT_CONFIG))
        if changed:
            save_json(cfg_path, cfg)

    profile = home / "learner" / "profile.md"
    if not profile.exists():
        profile.write_text(PROFILE_TEMPLATE, encoding="utf-8", newline="\n")

    glossary = home / "learner" / "glossary.md"
    if not glossary.exists():
        glossary.write_text(GLOSSARY_HEADER, encoding="utf-8", newline="\n")

    state_path = home / "learner" / "state.json"
    if not state_path.exists():
        state = json.loads(json.dumps(DEFAULT_STATE))
        state["updated"] = today_str()
        state["session_counter"] = _max_session(home)
        save_json(state_path, state)
    else:
        state = load_json(state_path, DEFAULT_STATE)
        if int(state.get("session_counter", 0)) < _max_session(home):
            state["session_counter"] = _max_session(home)
            save_json(state_path, state)

    map_path = home / "learner" / "map.json"
    if not map_path.exists():
        save_json(map_path, {"version": 1, "maps": []})

    deltas = home / "deltas.jsonl"
    if not deltas.exists():
        deltas.write_text("", encoding="utf-8")

    return home


def _normalize_entries(items, kind: str) -> list:
    """Accept both the CLI shape and hand-written shorthand (plain strings)."""
    out = []
    for index, item in enumerate(items or [], 1):
        if isinstance(item, str):
            entry = {"text": item, "added": ""}
        elif isinstance(item, dict):
            entry = dict(item)
            entry.setdefault("text", entry.get("statement", ""))
        else:
            continue
        if kind == "capabilities":
            entry.setdefault("id", "c%d" % index)
            entry.setdefault("statement", entry.get("text", ""))
            entry.setdefault("basis", "")
            entry.setdefault("confidence", "medium")
            entry.setdefault("updated", "")
        out.append(entry)
    return out


def load_state(home: Path) -> dict:
    state = load_json(home / "learner" / "state.json", DEFAULT_STATE)
    for key, value in DEFAULT_STATE.items():
        state.setdefault(key, value)
    state["goals"] = _normalize_entries(state.get("goals"), "goals")
    state["questions"] = _normalize_entries(state.get("questions"), "questions")
    state["capabilities"] = _normalize_entries(state.get("capabilities"), "capabilities")
    return state


def save_state(home: Path, state: dict) -> None:
    state["updated"] = today_str()
    save_json(home / "learner" / "state.json", state)


def require_consent(args, action: str = "write") -> bool:
    consent = getattr(args, "consent", None)
    if consent is None:
        raise SystemExit("--consent is required for %s (off|outline|verbatim)" % action)
    if consent not in CONSENT_LEVELS:
        raise SystemExit("--consent must be one of %s" % (CONSENT_LEVELS,))
    if consent == "off":
        print("not recorded (consent=off)")
        return False
    return True


def _session_label(value):
    """Hand-written deltas may use an int or 'session 1' instead of '0001'."""
    if isinstance(value, int):
        return "%04d" % value
    if isinstance(value, str):
        match = re.match(r"\s*(\d+)", value)
        if match:
            return "%04d" % int(match.group(1))
    return value


def _read_deltas(home: Path, limit: int | None = None) -> list:
    path = home / "deltas.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        row.setdefault("date", row.get("ts") or "")
        row["session"] = _session_label(row.get("session"))
        rows.append(row)
    return rows[-limit:] if limit else rows


# ------------------------------------------------------------------ knowledge map


def load_maps(home: Path) -> dict:
    data = load_json(home / "learner" / "map.json", {"version": 1, "maps": []})
    if not isinstance(data, dict):
        data = {"version": 1, "maps": []}
    maps = data.get("maps")
    if not isinstance(maps, list):
        maps = []
    clean = []
    for m in maps:
        if not isinstance(m, dict):
            continue
        m.setdefault("id", "")
        m.setdefault("title", m.get("id") or "")
        m.setdefault("goal", "")
        m.setdefault("created", today_str())
        m.setdefault("updated", today_str())
        nodes = []
        for n in m.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            n.setdefault("id", "")
            if not n.get("id"):
                continue
            n.setdefault("title", n["id"])
            n.setdefault("kind", "concept")
            n.setdefault("role", "trunk")
            n.setdefault("status", "unseen")
            n.setdefault("note", "")
            if n["kind"] not in MAP_KINDS:
                n["kind"] = "concept"
            if n["role"] not in MAP_ROLES:
                n["role"] = "trunk"
            if n["status"] not in MAP_STATUSES:
                n["status"] = "unseen"
            nodes.append(n)
        m["nodes"] = nodes
        edges = []
        for e in m.get("edges") or []:
            if not isinstance(e, dict) or not e.get("from") or not e.get("to"):
                continue
            rel = e.get("rel", "prereq")
            if rel not in MAP_RELATIONS:
                rel = "prereq"
            edges.append({"from": e["from"], "to": e["to"], "rel": rel})
        m["edges"] = edges
        if not isinstance(m.get("position"), dict):
            m["position"] = {}
        clean.append(m)
    data["maps"] = clean
    data["version"] = 1
    return data


def save_maps(home: Path, data: dict) -> None:
    for m in data.get("maps", []):
        m["updated"] = today_str()
    save_json(home / "learner" / "map.json", data)


def _find_map(data: dict, topic: str):
    return next((m for m in data.get("maps", []) if m.get("id") == topic), None)


def _find_node(m: dict, node_id: str):
    return next((n for n in m.get("nodes", []) if n.get("id") == node_id), None)


def _node_title(m: dict, node_id: str) -> str:
    node = _find_node(m, node_id)
    return (node or {}).get("title") or node_id


def _upstream(m: dict, node_id: str) -> list:
    return [e["from"] for e in m.get("edges", [])
            if e.get("rel") == "prereq" and e.get("to") == node_id]


def _downstream(m: dict, node_id: str) -> list:
    return [e["to"] for e in m.get("edges", [])
            if e.get("rel") == "prereq" and e.get("from") == node_id]


def _tree_lines(m: dict, node_ids: list, children: dict, pos_node: str,
                depth: int = 0, seen: set | None = None) -> list:
    if seen is None:
        seen = set()
    lines = []
    for node_id in node_ids:
        if node_id in seen or _find_node(m, node_id) is None:
            continue
        seen.add(node_id)
        node = _find_node(m, node_id)
        mark = MAP_MARKS.get(node.get("status", "unseen"), "[ ]")
        here = "   ← 你在这里" if node_id == pos_node else ""
        note = ("  —— " + node["note"]) if node.get("note") else ""
        lines.append("%s%s %s%s%s" % ("  " * depth, mark,
                                      node.get("title") or node_id, note, here))
        kids = [kid for kid in children.get(node_id, []) if _find_node(m, kid)]
        if kids:
            lines.extend(_tree_lines(m, kids, children, pos_node, depth + 1, seen))
    return lines


def render_map_text(data: dict, state: dict) -> str:
    questions = state.get("questions") or []
    blocks = []
    for m in data.get("maps", []):
        lines = ["# 知识地图：%s" % (m.get("title") or m.get("id")), ""]
        if m.get("goal"):
            lines += ["方向：%s" % m["goal"], ""]
        pos = m.get("position") or {}
        pos_node = pos.get("node") or ""
        if pos_node:
            why = (" —— " + pos["why"]) if pos.get("why") else ""
            lines.append("你在这里：%s%s" % (_node_title(m, pos_node), why))
            ups = _upstream(m, pos_node)
            downs = _downstream(m, pos_node)
            lines.append("上游：%s" % ("、".join(_node_title(m, u) for u in ups) or "（无）"))
            lines.append("下游：%s" % ("、".join(_node_title(m, d) for d in downs) or "（无）"))
            if pos.get("next"):
                lines.append("下一步：%s" % pos["next"])
            lines.append("")

        prereq = [e for e in m.get("edges", []) if e.get("rel") == "prereq"]
        children = {}
        for edge in prereq:
            children.setdefault(edge["from"], []).append(edge["to"])
        has_parent = {edge["to"] for edge in prereq}
        nodes = m.get("nodes", [])
        roots = [n["id"] for n in nodes if n.get("role") == "trunk" and n["id"] not in has_parent]
        if not roots:
            roots = [n["id"] for n in nodes if n.get("role") == "trunk"]
        lines += ["## 主干", ""]
        tree = _tree_lines(m, roots, children, pos_node) if roots else []
        if tree:
            lines += tree
        else:
            lines.append("（还没有节点）")
        lines.append("")

        branches = [n for n in nodes if n.get("role") == "branch"]
        contrasts = [e for e in m.get("edges", []) if e.get("rel") == "contrast"]
        if branches or contrasts:
            lines += ["## 侧枝 / 对照", ""]
            for node in branches:
                mark = MAP_MARKS.get(node.get("status", "unseen"), "[ ]")
                here = "   ← 你在这里" if node["id"] == pos_node else ""
                lines.append("- %s %s%s" % (mark, node.get("title") or node["id"], here))
            for edge in contrasts:
                lines.append("- %s ↔ %s" % (_node_title(m, edge["from"]),
                                             _node_title(m, edge["to"])))
            lines.append("")

        if len(nodes) > 12:
            lines += ["（图较大：%d 个节点，考虑拆分或裁剪。）" % len(nodes), ""]

        lines += ["## 开放问题", ""]
        related = [q for q in questions
                   if isinstance(q, dict) and q.get("node") in {n["id"] for n in nodes}]
        if related:
            for q in related:
                lines.append("- %s（%s）" % (q.get("text", ""), _node_title(m, q["node"])))
        else:
            lines.append("- （暂无）")
        blocks.append("\n".join(lines).rstrip())
    if not blocks:
        return "# 知识地图\n\n还没有地图。先一起画一张。\n"
    return "\n\n---\n\n".join(blocks)


def write_map_file(home: Path, data: dict, state: dict) -> str:
    text = render_map_text(data, state)
    path = home / "map.md"
    if data.get("maps"):
        path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    elif path.exists():
        path.unlink()
    return text


def cmd_map(args) -> int:
    home = ensure_home(home_of(args))
    action = args.action
    data = load_maps(home)

    if action == "show":
        state = load_state(home)
        if args.topic:
            m = _find_map(data, args.topic)
            if m is None:
                raise SystemExit("map not found: %s" % args.topic)
            data = {"version": 1, "maps": [m]}
        if args.json:
            print_json(data)
            return 0
        if args.topic:
            print(render_map_text(data, state))
        else:
            print(write_map_file(home, data, state))
        return 0

    if not require_consent(args, "map"):
        return 0
    if not args.topic:
        raise SystemExit("map --action %s needs --topic" % action)

    m = _find_map(data, args.topic)
    if action == "new":
        if m is not None:
            raise SystemExit("map already exists: %s" % args.topic)
        if not args.title:
            raise SystemExit("map new needs --title")
        m = {"id": args.topic, "title": args.title, "goal": args.goal or "",
             "created": today_str(), "updated": today_str(),
             "nodes": [], "edges": [], "position": {}}
        data["maps"].append(m)
        save_maps(home, data)
        write_map_file(home, data, load_state(home))
        print("map created: %s (%s)" % (m["id"], m["title"]))
        return 0

    if m is None:
        raise SystemExit("map not found: %s" % args.topic)

    if action == "add":
        if not args.node or not args.title:
            raise SystemExit("map add needs --node and --title")
        if _find_node(m, args.node) is not None:
            raise SystemExit("node already exists: %s" % args.node)
        if len(m["nodes"]) >= 12:
            eprint("warning: map has %d nodes; consider splitting or pruning" % len(m["nodes"]))
        m["nodes"].append({
            "id": args.node.strip(),
            "title": args.title.strip(),
            "kind": args.kind or "concept",
            "role": args.role or "trunk",
            "status": args.status or "unseen",
            "note": (args.note or "").strip(),
        })
        save_maps(home, data)
        write_map_file(home, data, load_state(home))
        print("node added: %s (%s)" % (m["nodes"][-1]["id"], m["nodes"][-1]["title"]))
        return 0

    if action == "link":
        if not args.from_node or not args.to_node:
            raise SystemExit("map link needs --from and --to")
        if _find_node(m, args.from_node) is None:
            raise SystemExit("node not found: %s" % args.from_node)
        if _find_node(m, args.to_node) is None:
            raise SystemExit("node not found: %s" % args.to_node)
        if args.from_node == args.to_node:
            raise SystemExit("cannot link a node to itself")
        rel = args.rel or "prereq"
        if any(e["from"] == args.from_node and e["to"] == args.to_node
               and e["rel"] == rel for e in m["edges"]):
            print("link already exists: %s -[%s]-> %s" % (args.from_node, rel, args.to_node))
            return 0
        m["edges"].append({"from": args.from_node, "to": args.to_node, "rel": rel})
        save_maps(home, data)
        write_map_file(home, data, load_state(home))
        print("link added: %s -[%s]-> %s" % (args.from_node, rel, args.to_node))
        return 0

    if action == "status":
        if not args.node or not args.status:
            raise SystemExit("map status needs --node and --status")
        node = _find_node(m, args.node)
        if node is None:
            raise SystemExit("node not found: %s" % args.node)
        node["status"] = args.status
        save_maps(home, data)
        write_map_file(home, data, load_state(home))
        print("status: %s -> %s" % (args.node, args.status))
        return 0

    if action == "position":
        if not args.node:
            raise SystemExit("map position needs --node")
        if _find_node(m, args.node) is None:
            raise SystemExit("node not found: %s" % args.node)
        m["position"] = {"node": args.node, "why": args.why or "", "next": args.next or ""}
        save_maps(home, data)
        write_map_file(home, data, load_state(home))
        print("position: %s" % args.node)
        return 0

    if action == "drop":
        if args.node:
            node = _find_node(m, args.node)
            if node is None:
                raise SystemExit("node not found: %s" % args.node)
            m["nodes"] = [n for n in m["nodes"] if n["id"] != args.node]
            m["edges"] = [e for e in m["edges"]
                          if e["from"] != args.node and e["to"] != args.node]
            if (m.get("position") or {}).get("node") == args.node:
                m["position"] = {}
            message = "node removed: %s" % args.node
        else:
            data["maps"] = [item for item in data["maps"] if item["id"] != args.topic]
            message = "map removed: %s" % args.topic
        save_maps(home, data)
        write_map_file(home, data, load_state(home))
        print(message)
        return 0

    raise SystemExit("unknown map action: %s" % action)


# ------------------------------------------------------------------ commands


def cmd_init(args) -> int:
    home = ensure_home(home_of(args), lang=args.lang)
    print("workspace: %s" % home)
    print("next: open SKILL.md, start the first conversation. No corpus needed —")
    print("      point the model at any local file you want to learn from.")
    return 0


def cmd_doctor(args) -> int:
    home = home_of(args)
    print("edu-dsh  : %s" % VERSION)
    print("python   : %s" % sys.version.split()[0])
    print("platform : %s" % sys.platform)
    print("home     : %s" % home)

    writable = True
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        writable = False
        print("writable : NO (%s)" % exc)
    if writable:
        print("writable : yes")

    cfg_path = home / "config.json"
    if cfg_path.exists():
        cfg, changed = normalize_config(load_json(cfg_path, DEFAULT_CONFIG))
        print("retrieval: %s" % cfg.get("retrieval_mode"))
        print("consent  : %s (default)" % cfg.get("consent_default"))
        print("context  : %s tokens" % cfg.get("context_window"))
        print("multimodal: %s" % cfg.get("multimodal"))
        if changed:
            print("config   : needs repair (run init; invalid values fail closed)")
    else:
        print("config   : missing (run init)")

    state = load_json(home / "learner" / "state.json", DEFAULT_STATE)
    print("goals    : %d" % len(state.get("goals") or []))
    print("can-do   : %d" % len(state.get("capabilities") or []))
    print("questions: %d" % len(state.get("questions") or []))
    print("sessions : %d" % len(list((home / "sessions").glob("*.md"))))
    print("deltas   : %d" % len(_read_deltas(home)))
    maps = load_maps(home).get("maps") or []
    print("maps     : %d map(s), %d node(s)" % (
        len(maps), sum(len(m.get("nodes") or []) for m in maps)))
    return 0


def cmd_state(args) -> int:
    home = ensure_home(home_of(args))
    cfg, _ = normalize_config(load_json(home / "config.json", DEFAULT_CONFIG))
    state = load_state(home)
    sessions = sorted((home / "sessions").glob("*.md"))

    if args.json:
        print_json({
            "home": str(home),
            "config": cfg,
            "state": state,
            "maps": load_maps(home).get("maps") or [],
            "sessions": [p.name for p in sessions[-10:]],
            "recent_deltas": _read_deltas(home, 5),
        })
        return 0

    print("workspace: %s" % home)
    print("retrieval: %s   consent: %s" % (
        cfg.get("retrieval_mode"), cfg.get("consent_default")))
    if state.get("current_topic"):
        print("current  : %s" % state.get("current_topic"))
    if state.get("next_step"):
        print("next     : %s" % state.get("next_step"))

    maps = load_maps(home).get("maps") or []
    if maps:
        print("\nmaps:")
        for m in maps[:5]:
            pos = m.get("position") or {}
            node = pos.get("node")
            if node:
                ups = _upstream(m, node)
                downs = _downstream(m, node)
                print("  %s → %s（上：%s；下：%s）" % (
                    m.get("title") or m.get("id"), _node_title(m, node),
                    "、".join(_node_title(m, u) for u in ups) or "无",
                    "、".join(_node_title(m, d) for d in downs) or "无"))
            else:
                print("  %s（未定位）" % (m.get("title") or m.get("id")))
    else:
        print("\nmaps     : (none)")

    goals = state.get("goals") or []
    if goals:
        print("\ngoals:")
        for index, goal in enumerate(goals, 1):
            print("  %d. %s" % (index, goal.get("text", "")))

    caps = state.get("capabilities") or []
    if caps:
        print("\ncan do:")
        for cap in caps:
            print("  [%s] %s  (%s, %s)" % (
                cap.get("id", "?"), cap.get("statement", ""),
                cap.get("confidence", "medium"), cap.get("updated", "")))
    else:
        print("\ncan do : (nothing recorded yet)")

    questions = state.get("questions") or []
    if questions:
        print("\nopen questions:")
        for index, question in enumerate(questions, 1):
            print("  %d. %s" % (index, question.get("text", "")))

    if sessions:
        print("\nlast session: %s" % sessions[-1].name)
    deltas = _read_deltas(home, 1)
    if deltas:
        last = deltas[-1]
        print("last delta  : 会 %s | 做 %s | 想 %s" % (
            last.get("learned") or "-",
            last.get("did") or "-",
            last.get("want") or "-"))
        if last.get("alone"):
            print("              独自: %s" % last["alone"])
        if last.get("verified"):
            print("              验证: %s" % last["verified"])
        if last.get("asked"):
            print("              问: %s" % last["asked"])
        if last.get("returned"):
            print("              回: %s" % last["returned"])
    return 0


def _session_meta(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta = {
        "file": path.name,
        "topic": "",
        "node": "",
        "mode": "",
        "consent": "legacy",
        "quotes": ("## 原话" in text) or ("## 用户原话" in text),
    }
    for line in text.splitlines():
        if line.startswith("- topic:"):
            meta["topic"] = line.split(":", 1)[1].strip()
        elif line.startswith("- node:"):
            meta["node"] = line.split(":", 1)[1].strip()
        elif line.startswith("- mode:"):
            meta["mode"] = line.split(":", 1)[1].strip()
        elif line.startswith("- consent:"):
            meta["consent"] = line.split(":", 1)[1].strip()
    return meta


def cmd_records(args) -> int:
    home = ensure_home(home_of(args))
    rows = [_session_meta(path) for path in sorted((home / "sessions").glob("*.md"))]
    if args.json:
        print_json(rows)
        return 0
    if not rows:
        print("no session records.")
        return 0
    print("%-40s %-10s %-8s %-7s %s" % ("FILE", "MODE", "CONSENT", "QUOTES", "TOPIC"))
    for row in rows:
        print("%-40s %-10s %-8s %-7s %s" % (
            row["file"], row["mode"] or "-", row["consent"],
            "yes" if row["quotes"] else "no", row["topic"] or "-"))
    return 0


def cmd_goal(args) -> int:
    home = ensure_home(home_of(args))
    state = load_state(home)
    goals = state.setdefault("goals", [])

    if args.list or (not args.add and args.drop is None):
        if not goals:
            print("no goals yet.")
            return 0
        for index, goal in enumerate(goals, 1):
            print("%d. %s" % (index, goal.get("text", "")))
        return 0

    if not require_consent(args, "goal"):
        return 0

    if args.add:
        goals.append({"text": args.add.strip(), "added": today_str()})
        save_state(home, state)
        print("goal added: %s" % args.add.strip())
        return 0

    index = _parse_index(args.drop, len(goals), "goal")
    removed = goals.pop(index - 1)
    save_state(home, state)
    print("goal removed: %s" % removed.get("text", ""))
    return 0


def cmd_question(args) -> int:
    home = ensure_home(home_of(args))
    state = load_state(home)
    items = state.setdefault("questions", [])

    if args.list or (not args.add and args.drop is None):
        if not items:
            print("no open questions yet.")
            return 0
        for index, item in enumerate(items, 1):
            print("%d. %s" % (index, item.get("text", "")))
        return 0

    if not require_consent(args, "question"):
        return 0

    if args.add:
        entry = {"text": args.add.strip(), "added": today_str()}
        if getattr(args, "node", None):
            entry["node"] = args.node.strip()
        items.append(entry)
        save_state(home, state)
        write_map_file(home, load_maps(home), state)
        print("question added: %s" % args.add.strip())
        return 0

    index = _parse_index(args.drop, len(items), "question")
    removed = items.pop(index - 1)
    save_state(home, state)
    write_map_file(home, load_maps(home), state)
    print("question removed: %s" % removed.get("text", ""))
    return 0


def _parse_index(raw, length: int, label: str) -> int:
    try:
        index = int(raw)
    except (TypeError, ValueError):
        raise SystemExit("--drop needs a 1-based number")
    if not 1 <= index <= length:
        raise SystemExit("%s #%d does not exist (have %d)" % (label, index, length))
    return index


def _next_cap_id(caps: list) -> str:
    highest = 0
    for cap in caps:
        match = re.fullmatch(r"c(\d+)", str(cap.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return "c%d" % (highest + 1)


def cmd_cap(args) -> int:
    home = ensure_home(home_of(args))
    state = load_state(home)
    caps = state.setdefault("capabilities", [])

    if args.list or (not args.add and not args.drop):
        if not caps:
            print("no can-do statements yet.")
            return 0
        for cap in caps:
            print("[%s] %s  (%s, %s)" % (
                cap.get("id", "?"), cap.get("statement", ""),
                cap.get("confidence", "medium"), cap.get("updated", "")))
            if cap.get("basis"):
                print("      依据: %s" % cap.get("basis"))
        return 0

    if not require_consent(args, "capability"):
        return 0

    if args.add:
        if not args.statement:
            raise SystemExit("cap --add needs --statement")
        if args.confidence and args.confidence not in CONFIDENCE_LEVELS:
            raise SystemExit("confidence must be one of %s" % (CONFIDENCE_LEVELS,))
        cap = {
            "id": _next_cap_id(caps),
            "statement": args.statement.strip(),
            "basis": (args.basis or "").strip(),
            "confidence": args.confidence or "medium",
            "updated": today_str(),
        }
        caps.append(cap)
        save_state(home, state)
        print("capability added: [%s] %s" % (cap["id"], cap["statement"]))
        return 0

    target = next((cap for cap in caps if cap.get("id") == args.drop), None)
    if target is None:
        raise SystemExit("capability %s not found" % args.drop)
    caps.remove(target)
    save_state(home, state)
    print("capability removed: [%s] %s" % (target.get("id"), target.get("statement")))
    return 0


def cmd_glossary(args) -> int:
    home = ensure_home(home_of(args))
    path = home / "learner" / "glossary.md"

    if args.list or not args.add:
        print(path.read_text(encoding="utf-8").rstrip())
        return 0

    if not require_consent(args, "glossary"):
        return 0
    if not (args.term and args.full and args.plain):
        raise SystemExit("glossary --add needs --term, --full, --plain")

    term = args.term.strip()
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    if re.search(r"^\|\s*%s\s*\|" % re.escape(term.lower()), lowered, re.MULTILINE):
        print("already recorded: %s" % term)
        return 0

    def cell(value: str) -> str:
        return (value or "").replace("|", "/").replace("\n", " ").strip()

    row = "| %s | %s | %s | %s | %s |\n" % (
        cell(term), cell(args.full), cell(args.plain), cell(args.example or "-"), today_str())
    path.write_text(text.rstrip("\n") + "\n" + row, encoding="utf-8", newline="\n")
    print("glossary added: %s" % term)
    return 0


def cmd_note(args) -> int:
    home = ensure_home(home_of(args))
    if not require_consent(args, "session note"):
        return 0
    if not args.topic or not args.summary:
        raise SystemExit("note needs --topic and --summary")

    state = load_state(home)
    number = int(state.get("session_counter", 0)) + 1
    state["session_counter"] = number
    state["current_topic"] = args.topic.strip()
    if args.next:
        state["next_step"] = args.next.strip()
    save_state(home, state)

    mode = args.mode or "curiosity"
    filename = "%04d-%s-%s.md" % (number, today_str(), slugify(args.topic))
    path = home / "sessions" / filename

    lines = [
        "# Session %04d — %s — %s" % (number, today_str(), mode),
        "",
        "- topic: %s" % args.topic.strip(),
    ]
    if args.node:
        lines.append("- node: %s" % args.node.strip())
    lines += [
        "- mode: %s" % mode,
        "- consent: %s" % args.consent,
        "",
        "## 概要（转述）",
        "",
        args.summary.strip(),
    ]
    if args.next:
        lines += ["", "## 下一步", "", "- %s" % args.next.strip()]
    if args.consent == "verbatim":
        lines += ["", "## 原话（已同意）", ""]
        evidence = [item for item in (args.evidence or []) if item.strip()]
        lines += ["- %s" % item.strip() for item in evidence] or ["- （未记录）"]
    elif args.evidence:
        eprint("note: --evidence ignored unless --consent verbatim")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("session %04d written: %s" % (number, filename))
    return 0


def cmd_delta(args) -> int:
    home = ensure_home(home_of(args))
    if not require_consent(args, "delta"):
        return 0
    if not any([args.learned, args.did, args.want]):
        raise SystemExit("delta needs at least one of --learned / --did / --want")

    state = load_state(home)
    session = args.session or "last"
    if session in ("last", "latest"):
        session = "%04d" % int(state.get("session_counter", 0))
    else:
        match = re.match(r"(\d+)", session)
        session = "%04d" % int(match.group(1)) if match else session

    record = {
        "date": today_str(),
        "session": session,
        "learned": (args.learned or "").strip(),
        "did": (args.did or "").strip(),
        "want": (args.want or "").strip(),
    }
    if args.alone:
        record["alone"] = args.alone.strip()
    if args.verified:
        record["verified"] = args.verified.strip()
    if getattr(args, "asked", None):
        record["asked"] = args.asked.strip()
    if getattr(args, "returned", None):
        record["returned"] = args.returned.strip()
    if args.evidence:
        if args.consent == "verbatim":
            record["evidence"] = [item.strip() for item in args.evidence]
        else:
            eprint("note: --evidence ignored unless --consent verbatim")

    with (home / "deltas.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("delta recorded for session %s" % session)
    return 0


def cmd_export(args) -> int:
    home = ensure_home(home_of(args))
    target = Path(args.to).expanduser()
    if target.suffix.lower() == ".zip":
        archive = target
        archive.parent.mkdir(parents=True, exist_ok=True)
    else:
        target.mkdir(parents=True, exist_ok=True)
        archive = target / ("edu-export-%s.zip" % today_str())

    entries = ["config.json", "learner", "sessions", "notes", "deltas.jsonl", "map.md"]
    with zipfile.ZipFile(str(archive), "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in entries:
            source = home / rel
            if source.is_file():
                zf.write(str(source), rel)
            elif source.is_dir():
                for path in sorted(source.rglob("*")):
                    if path.is_file():
                        zf.write(str(path), str(path.relative_to(home)))
    print("exported: %s" % archive)
    return 0


def _backup(home: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = home / "backup" / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for rel in ("config.json", "learner", "sessions", "notes", "deltas.jsonl", "map.md"):
        source = home / rel
        if source.is_file():
            shutil.copy2(str(source), str(dest / rel))
        elif source.is_dir():
            shutil.copytree(str(source), str(dest / rel), dirs_exist_ok=True)
    return dest


def cmd_forget(args) -> int:
    home = ensure_home(home_of(args))
    sessions = sorted((home / "sessions").glob("*.md"))
    actions = []

    if args.session:
        match = re.match(r"(\d+)", args.session)
        if not match:
            raise SystemExit("--session needs a session number, e.g. 0001")
        number = int(match.group(1))
        targets = [path for path in sessions if path.name.startswith("%04d-" % number)]
        if not targets:
            raise SystemExit("session %04d not found" % number)
        actions.extend("delete %s" % path.name for path in targets)
        actions.append("drop delta rows for session %04d" % number)
    else:
        actions.append("delete all learner state, glossary, profile, notes")
        actions.append("delete all sessions, deltas, and the knowledge map")
        actions.append("keep config.json")

    for action in actions:
        print(action)
    if not args.apply:
        print("dry-run only; run again with --apply to delete (a backup will be made)")
        return 0

    backup = _backup(home)
    print("backup: %s" % backup)

    if args.session:
        match = re.match(r"(\d+)", args.session)
        number = int(match.group(1))
        for path in sessions:
            if path.name.startswith("%04d-" % number):
                path.unlink()
        rows = [row for row in _read_deltas(home) if row.get("session") != "%04d" % number]
        (home / "deltas.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8", newline="\n")
    else:
        for rel in ("learner", "sessions", "notes"):
            shutil.rmtree(home / rel, ignore_errors=True)
        (home / "deltas.jsonl").write_text("", encoding="utf-8")
        map_md = home / "map.md"
        if map_md.exists():
            map_md.unlink()
        ensure_home(home)

    print("done.")
    return 0


def cmd_config(args) -> int:
    home = ensure_home(home_of(args))
    cfg_path = home / "config.json"
    cfg, _ = normalize_config(load_json(cfg_path, DEFAULT_CONFIG))

    if not args.set_values:
        print_json(cfg)
        return 0

    for pair in args.set_values:
        if "=" not in pair:
            raise SystemExit("expected KEY=VALUE, got %r" % pair)
        key, raw = pair.split("=", 1)
        key, raw = key.strip(), raw.strip()
        if key == "retrieval_mode":
            if raw not in RETRIEVAL_MODES:
                raise SystemExit("retrieval_mode must be one of %s" % (RETRIEVAL_MODES,))
            cfg[key] = raw
        elif key == "consent_default":
            if raw not in CONSENT_LEVELS:
                raise SystemExit("consent_default must be one of %s" % (CONSENT_LEVELS,))
            cfg[key] = raw
        elif key == "language":
            if raw not in ("auto", "zh", "en"):
                raise SystemExit("language must be auto, zh or en")
            cfg[key] = raw
        elif key == "context_window":
            try:
                cfg[key] = int(raw)
            except ValueError:
                raise SystemExit("context_window must be an integer")
            if cfg[key] < 8000:
                raise SystemExit("context_window must be >= 8000")
        elif key == "multimodal":
            cfg[key] = raw.lower() in ("1", "true", "yes", "on")
        else:
            raise SystemExit("unknown config key: %s" % key)

    save_json(cfg_path, cfg)
    print_json(cfg)
    return 0


# ---------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edu_dsh.py",
        description="edu-dsh workspace CLI: memory, consent, ownership.",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_home(sp):
        sp.add_argument("--home", default=None,
                        help="workspace (default: $EDU_HOME or ~/.edu-dsh)")

    def add_consent(sp, required=False):
        sp.add_argument("--consent", default=None, choices=CONSENT_LEVELS,
                        required=required)

    p = sub.add_parser("init", help="create a workspace")
    add_home(p)
    p.add_argument("--lang", default="auto", choices=("auto", "zh", "en"))
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("doctor", help="check the workspace")
    add_home(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("state", help="show goals, can-do statements, questions")
    add_home(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("records", help="list session records")
    add_home(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_records)

    p = sub.add_parser("map", help="build and show the knowledge map")
    add_home(p)
    p.add_argument("--action", required=True,
                   choices=("new", "add", "link", "status", "position", "drop", "show"))
    p.add_argument("--topic", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--goal", default=None)
    p.add_argument("--node", default=None)
    p.add_argument("--from", dest="from_node", default=None)
    p.add_argument("--to", dest="to_node", default=None)
    p.add_argument("--rel", default=None, choices=MAP_RELATIONS)
    p.add_argument("--kind", default=None, choices=MAP_KINDS)
    p.add_argument("--role", default=None, choices=MAP_ROLES)
    p.add_argument("--status", default=None, choices=MAP_STATUSES)
    p.add_argument("--why", default=None)
    p.add_argument("--next", default=None)
    p.add_argument("--note", default=None,
                   help="what problem this node answers (optional)")
    p.add_argument("--json", action="store_true")
    add_consent(p)
    p.set_defaults(func=cmd_map)

    p = sub.add_parser("goal", help="add, drop or list goals")
    add_home(p)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--add", default=None)
    group.add_argument("--drop", default=None)
    group.add_argument("--list", action="store_true")
    add_consent(p)
    p.set_defaults(func=cmd_goal)

    p = sub.add_parser("cap", help="add, drop or list can-do statements")
    add_home(p)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--add", action="store_true")
    group.add_argument("--drop", default=None)
    group.add_argument("--list", action="store_true")
    p.add_argument("--statement", default=None)
    p.add_argument("--basis", default=None, help="paraphrased evidence, not a quote")
    p.add_argument("--confidence", default=None, choices=CONFIDENCE_LEVELS)
    add_consent(p)
    p.set_defaults(func=cmd_cap)

    p = sub.add_parser("question", help="add, drop or list open questions")
    add_home(p)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--add", default=None)
    group.add_argument("--drop", default=None)
    group.add_argument("--list", action="store_true")
    p.add_argument("--node", default=None, help="attach the question to a map node")
    add_consent(p)
    p.set_defaults(func=cmd_question)

    p = sub.add_parser("glossary", help="add or list explained terms")
    add_home(p)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--add", action="store_true")
    group.add_argument("--list", action="store_true")
    p.add_argument("--term", default=None)
    p.add_argument("--full", default=None)
    p.add_argument("--plain", default=None)
    p.add_argument("--example", default=None)
    add_consent(p)
    p.set_defaults(func=cmd_glossary)

    p = sub.add_parser("note", help="write a session note")
    add_home(p)
    p.add_argument("--topic", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--mode", default=None, choices=SESSION_MODES)
    p.add_argument("--node", default=None, help="map node covered this session")
    p.add_argument("--next", default=None)
    p.add_argument("--evidence", action="append", default=[],
                   help="verbatim only; ignored under outline")
    add_consent(p, required=True)
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("delta", help="record what the user gained this round")
    add_home(p)
    p.add_argument("--session", default="last")
    p.add_argument("--learned", default=None)
    p.add_argument("--did", default=None)
    p.add_argument("--want", default=None)
    p.add_argument("--alone", default=None,
                   help="what the user did without AI this round (optional)")
    p.add_argument("--verified", default=None,
                   help="how it was verified: test/compiler/peer/reality/self (optional)")
    p.add_argument("--asked", default=None,
                   help="a question the user asked on their own (optional)")
    p.add_argument("--returned", default=None,
                   help="an old question the user came back to (optional)")
    p.add_argument("--evidence", action="append", default=[])
    add_consent(p, required=True)
    p.set_defaults(func=cmd_delta)

    p = sub.add_parser("export", help="export learning data")
    add_home(p)
    p.add_argument("--to", required=True)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("forget", help="delete learning data")
    add_home(p)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--session", default=None)
    group.add_argument("--all", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_forget)

    p = sub.add_parser("config", help="show or change configuration")
    add_home(p)
    p.add_argument("--set", dest="set_values", action="append", default=[],
                   metavar="KEY=VALUE")
    p.set_defaults(func=cmd_config)

    return parser


def main(argv=None) -> int:
    if sys.version_info < MIN_PYTHON:
        raise SystemExit("Python %s+ required; found %s." % (
            ".".join(map(str, MIN_PYTHON)), sys.version.split()[0]))
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
