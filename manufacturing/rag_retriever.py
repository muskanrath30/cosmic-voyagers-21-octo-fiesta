"""
Local RAG over the maintenance manual.

The manual (knowledge/maintenance_manual.txt) is split on "## " headers. Each
section lists the reason codes it applies to in a "Codes:" line. Retrieval
ranks sections by how many of the record's reason codes they cover, returns the
best few, and always appends the "ALL" sections (general principles).

Public API (unchanged from the original):
    retrieve_knowledge(reason_codes) -> str

New:
    retrieve_sections(reason_codes) -> list[{"title", "codes", "text"}]
        used by the UI to show which manual sections grounded the answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow running this file directly
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import functools

from manufacturing import config

MAX_SECTIONS = 4
ALL = "ALL"


@functools.lru_cache(maxsize=1)
def _sections() -> tuple[dict, ...]:
    path = config.KNOWLEDGE_FILE
    if not path.exists():
        return ()

    text = path.read_text(encoding="utf-8")
    sections = []

    for block in text.split("\n## ")[1:] if "\n## " in text else []:
        lines = block.strip().splitlines()
        title = lines[0].strip()
        codes: set[str] = set()
        body_lines = []
        for line in lines[1:]:
            if line.lower().startswith("codes:"):
                codes = {c.strip() for c in line.split(":", 1)[1].split(",") if c.strip()}
            else:
                body_lines.append(line)
        sections.append({
            "title": title,
            "codes": codes,
            "text": f"{title}\n" + "\n".join(body_lines).strip(),
        })

    return tuple(sections)


def load_knowledge() -> str:
    """Return the whole manual (kept for backwards compatibility)."""
    return config.KNOWLEDGE_FILE.read_text(encoding="utf-8")


def retrieve_sections(reason_codes: list[str]) -> list[dict]:
    wanted = set(reason_codes)
    matched, general = [], []

    for section in _sections():
        if ALL in section["codes"]:
            general.append(section)
            continue
        overlap = len(wanted & section["codes"])
        if overlap:
            matched.append((overlap, section))

    matched.sort(key=lambda pair: -pair[0])
    chosen = [s for _, s in matched[:MAX_SECTIONS]]

    return [
        {"title": s["title"], "codes": sorted(s["codes"]), "text": s["text"]}
        for s in chosen + general
    ]


def retrieve_knowledge(reason_codes: list[str]) -> str:
    """Retrieved manual text for the supplied reason codes."""

    return "\n\n".join(s["text"] for s in retrieve_sections(reason_codes))


if __name__ == "__main__":

    codes = ["HIGH_TOOL_WEAR", "HIGH_TORQUE", "HIGH_MECHANICAL_LOAD"]

    print("=" * 80)
    print("LOCAL RAG RETRIEVAL TEST")
    print("=" * 80)
    for s in retrieve_sections(codes):
        print(f"- {s['title']}")
    print()
    print(retrieve_knowledge(codes))
