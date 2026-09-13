"""Per-agent cache backed by markdown files under code/cache/{agent_name}.md.

Agents read the cache before regenerating expensive artifacts (SQL results, OCR
extractions). The cache is a simple keyed document store; values are plain text.
"""

from __future__ import annotations

from config import SETTINGS

_SEP = "\n\n===ENTRY===\n\n"


def _cache_path(agent_name: str):
    SETTINGS.cache_dir.mkdir(parents=True, exist_ok=True)
    return SETTINGS.cache_dir / f"{agent_name}.md"


def read_cache(agent_name: str) -> str:
    p = _cache_path(agent_name)
    return p.read_text() if p.exists() else ""


def lookup(agent_name: str, key: str) -> str | None:
    """Return the stored value for `key`, or None."""
    raw = read_cache(agent_name)
    for chunk in raw.split(_SEP):
        if not chunk.strip():
            continue
        head, _, body = chunk.partition("\n")
        if head.strip() == f"KEY: {key}":
            return body.strip()
    return None


def upsert(agent_name: str, key: str, value: str) -> None:
    raw = read_cache(agent_name)
    entries: dict[str, str] = {}
    order: list[str] = []
    for chunk in raw.split(_SEP):
        if not chunk.strip():
            continue
        head, _, body = chunk.partition("\n")
        k = head.strip().removeprefix("KEY:").strip()
        if k and k not in entries:
            order.append(k)
        entries[k] = body.strip()
    if key not in entries:
        order.append(key)
    entries[key] = value
    doc = _SEP.join(f"KEY: {k}\n{entries[k]}" for k in order)
    _cache_path(agent_name).write_text(doc + "\n")


def invalidate(agent_name: str, key: str) -> bool:
    """Drop a single cached entry. Returns True if the key existed."""
    raw = read_cache(agent_name)
    entries: dict[str, str] = {}
    order: list[str] = []
    found = False
    for chunk in raw.split(_SEP):
        if not chunk.strip():
            continue
        head, _, body = chunk.partition("\n")
        k = head.strip().removeprefix("KEY:").strip()
        if k == key:
            found = True
            continue
        if k and k not in entries:
            order.append(k)
        entries[k] = body.strip()
    if not found:
        return False
    doc = _SEP.join(f"KEY: {k}\n{entries[k]}" for k in order)
    _cache_path(agent_name).write_text((doc + "\n") if doc else "")
    return True
