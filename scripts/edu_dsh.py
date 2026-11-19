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
import sqlite3
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

VERSION = "0.15.2"
MIN_PYTHON = (3, 10)

CONSENT_LEVELS = ("off", "outline", "verbatim")
RETRIEVAL_MODES = ("local", "web", "ask", "auto")
CONFIDENCE_LEVELS = ("low", "medium", "high")
SESSION_MODES = ("curiosity", "systematic", "skill", "read", "spark")
MAP_STATUSES = ("unseen", "touched", "practicing", "can-do")
MAP_KINDS = ("concept", "skill", "method", "problem")
MAP_ROLES = ("trunk", "branch")
MAP_RELATIONS = ("prereq", "part-of", "contrast")
MAP_MODES = ("mainline", "branch", "review")
PROGRESS_LEAPS = ("first", "second")
PROGRESS_LIMITS = {"context": 160, "summary": 80, "evidence": 160}
PROGRESS_LABELS = {
    "first": "第一次飞跃（感性 → 理性）",
    "second": "第二次飞跃（理性 → 实践）",
}
BLINDSPOT_KINDS = ("concept", "principle", "skill", "method", "boundary")
BLINDSPOT_STATUSES = ("unknown", "noticed", "explained", "applied", "verified")
BLINDSPOT_KIND_LABELS = {
    "concept": "概念",
    "principle": "原理",
    "skill": "技能",
    "method": "方法",
    "boundary": "边界",
}
BLINDSPOT_STATUS_LABELS = {
    "unknown": "未识别",
    "noticed": "已发现",
    "explained": "能解释",
    "applied": "能应用",
    "verified": "已确认",
}
BLINDSPOT_LIMITS = {"title": 80, "context": 160}
KB_TYPES = ("fact", "concept", "principle", "procedure", "method", "meta")
KB_TYPE_LABELS = {
    "fact": "事实",
    "concept": "概念",
    "principle": "原理",
    "procedure": "程序",
    "method": "方法",
    "meta": "元认知",
}
KB_GRANULARITIES = ("atom", "cluster", "meta")
KB_GRANULARITY_LABELS = {"atom": "原子", "cluster": "组合", "meta": "元"}
KB_STATES = ("unpracticed", "perceptual", "rational", "practiced", "consolidated")
KB_STATE_LABELS = {
    "unpracticed": "未实践",
    "perceptual": "感性认识",
    "rational": "理性认识",
    "practiced": "实践检验",
    "consolidated": "反复检验",
}
KB_RELATIONS = ("prereq", "part-of", "contrast", "application", "analogy")
KB_RELATION_LABELS = {
    "prereq": "先修",
    "part-of": "组成",
    "contrast": "对照",
    "application": "应用",
    "analogy": "类比",
}
KB_DISCIPLINES = ("math", "cs", "physics", "chemistry", "biology", "engineering",
                  "language", "humanities", "social-science", "arts", "other")
KB_DISCIPLINE_LABELS = {
    "math": "数学",
    "cs": "计算机",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "engineering": "工程",
    "language": "语言",
    "humanities": "人文",
    "social-science": "社科",
    "arts": "艺术",
    "other": "其他",
}
KB_DISCIPLINE_ALIASES = {
    "数学": "math",
    "计算机": "cs",
    "编程": "cs",
    "物理": "physics",
    "化学": "chemistry",
    "生物": "biology",
    "工程": "engineering",
    "语言": "language",
    "人文": "humanities",
    "社科": "social-science",
    "艺术": "arts",
    "其他": "other",
}
KB_INTERVALS = (1, 3, 7, 14, 30, 60, 120)
KB_DB_VERSION = 1
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

    progress = home / "learner" / "progress.jsonl"
    if not progress.exists():
        progress.write_text("", encoding="utf-8")

    blindspots = home / "learner" / "blindspots.jsonl"
    if not blindspots.exists():
        blindspots.write_text("", encoding="utf-8")

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


# ------------------------------------------------------------------ progress


def load_progress(home: Path, limit: int | None = None) -> list:
    path = home / "learner" / "progress.jsonl"
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
        row.setdefault("date", "")
        row["session"] = _session_label(row.get("session"))
        if row.get("leap") not in PROGRESS_LEAPS:
            row["leap"] = "first"
        rows.append(row)
    return rows[-limit:] if limit else rows


