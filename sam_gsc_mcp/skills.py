"""Load the bundled SEO skills (playbooks) from skills/<name>/SKILL.md."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

_PKG = Path(__file__).resolve().parent


def skills_dir() -> Optional[Path]:
    """Installed wheel: sam_gsc_mcp/skills. Git clone: <repo>/skills."""
    for cand in (_PKG / "skills", _PKG.parent / "skills"):
        if cand.is_dir():
            return cand
    return None


def _frontmatter(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return meta
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line[:1] in (" ", "\t") and key:  # folded continuation
            meta[key] = (meta[key] + " " + line.strip()).strip()
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            meta[key] = val.strip().strip('"')
    return meta


def list_skills() -> list[dict[str, str]]:
    base = skills_dir()
    if not base:
        return []
    out = []
    for skill_md in sorted(base.glob("*/SKILL.md")):
        meta = _frontmatter(skill_md.read_text(encoding="utf-8"))
        out.append(
            {
                "id": skill_md.parent.name,
                "title": meta.get("title") or skill_md.parent.name.replace("-", " ").title(),
                "description": meta.get("description", ""),
                "uri": f"skill://{skill_md.parent.name}",
            }
        )
    return out


def read_skill(skill_id: str) -> Optional[dict[str, str]]:
    base = skills_dir()
    if not base:
        return None
    name = skill_id.strip().removeprefix("skill://").removesuffix("/SKILL.md").removesuffix(".md")
    name = name.replace("_", "-")
    path = (base / name / "SKILL.md").resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    meta = _frontmatter(text)
    return {
        "id": name,
        "title": meta.get("title") or name.replace("-", " ").title(),
        "description": meta.get("description", ""),
        "content": text,
    }
