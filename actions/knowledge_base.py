"""
knowledge_base.py — Segundo cerebro / base de conocimiento personal para NEXO.
Guarda notas, conceptos, referencias, ideas, snippets y los hace buscables.
Persiste en config/knowledge_base.json.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

_KB_FILE = Path(__file__).resolve().parent.parent / "config" / "knowledge_base.json"


def _load() -> dict:
    try:
        return json.loads(_KB_FILE.read_text("utf-8"))
    except Exception:
        return {"entries": [], "last_updated": ""}


def _save(kb: dict):
    _KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    kb["last_updated"] = datetime.now().isoformat()
    _KB_FILE.write_text(json.dumps(kb, indent=2, ensure_ascii=False), "utf-8")


_TYPE_ICONS = {
    "note":     "📝",
    "idea":     "💡",
    "snippet":  "💻",
    "reference":"🔗",
    "fact":     "📌",
    "task":     "✅",
    "question": "❓",
}


def knowledge_base(parameters: dict, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "search").lower().strip()

    # ── add ───────────────────────────────────────────────────────────────────
    if action in ("add", "save", "store"):
        title   = params.get("title", "").strip()
        content = params.get("content", params.get("text", "")).strip()
        if not content:
            return "❌ Especificá content o text."
        kind    = params.get("type", "note").lower()
        tags    = params.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]

        kb = _load()
        eid = f"e{int(time.time())}"
        kb["entries"].append({
            "id": eid,
            "title": title or content[:60],
            "content": content,
            "type": kind,
            "tags": tags,
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
        })
        _save(kb)
        return f"{_TYPE_ICONS.get(kind,'📝')} Guardado en base de conocimiento (ID: {eid})."

    # ── search ────────────────────────────────────────────────────────────────
    elif action in ("search", "find", "buscar"):
        query = params.get("query", params.get("q", "")).strip()
        kind  = params.get("type", "").lower()
        tag   = params.get("tag", "").lower()

        if not query and not kind and not tag:
            return "❌ Especificá query, type o tag."

        kb      = _load()
        pattern = re.compile(query, re.IGNORECASE) if query else None
        results = []

        for e in kb["entries"]:
            if kind and e.get("type", "") != kind:
                continue
            if tag and tag not in [t.lower() for t in e.get("tags", [])]:
                continue
            if pattern:
                searchable = f"{e.get('title','')} {e.get('content','')} {' '.join(e.get('tags',[]))}"
                if not pattern.search(searchable):
                    continue
            results.append(e)

        if not results:
            return f"🔍 Sin resultados para '{query or kind or tag}'."

        lines = [f"🔍 {len(results)} resultado(s):"]
        for e in results[:10]:
            icon = _TYPE_ICONS.get(e.get("type","note"), "📝")
            tags_str = f" [{', '.join(e['tags'])}]" if e.get("tags") else ""
            lines.append(f"\n{icon} [{e['id']}] {e['title']}{tags_str}")
            preview = e["content"][:150].replace("\n", " ")
            lines.append(f"   {preview}{'…' if len(e['content'])>150 else ''}")

        return "\n".join(lines)

    # ── list ──────────────────────────────────────────────────────────────────
    elif action == "list":
        kb   = _load()
        kind = params.get("type", "").lower()
        entries = kb["entries"]
        if kind:
            entries = [e for e in entries if e.get("type") == kind]
        if not entries:
            return "La base de conocimiento está vacía."

        lines = [f"📚 Base de conocimiento ({len(entries)} entradas):"]
        for e in entries[-20:]:
            icon = _TYPE_ICONS.get(e.get("type","note"), "📝")
            tags_str = f" [{', '.join(e['tags'])}]" if e.get("tags") else ""
            lines.append(f"  {icon} [{e['id']}] {e['title']}{tags_str} — {e['created'][:10]}")
        return "\n".join(lines)

    # ── get / read ────────────────────────────────────────────────────────────
    elif action in ("get", "read", "view"):
        eid = str(params.get("entry_id", params.get("id", "")))
        if not eid:
            return "❌ Especificá entry_id."
        kb = _load()
        for e in kb["entries"]:
            if e["id"] == eid:
                icon = _TYPE_ICONS.get(e.get("type","note"), "📝")
                tags_str = f"\n   Tags: {', '.join(e['tags'])}" if e.get("tags") else ""
                return (
                    f"{icon} {e['title']}\n"
                    f"   Tipo: {e.get('type','note')}{tags_str}\n"
                    f"   Creado: {e['created'][:10]}\n\n"
                    f"{e['content']}"
                )
        return f"❌ Entrada '{eid}' no encontrada."

    # ── update ────────────────────────────────────────────────────────────────
    elif action == "update":
        eid     = str(params.get("entry_id", params.get("id", "")))
        content = params.get("content", params.get("text", "")).strip()
        title   = params.get("title", "").strip()
        if not eid:
            return "❌ Especificá entry_id."

        kb = _load()
        for e in kb["entries"]:
            if e["id"] == eid:
                if content:
                    e["content"] = content
                if title:
                    e["title"] = title
                if params.get("tags"):
                    tags = params["tags"]
                    if isinstance(tags, str):
                        tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
                    e["tags"] = tags
                e["updated"] = datetime.now().isoformat()
                _save(kb)
                return f"✅ Entrada '{eid}' actualizada."
        return f"❌ Entrada '{eid}' no encontrada."

    # ── delete ────────────────────────────────────────────────────────────────
    elif action == "delete":
        eid = str(params.get("entry_id", params.get("id", "")))
        if not eid:
            return "❌ Especificá entry_id."
        kb   = _load()
        orig = len(kb["entries"])
        kb["entries"] = [e for e in kb["entries"] if e["id"] != eid]
        if len(kb["entries"]) == orig:
            return f"❌ Entrada '{eid}' no encontrada."
        _save(kb)
        return f"🗑 Entrada '{eid}' eliminada."

    # ── stats ─────────────────────────────────────────────────────────────────
    elif action == "stats":
        kb = _load()
        entries = kb["entries"]
        if not entries:
            return "La base de conocimiento está vacía."
        from collections import Counter
        by_type = Counter(e.get("type","note") for e in entries)
        all_tags: list[str] = []
        for e in entries:
            all_tags.extend(e.get("tags", []))
        top_tags = Counter(all_tags).most_common(5)
        lines = [
            f"📊 Base de conocimiento: {len(entries)} entradas",
            "   Por tipo:",
        ]
        for t, c in by_type.items():
            icon = _TYPE_ICONS.get(t,"📝")
            lines.append(f"     {icon} {t}: {c}")
        if top_tags:
            lines.append("   Tags más usados:")
            for tag, cnt in top_tags:
                lines.append(f"     #{tag}: {cnt}x")
        return "\n".join(lines)

    # ── export ────────────────────────────────────────────────────────────────
    elif action == "export":
        out_path = params.get("path", "").strip()
        kb = _load()
        entries = kb["entries"]
        if not entries:
            return "La base de conocimiento está vacía."
        if not out_path:
            out_path = str(Path.home() / "nexo_knowledge_export.md")

        lines = ["# NEXO — Base de Conocimiento\n"]
        for e in entries:
            icon = _TYPE_ICONS.get(e.get("type","note"), "📝")
            tags_str = f" `{'` `'.join(e['tags'])}`" if e.get("tags") else ""
            lines.append(f"## {icon} {e['title']}{tags_str}\n")
            lines.append(f"*{e.get('type','note')} — {e['created'][:10]}*\n")
            lines.append(f"{e['content']}\n")
            lines.append("---\n")

        Path(out_path).write_text("\n".join(lines), "utf-8")
        return f"📤 Base de conocimiento exportada a '{out_path}' ({len(entries)} entradas)."

    else:
        return (
            f"Acción desconocida: '{action}'. "
            "Opciones: add/save/store, search/find, list, get/read/view, update, delete, stats, export."
        )