def _next_progress_id(rows: list) -> str:
    highest = 0
    for row in rows:
        match = re.match(r"p-(\d+)", str(row.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return "p-%04d" % (highest + 1)


def _safe_file_part(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "-", (text or "").strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "学习"


def _progress_title(home: Path, record: dict) -> str:
    topic = (record.get("topic") or "").strip()
    if not topic:
        return "学习"
    for m in load_maps(home).get("maps") or []:
        if m.get("id") == topic:
            return (m.get("title") or topic).strip()
    return topic


def progress_file_path(home: Path, record: dict) -> Path:
    title = _safe_file_part(_progress_title(home, record))
    return home / "learner" / ("%s（学习主线）进步记录.md" % title)


def render_progress_file(records: list) -> str:
    lines = []
    for row in records:
        label = "第一次飞跃" if row.get("leap") == "first" else "第二次飞跃"
        lines.append("> %s · %s" % (row.get("date") or "", label))
        lines.append("> 上下文：%s" % (row.get("context") or ""))
        lines.append("> 概述：%s" % (row.get("summary") or ""))
        if row.get("evidence"):
            lines.append("> 证据：%s" % row["evidence"])
        if row.get("blindspot"):
            lines.append("> 盲区：%s" % row["blindspot"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_progress_files(home: Path, records: list) -> list:
    groups = {}
    for row in records:
        path = progress_file_path(home, row)
        groups.setdefault(path, []).append(row)

    written = []
    learner = home / "learner"
    learner.mkdir(parents=True, exist_ok=True)
    for path, rows in groups.items():
        text = render_progress_file(rows)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append((path, text))

    current = {path.name for path, _ in written}
    for path in learner.glob("*（学习主线）进步记录.md"):
        if path.name not in current:
            path.unlink()
    legacy = learner / "progress.md"
    if legacy.exists():
        legacy.unlink()
    return written


def _resolve_session(state: dict, value) -> str:
    if not value or value in ("last", "latest"):
        return "%04d" % int(state.get("session_counter", 0))
    return _session_label(value)


# ------------------------------------------------------------------ blind spots


def load_blindspots(home: Path, limit: int | None = None) -> list:
    path = home / "learner" / "blindspots.jsonl"
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
        row.setdefault("date", "")
        row["session"] = _session_label(row.get("session"))
        if row.get("kind") not in BLINDSPOT_KINDS:
            row["kind"] = "concept"
        if row.get("status") not in BLINDSPOT_STATUSES:
            row["status"] = "noticed"
        rows.append(row)
    return rows[-limit:] if limit else rows


def _next_blindspot_id(rows: list) -> str:
    highest = 0
    for row in rows:
        match = re.match(r"bs-(\d+)", str(row.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return "bs-%04d" % (highest + 1)


def _blindspot_title(home: Path, record: dict) -> str:
    topic = (record.get("topic") or "").strip()
    if not topic:
        return "学习"
    for m in load_maps(home).get("maps") or []:
        if m.get("id") == topic:
            return (m.get("title") or topic).strip()
    return topic


def blindspot_file_path(home: Path, record: dict) -> Path:
    title = _safe_file_part(_blindspot_title(home, record))
    return home / "learner" / ("%s（主线）知识盲区.md" % title)


def render_blindspot_file(records: list) -> str:
    lines = []
    for row in records:
        kind = BLINDSPOT_KIND_LABELS.get(row.get("kind"), "概念")
        status = BLINDSPOT_STATUS_LABELS.get(row.get("status"), "已发现")
        lines.append("> %s · %s · %s · %s" % (
            row.get("date") or "", row.get("id") or "", kind, status))
        lines.append("> 盲区：%s" % (row.get("title") or ""))
        lines.append("> 上下文：%s" % (row.get("context") or ""))
        if row.get("progress_id"):
            lines.append("> 关联进步：%s" % row["progress_id"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_blindspot_files(home: Path, records: list) -> list:
    groups = {}
    for row in records:
        path = blindspot_file_path(home, row)
        groups.setdefault(path, []).append(row)

    written = []
    learner = home / "learner"
    learner.mkdir(parents=True, exist_ok=True)
    for path, rows in groups.items():
        text = render_blindspot_file(rows)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append((path, text))

    current = {path.name for path, _ in written}
    for path in learner.glob("*（主线）知识盲区.md"):
        if path.name not in current:
            path.unlink()
    return written


def save_blindspots(home: Path, records: list) -> None:
    (home / "learner" / "blindspots.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
        encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ knowledge db (MVP)


def kb_path(home: Path) -> Path:
    return home / "learner" / "knowledge.db"


def _kb_schema_sql() -> str:
    types = ",".join("'%s'" % item for item in KB_TYPES)
    grans = ",".join("'%s'" % item for item in KB_GRANULARITIES)
    states = ",".join("'%s'" % item for item in KB_STATES)
    rels = ",".join("'%s'" % item for item in KB_RELATIONS)
    return """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        domain TEXT NOT NULL DEFAULT '',
        type TEXT NOT NULL CHECK(type IN (%s)),
        granularity TEXT NOT NULL CHECK(granularity IN (%s)),
        state TEXT NOT NULL CHECK(state IN (%s)),
        conditions TEXT NOT NULL DEFAULT '',
        context TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL,
        updated TEXT NOT NULL,
        last_reviewed TEXT NOT NULL DEFAULT '',
        review_count INTEGER NOT NULL DEFAULT 0,
        interval_days INTEGER NOT NULL DEFAULT 0,
        ease REAL NOT NULL DEFAULT 2.5,
        next_review TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS item_disciplines (
        item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        discipline TEXT NOT NULL,
        PRIMARY KEY (item_id, discipline)
    );
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        context TEXT NOT NULL DEFAULT '',
        evidence TEXT NOT NULL DEFAULT '',
        date TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        date TEXT NOT NULL,
        result TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS links (
        from_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        to_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        rel TEXT NOT NULL CHECK(rel IN (%s)),
        PRIMARY KEY (from_id, to_id, rel)
    );
    """ % (types, grans, states, rels)


def kb_connect(home: Path) -> sqlite3.Connection:
    kb_path(home).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(kb_path(home)))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def kb_init(home: Path) -> None:
    conn = kb_connect(home)
    try:
        conn.executescript(_kb_schema_sql())
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(KB_DB_VERSION),))
        conn.commit()
    finally:
        conn.close()


def _kb_discipline(value: str) -> str:
    raw = (value or "").strip().lower()
    return KB_DISCIPLINE_ALIASES.get(raw, raw or "other")


def _kb_next_id(conn: sqlite3.Connection) -> str:
    highest = 0
    for row in conn.execute("SELECT id FROM items WHERE id LIKE 'k-%'"):
        match = re.match(r"k-(\d+)", row["id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return "k-%04d" % (highest + 1)


def _kb_add_item(conn, *, title, disciplines, domain, item_type, granularity,
                 state, conditions="", context="", evidence="", date_str=None):
    title = (title or "").strip()
    if not title:
        raise SystemExit("kb add needs --title")
    if item_type not in KB_TYPES:
        raise SystemExit("kb add needs --type %s" % "|".join(KB_TYPES))
    if granularity not in KB_GRANULARITIES:
        raise SystemExit("kb add needs --granularity %s" % "|".join(KB_GRANULARITIES))
    if state not in KB_STATES:
        raise SystemExit("kb add needs --state %s" % "|".join(KB_STATES))
    names = [_kb_discipline(item) for item in (disciplines or ["other"])]
    names = list(dict.fromkeys(name for name in names if name))
    if not names:
        names = ["other"]
    date_str = date_str or today_str()
    item_id = _kb_next_id(conn)
    conn.execute(
        "INSERT INTO items(id,title,domain,type,granularity,state,conditions,context,"
        "created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (item_id, title, (domain or "").strip(), item_type, granularity, state,
         (conditions or "").strip(), (context or "").strip(), date_str, date_str))
    conn.executemany(
        "INSERT INTO item_disciplines(item_id, discipline) VALUES(?,?)",
        [(item_id, name) for name in names])
    conn.execute(
        "INSERT INTO events(item_id, kind, context, evidence, date) VALUES(?,?,?,?,?)",
        (item_id, "added", (context or "").strip(), (evidence or "").strip(), date_str))
    return item_id


def _kb_query_items(conn, discipline=None, item_type=None, state=None,
                    due=False, limit=50):
    clauses = []
    params = []
    if discipline:
        clauses.append("d.discipline = ?")
        params.append(_kb_discipline(discipline))
    if item_type:
        clauses.append("i.type = ?")
        params.append(item_type)
    if state:
        clauses.append("i.state = ?")
        params.append(state)
    if due:
        clauses.append("i.next_review != '' AND i.next_review <= ?")
        params.append(today_str())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        "SELECT i.*, GROUP_CONCAT(d.discipline) AS disciplines "
        "FROM items i LEFT JOIN item_disciplines d ON d.item_id = i.id"
        + where +
        " GROUP BY i.id ORDER BY "
        "CASE WHEN i.next_review = '' THEN 1 ELSE 0 END, i.next_review, i.id LIMIT ?")
    params.append(int(limit or 50))
    return [dict(row) for row in conn.execute(sql, params)]


def _kb_show_text(rows: list) -> str:
    lines = [
        "# 知识库",
        "",
        "| 学科 | 领域 | 标题 | 类型 | 粒度 | 阶段 | 下次复习 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            row.get("disciplines") or "other",
            row.get("domain") or "",
            row.get("title") or "",
            KB_TYPE_LABELS.get(row.get("type"), row.get("type")),
            KB_GRANULARITY_LABELS.get(row.get("granularity"), row.get("granularity")),
            KB_STATE_LABELS.get(row.get("state"), row.get("state")),
            row.get("next_review") or "—",
        ))
    return "\n".join(lines).rstrip() + "\n"


def _kb_state_advance(state: str, result: str) -> str:
    index = KB_STATES.index(state) if state in KB_STATES else 0
    if result == "fail":
        return KB_STATES[max(index - 1, 0)]
    if state == "practiced":
        return "consolidated"
    return state


def _kb_review_item(conn, item_id: str, result: str, note: str = "") -> dict:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise SystemExit("kb item not found: %s" % item_id)
    if result not in ("pass", "fail"):
        raise SystemExit("kb review needs --result pass|fail")
    item = dict(row)
    count = int(item.get("review_count", 0)) + 1
    ease = float(item.get("ease", 2.5))
    interval = int(item.get("interval_days", 0))
    if result == "pass":
        ease = min(3.0, ease + 0.1)
        interval = 1 if interval <= 0 else min(180, max(1, round(interval * ease)))
    else:
        ease = max(1.3, ease - 0.2)
        interval = 1
    next_review = (date.today() + timedelta(days=interval)).isoformat()
    new_state = _kb_state_advance(item.get("state", "unpracticed"), result)
    conn.execute(
        "UPDATE items SET state=?, updated=?, last_reviewed=?, review_count=?, "
        "interval_days=?, ease=?, next_review=? WHERE id=?",
        (new_state, today_str(), today_str(), count, interval, ease, next_review, item_id))
    conn.execute(
        "INSERT INTO reviews(item_id, date, result, note) VALUES(?,?,?,?)",
        (item_id, today_str(), result, (note or "").strip()))
    return {
        "id": item_id,
        "state": new_state,
        "interval_days": interval,
        "next_review": next_review,
        "review_count": count,
    }


def _kb_export(conn, target: Path) -> dict:
    data = {
        "schema_version": KB_DB_VERSION,
        "exported_at": today_str(),
        "items": [dict(row) for row in conn.execute("SELECT * FROM items ORDER BY id")],
        "disciplines": [dict(row) for row in conn.execute(
            "SELECT * FROM item_disciplines ORDER BY item_id, discipline")],
        "events": [dict(row) for row in conn.execute(
            "SELECT * FROM events ORDER BY id")],
        "reviews": [dict(row) for row in conn.execute(
            "SELECT * FROM reviews ORDER BY id")],
        "links": [dict(row) for row in conn.execute(
            "SELECT * FROM links ORDER BY from_id, to_id, rel")],
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    return data


def kb_import(home: Path, default_discipline: str = "other", force: bool = False) -> dict:
    kb_init(home)
    conn = kb_connect(home)
    try:
        existing = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
        if existing and not force:
            raise SystemExit("knowledge.db already has items; use --force to rebuild")
        if force:
            for table in ("links", "events", "reviews", "item_disciplines", "items"):
                conn.execute("DELETE FROM %s" % table)

        blindspots = load_blindspots(home)
        progress = load_progress(home)
        state_map = {
            "unknown": "unpracticed",
            "noticed": "unpracticed",
            "explained": "rational",
            "applied": "practiced",
            "verified": "consolidated",
        }
        kind_map = {
            "concept": "concept",
            "principle": "principle",
            "skill": "procedure",
            "method": "method",
            "boundary": "concept",
        }
        imported = {"items": 0, "events": 0, "reviews": 0, "links": 0}
        blind_ids = set()
        for row in blindspots:
            item_id = row.get("id") or _kb_next_id(conn)
            title = row.get("title") or row.get("context") or item_id
            item_type = kind_map.get(row.get("kind"), "concept")
            state = state_map.get(row.get("status"), "unpracticed")
            conn.execute(
                "INSERT OR REPLACE INTO items(id,title,domain,type,granularity,state,"
                "conditions,context,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (item_id, title, row.get("topic") or "", item_type, "atom", state,
                 "边界/适用条件（导入时待补）" if row.get("kind") == "boundary" else "",
                 row.get("context") or "", row.get("date") or today_str(),
                 row.get("updated") or row.get("date") or today_str()))
            conn.execute(
                "INSERT OR IGNORE INTO item_disciplines(item_id, discipline) VALUES(?,?)",
                (item_id, _kb_discipline(default_discipline)))
            conn.execute(
                "INSERT INTO events(item_id, kind, context, evidence, date) "
                "VALUES(?,?,?,?,?)",
                (item_id, "blindspot_declared", row.get("context") or "",
                 "", row.get("date") or today_str()))
            imported["items"] += 1
            imported["events"] += 1
            blind_ids.add(item_id)

        for row in progress:
            blindspot = row.get("blindspot") or ""
            kind = "first_leap" if row.get("leap") == "first" else "second_leap"
            if blindspot and blindspot in blind_ids:
                conn.execute(
                    "INSERT INTO events(item_id, kind, context, evidence, date) "
                    "VALUES(?,?,?,?,?)",
                    (blindspot, kind, row.get("context") or "",
                     row.get("evidence") or "", row.get("date") or today_str()))
                target = "rational" if kind == "first_leap" else "practiced"
                current = conn.execute(
                    "SELECT state FROM items WHERE id = ?", (blindspot,)).fetchone()["state"]
                if KB_STATES.index(target) > KB_STATES.index(current):
                    conn.execute(
                        "UPDATE items SET state=?, updated=? WHERE id=?",
                        (target, today_str(), blindspot))
                imported["events"] += 1
                continue
            item_id = row.get("id") or _kb_next_id(conn)
            state = "rational" if kind == "first_leap" else "practiced"
            title = row.get("summary") or row.get("context") or item_id
            conn.execute(
                "INSERT OR REPLACE INTO items(id,title,domain,type,granularity,state,"
                "conditions,context,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (item_id, title, row.get("topic") or "", "concept", "atom", state,
                 "", row.get("context") or "", row.get("date") or today_str(),
                 today_str()))
            conn.execute(
                "INSERT OR IGNORE INTO item_disciplines(item_id, discipline) VALUES(?,?)",
                (item_id, _kb_discipline(default_discipline)))
            conn.execute(
                "INSERT INTO events(item_id, kind, context, evidence, date) "
                "VALUES(?,?,?,?,?)",
                (item_id, kind, row.get("context") or "",
                 row.get("evidence") or "", row.get("date") or today_str()))
            imported["items"] += 1
            imported["events"] += 1

        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('imported_at', ?)",
            (today_str(),))
        conn.commit()
        return imported
    finally:
        conn.close()


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
        pos = m["position"]
        node_ids = {n["id"] for n in nodes}
        if not pos.get("node") or pos.get("node") not in node_ids:
            m["position"] = {}
        else:
            mode = pos.get("mode") or "mainline"
            if mode not in MAP_MODES:
                mode = "mainline"
            ret = pos.get("return_to") or ""
            if mode in ("branch", "review"):
                if not ret or ret == pos["node"] or ret not in node_ids:
                    mode = "mainline"
                    ret = ""
            else:
                mode = "mainline"
                ret = ""
            pos["mode"] = mode
            if ret:
                pos["return_to"] = ret
            else:
                pos.pop("return_to", None)
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
                depth: int = 0, seen: set | None = None,
                bookmark_node: str = "") -> list:
    if seen is None:
        seen = set()
    lines = []
    for node_id in node_ids:
        if node_id in seen or _find_node(m, node_id) is None:
            continue
        seen.add(node_id)
        node = _find_node(m, node_id)
        mark = MAP_MARKS.get(node.get("status", "unseen"), "[ ]")
        tags = []
        if node_id == pos_node:
            tags.append("你在这里")
        if bookmark_node and node_id == bookmark_node and node_id != pos_node:
            tags.append("主线")
        here = ("   ← " + " · ".join(tags)) if tags else ""
        note = ("  —— " + node["note"]) if node.get("note") else ""
        lines.append("%s%s %s%s%s" % ("  " * depth, mark,
                                      node.get("title") or node_id, note, here))
        kids = [kid for kid in children.get(node_id, []) if _find_node(m, kid)]
        if kids:
            lines.extend(_tree_lines(m, kids, children, pos_node, depth + 1, seen,
                                     bookmark_node))
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
        pos_mode = pos.get("mode") or "mainline"
        return_to = pos.get("return_to") or ""
        if pos_node:
            mode_label = ""
            if pos_mode == "branch":
                mode_label = "（临时 · 分支）"
            elif pos_mode == "review":
                mode_label = "（临时 · 回头）"
            why = (" —— " + pos["why"]) if pos.get("why") else ""
            lines.append("你在这里：%s%s%s" % (_node_title(m, pos_node),
                                              mode_label, why))
            if return_to:
                lines.append("主线：%s" % _node_title(m, return_to))
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
        tree = _tree_lines(m, roots, children, pos_node,
                           bookmark_node=return_to) if roots else []
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
                tags = []
                if node["id"] == pos_node:
                    tags.append("你在这里")
                if return_to and node["id"] == return_to and node["id"] != pos_node:
                    tags.append("主线")
                here = ("   ← " + " · ".join(tags)) if tags else ""
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
        mode = args.mode
        return_to = args.return_to or ""
        if mode is None:
            mode = "branch" if return_to else "mainline"
        if mode == "mainline" and return_to:
            raise SystemExit("mainline position does not take --return-to")
        if mode in ("branch", "review"):
            if not return_to:
                raise SystemExit("map position --mode %s needs --return-to" % mode)
            if return_to == args.node:
                raise SystemExit("--return-to must differ from --node")
            if _find_node(m, return_to) is None:
                raise SystemExit("return-to node not found: %s" % return_to)
        position = {"node": args.node, "mode": mode,
                    "why": args.why or "", "next": args.next or ""}
        if return_to:
            position["return_to"] = return_to
        m["position"] = position
        save_maps(home, data)
        write_map_file(home, data, load_state(home))
        suffix = "" if mode == "mainline" else " (%s)" % mode
        print("position: %s%s" % (args.node, suffix))
        return 0

    if action == "drop":
        if args.node:
            node = _find_node(m, args.node)
            if node is None:
                raise SystemExit("node not found: %s" % args.node)
            m["nodes"] = [n for n in m["nodes"] if n["id"] != args.node]
            m["edges"] = [e for e in m["edges"]
                          if e["from"] != args.node and e["to"] != args.node]
            pos = m.get("position") or {}
            if pos.get("node") == args.node:
                m["position"] = {}
            elif pos.get("return_to") == args.node:
                pos.pop("return_to", None)
                pos["mode"] = "mainline"
                m["position"] = pos
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
    print("progress : %d record(s)" % len(load_progress(home)))
    print("blindspots: %d record(s)" % len(load_blindspots(home)))
    if kb_path(home).exists():
        try:
            conn = kb_connect(home)
            count = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"]
            conn.close()
            print("kb       : %d item(s)" % count)
        except sqlite3.Error:
            print("kb       : needs repair")
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
            "progress": load_progress(home)[-5:],
            "blindspots": load_blindspots(home)[-10:],
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
                mode = pos.get("mode") or "mainline"
                ret = pos.get("return_to") or ""
                tag = ""
                if mode in ("branch", "review") and ret:
                    tag = "（%s；主线 %s）" % (
                        "分支" if mode == "branch" else "回头",
                        _node_title(m, ret))
                print("  %s → %s%s（上：%s；下：%s）" % (
                    m.get("title") or m.get("id"), _node_title(m, node), tag,
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

    progress = load_progress(home)
    if progress:
        last_progress = progress[-1]
        label = "第一次飞跃" if last_progress.get("leap") == "first" else "第二次飞跃"
        print("progress    : %s · %s（%s）" % (
            label, last_progress.get("summary", ""), last_progress.get("date", "")))
        print("              file: %s" % progress_file_path(home, last_progress))
    else:
        print("progress    : (nothing recorded yet)")

    blinds = load_blindspots(home)
    if blinds:
        open_rows = [row for row in blinds if row.get("status") != "verified"]
        print("\nblindspots:")
        for row in open_rows[:5]:
            print("  [%s] %s %s %s" % (
                BLINDSPOT_STATUS_LABELS.get(row.get("status"), "已发现"),
                row.get("id"), BLINDSPOT_KIND_LABELS.get(row.get("kind"), "概念"),
                row.get("title", "")))
        if not open_rows:
            print("  (all verified)")
        print("  file: %s" % blindspot_file_path(home, blinds[-1]))
    else:
        print("\nblindspots: (none)")
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


def _add_progress_record(home: Path, *, context, summary, leap, evidence="",
                         topic="", node="", session="last", blindspot=""):
    context = (context or "").strip()
    summary = (summary or "").strip()
    for prefix in ("第一次飞跃：", "第一次飞跃:", "第二次飞跃：", "第二次飞跃:"):
        if summary.startswith(prefix):
            summary = summary[len(prefix):].strip()
            break
    if not context or not summary or leap not in PROGRESS_LEAPS:
        raise SystemExit(
            "progress add needs --context, --summary and --leap first|second")

    for field, value in (("context", context), ("summary", summary)):
        limit = PROGRESS_LIMITS[field]
        if len(value) > limit:
            raise SystemExit("progress --%s must be <= %d chars (got %d)" % (
                field, limit, len(value)))

    evidence = (evidence or "").strip()
    if len(evidence) > PROGRESS_LIMITS["evidence"]:
        raise SystemExit("progress --evidence must be <= %d chars (got %d)" % (
            PROGRESS_LIMITS["evidence"], len(evidence)))

    records = load_progress(home)
    state = load_state(home)
    record = {
        "id": _next_progress_id(records),
        "date": today_str(),
        "session": _resolve_session(state, session),
        "leap": leap,
        "context": context,
        "summary": summary,
    }
    if topic:
        record["topic"] = topic.strip()
    if node:
        record["node"] = node.strip()
    if evidence:
        record["evidence"] = evidence
    if blindspot:
        record["blindspot"] = blindspot

    with (home / "learner" / "progress.jsonl").open(
            "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    write_progress_files(home, records + [record])
    return record


def cmd_progress(args) -> int:
    home = ensure_home(home_of(args))
    records = load_progress(home)

    if args.action == "show":
        shown = records[-args.limit:] if args.limit and args.limit > 0 else records
        write_progress_files(home, records)
        if args.json:
            print_json(shown)
            return 0
        if not shown:
            print("> 还没有记录。一次真正的进步，至少要有具体上下文和一句抽象概述。")
            return 0
        groups = {}
        for row in shown:
            groups.setdefault(progress_file_path(home, row), []).append(row)
        for path, rows in groups.items():
            print("> %s" % path)
            print(render_progress_file(rows).rstrip())
            print()
        return 0

    if not require_consent(args, "progress"):
        return 0

    record = _add_progress_record(
        home, context=args.context, summary=args.summary, leap=args.leap,
        evidence=args.evidence or "", topic=args.topic or "",
        node=args.node or "", session=args.session)
    print("progress recorded: %s (%s)" % (record["id"], record["leap"]))
    return 0


def _find_blindspot(records: list, blindspot_id: str):
    return next((row for row in records if row.get("id") == blindspot_id), None)


def cmd_blindspot(args) -> int:
    home = ensure_home(home_of(args))
    records = load_blindspots(home)

    if args.action == "list":
        shown = records
        if args.status:
            shown = [row for row in shown if row.get("status") == args.status]
        if args.json:
            print_json(shown)
            return 0
        if not shown:
            print("blindspots: (none)")
            return 0
        for row in shown:
            print("[%s] %s %s %s" % (
                BLINDSPOT_STATUS_LABELS.get(row.get("status"), "已发现"),
                row.get("id"), BLINDSPOT_KIND_LABELS.get(row.get("kind"), "概念"),
                row.get("title", "")))
        return 0

    if args.action == "show":
        write_blindspot_files(home, records)
        shown = records[-args.limit:] if args.limit and args.limit > 0 else records
        if args.json:
            print_json(shown)
            return 0
        if not shown:
            print("> 还没有记录知识盲区。")
            return 0
        groups = {}
        for row in shown:
            groups.setdefault(blindspot_file_path(home, row), []).append(row)
        for path, rows in groups.items():
            print("> %s" % path)
            print(render_blindspot_file(rows).rstrip())
            print()
        return 0

    if not require_consent(args, "blindspot"):
        return 0

    if args.action == "add":
        title = (args.title or "").strip()
        context = (args.context or "").strip()
        kind = args.kind
        if not title or not context or kind not in BLINDSPOT_KINDS:
            raise SystemExit(
                "blindspot add needs --title, --kind concept|principle|skill|method|boundary "
                "and --context; if the granularity is unclear, ask the user")
        for field, value in (("title", title), ("context", context)):
            limit = BLINDSPOT_LIMITS[field]
            if len(value) > limit:
                raise SystemExit("blindspot --%s must be <= %d chars (got %d)" % (
                    field, limit, len(value)))
        state = load_state(home)
        record = {
            "id": _next_blindspot_id(records),
            "date": today_str(),
            "session": _resolve_session(state, args.session),
            "title": title,
            "kind": kind,
            "context": context,
            "status": "noticed",
        }
        if args.topic:
            record["topic"] = args.topic.strip()
        if args.node:
            record["node"] = args.node.strip()
        save_blindspots(home, records + [record])
        write_blindspot_files(home, records + [record])
        print("blindspot recorded: %s (%s)" % (record["id"], kind))
        return 0

    if args.action == "status":
        if not args.id or args.status not in BLINDSPOT_STATUSES:
            raise SystemExit("blindspot status needs --id and --status")
        row = _find_blindspot(records, args.id)
        if row is None:
            raise SystemExit("blindspot not found: %s" % args.id)
        if args.status in ("explained", "applied"):
            raise SystemExit(
                "use blindspot resolve to reach explained/applied "
                "and link a progress record")
        if args.status == "verified" and row.get("status") != "applied":
            raise SystemExit(
                "blindspot must be applied before verified; "
                "use blindspot resolve --leap second first")
        row["status"] = args.status
        row["updated"] = today_str()
        save_blindspots(home, records)
        write_blindspot_files(home, records)
        print("blindspot status: %s -> %s" % (row["id"], args.status))
        return 0

    if args.action == "resolve":
        if not args.id or args.leap not in PROGRESS_LEAPS:
            raise SystemExit("blindspot resolve needs --id and --leap first|second")
        row = _find_blindspot(records, args.id)
        if row is None:
            raise SystemExit("blindspot not found: %s" % args.id)
        progress = _add_progress_record(
            home, context=args.context, summary=args.summary, leap=args.leap,
            evidence=args.evidence or "", topic=args.topic or row.get("topic", ""),
            node=args.node or row.get("node", ""), session=args.session,
            blindspot=row["id"])
        row["status"] = "explained" if args.leap == "first" else "applied"
        row["progress_id"] = progress["id"]
        row["updated"] = today_str()
        save_blindspots(home, records)
        write_blindspot_files(home, records)
        print("blindspot resolved: %s -> %s (%s)" % (
            row["id"], progress["id"], row["status"]))
        return 0

    if args.action == "drop":
        if not args.id:
            raise SystemExit("blindspot drop needs --id")
        row = _find_blindspot(records, args.id)
        if row is None:
            raise SystemExit("blindspot not found: %s" % args.id)
        remaining = [item for item in records if item.get("id") != args.id]
        save_blindspots(home, remaining)
        write_blindspot_files(home, remaining)
        print("blindspot removed: %s" % args.id)
        return 0

    raise SystemExit("unknown blindspot action: %s" % args.action)


def cmd_kb(args) -> int:
    home = ensure_home(home_of(args))
    action = args.action

    if action == "init":
        kb_init(home)
        print("knowledge.db ready: %s" % kb_path(home))
        return 0

    if action == "import":
        if not require_consent(args, "kb import"):
            return 0
        discipline = (args.discipline or ["other"])[0]
        result = kb_import(home, default_discipline=discipline, force=args.force)
        print("imported: %d item(s), %d event(s)" % (
            result.get("items", 0), result.get("events", 0)))
        return 0

    if not kb_path(home).exists():
        kb_init(home)
    conn = kb_connect(home)
    try:
        if action == "add":
            if not require_consent(args, "kb add"):
                return 0
            if not args.discipline:
                raise SystemExit(
                    "kb add needs --discipline (math|cs|...; ask the user if unsure)")
            item_id = _kb_add_item(
                conn, title=args.title, disciplines=args.discipline,
                domain=args.domain, item_type=args.kb_type,
                granularity=args.granularity, state=args.state or "unpracticed",
                conditions=args.conditions, context=args.context,
                evidence=args.evidence)
            conn.commit()
            print("kb item added: %s" % item_id)
            return 0

        if action in ("list", "due"):
            discipline = args.discipline[0] if args.discipline else None
            rows = _kb_query_items(
                conn, discipline=discipline, item_type=args.kb_type,
                state=args.state, due=(args.due or action == "due"),
                limit=args.limit)
            if args.json:
                print_json(rows)
                return 0
            if not rows:
                print("kb: (none)")
                return 0
            for row in rows:
                print("[%s] %s %s/%s · %s · %s%s" % (
                    KB_STATE_LABELS.get(row["state"], row["state"]), row["id"],
                    KB_TYPE_LABELS.get(row["type"], row["type"]),
                    KB_GRANULARITY_LABELS.get(row["granularity"], row["granularity"]),
                    row.get("disciplines") or "other", row["title"],
                    (" · due %s" % row["next_review"]) if row.get("next_review") else ""))
            return 0

        if action == "show":
            rows = _kb_query_items(conn, limit=100000)
            text = _kb_show_text(rows)
            path = home / "learner" / "knowledge.md"
            path.write_text(text, encoding="utf-8", newline="\n")
            print("knowledge view: %s" % path)
            return 0

        if action == "review":
            if not require_consent(args, "kb review"):
                return 0
            result = _kb_review_item(conn, args.id or "", args.result or "",
                                     args.note or "")
            conn.commit()
            print("kb review: %s -> %s, next %s" % (
                result["id"], result["state"], result["next_review"]))
            return 0

        if action == "link":
            if not require_consent(args, "kb link"):
                return 0
            if not args.from_id or not args.to or args.rel not in KB_RELATIONS:
                raise SystemExit(
                    "kb link needs --from, --to and --rel %s" % "|".join(KB_RELATIONS))
            for item_id in (args.from_id, args.to):
                if conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone() is None:
                    raise SystemExit("kb item not found: %s" % item_id)
            conn.execute(
                "INSERT OR IGNORE INTO links(from_id, to_id, rel) VALUES(?,?,?)",
                (args.from_id, args.to, args.rel))
            conn.commit()
            print("kb link: %s -%s-> %s" % (args.from_id, args.rel, args.to))
            return 0

        if action == "export":
            if not args.to:
                raise SystemExit("kb export needs --to <file.json>")
            target = Path(args.to).expanduser()
            _kb_export(conn, target)
            print("kb exported: %s" % target)
            return 0
    finally:
        conn.close()

    raise SystemExit("unknown kb action: %s" % action)


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
        actions.append("drop progress rows for session %04d" % number)
        actions.append("drop blindspots added in session %04d and clear dead links" % number)
    else:
        actions.append("delete all learner state, glossary, profile, notes")
        actions.append("delete all sessions, deltas, progress, blindspots, and the knowledge map")
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
        progress_rows = [row for row in load_progress(home)
                         if row.get("session") != "%04d" % number]
        removed_progress_ids = {row.get("id") for row in load_progress(home)
                                if row.get("session") == "%04d" % number}
        (home / "learner" / "progress.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in progress_rows),
            encoding="utf-8", newline="\n")
        write_progress_files(home, progress_rows)
        blinds = [row for row in load_blindspots(home)
                  if row.get("session") != "%04d" % number]
        for row in blinds:
            if row.get("progress_id") in removed_progress_ids:
                row.pop("progress_id", None)
                row["status"] = "noticed"
                row["updated"] = today_str()
        save_blindspots(home, blinds)
        write_blindspot_files(home, blinds)
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
    p.add_argument("--mode", default=None, choices=MAP_MODES)
    p.add_argument("--return-to", dest="return_to", default=None,
                   help="mainline node id when position is a temporary branch/review")
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

    p = sub.add_parser("progress", help="record and show cognitive progress")
    add_home(p)
    p.add_argument("--action", required=True, choices=("add", "show"))
    p.add_argument("--context", default=None,
                   help="concrete scene: what happened, where, what changed (<=160 chars)")
    p.add_argument("--summary", default=None,
                   help="abstract summary: which leap and what changed (<=80 chars)")
    p.add_argument("--leap", default=None, choices=PROGRESS_LEAPS)
    p.add_argument("--evidence", default=None,
                   help="file line, artifact or observation (<=160 chars)")
    p.add_argument("--topic", default=None)
    p.add_argument("--node", default=None)
    p.add_argument("--session", default="last")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    add_consent(p)
    p.set_defaults(func=cmd_progress)

    p = sub.add_parser("blindspot", help="record and review knowledge blind spots")
    add_home(p)
    p.add_argument("--action", required=True,
                   choices=("add", "list", "show", "status", "resolve", "drop"))
    p.add_argument("--id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--kind", default=None, choices=BLINDSPOT_KINDS)
    p.add_argument("--context", default=None,
                   help="simple context of where the blind spot showed up (<=160 chars)")
    p.add_argument("--status", default=None, choices=BLINDSPOT_STATUSES)
    p.add_argument("--leap", default=None, choices=PROGRESS_LEAPS)
    p.add_argument("--summary", default=None)
    p.add_argument("--evidence", default=None)
    p.add_argument("--topic", default=None)
    p.add_argument("--node", default=None)
    p.add_argument("--session", default="last")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    add_consent(p)
    p.set_defaults(func=cmd_blindspot)

    p = sub.add_parser("kb", help="SQLite knowledge base (parallel MVP)")
    add_home(p)
    p.add_argument("--action", required=True,
                   choices=("init", "import", "add", "list", "show", "review",
                            "due", "link", "export"))
    p.add_argument("--id", default=None)
    p.add_argument("--title", default=None)
    p.add_argument("--discipline", action="append", default=[])
    p.add_argument("--domain", default="")
    p.add_argument("--type", dest="kb_type", default=None, choices=KB_TYPES)
    p.add_argument("--granularity", default=None, choices=KB_GRANULARITIES)
    p.add_argument("--state", default=None, choices=KB_STATES)
    p.add_argument("--conditions", default="")
    p.add_argument("--context", default="")
    p.add_argument("--evidence", default="")
    p.add_argument("--result", default=None, choices=("pass", "fail"))
    p.add_argument("--note", default="")
    p.add_argument("--from", dest="from_id", default=None)
    p.add_argument("--to", dest="to", default=None)
    p.add_argument("--rel", default=None, choices=KB_RELATIONS)
    p.add_argument("--due", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    add_consent(p)
    p.set_defaults(func=cmd_kb)

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
