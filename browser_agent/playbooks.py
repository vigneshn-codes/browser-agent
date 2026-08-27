"""Skill & command playbook loader.

Two mechanisms, both driven by the Markdown files under `skills/` (packaged)
and `commands/` (repo root):

* **Commands** — an explicit `/name arg1 arg2` task is expanded into the command
  file's "Expansion" template, with positional args filling `{placeholders}`.
* **Skills** — a free-form task is matched against each skill's "When to use"
  section; the best-scoring skill's playbook is injected into the system prompt
  so the model follows the right procedure without the user naming it.

Skill/command bodies are trusted project content (unlike web page text), so they
are injected as guidance, not screened as untrusted data.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _PKG_DIR / "skills"

# Words too generic to help match a task to a skill.
_STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "or", "for", "in", "on", "with", "your",
    "you", "this", "that", "is", "are", "it", "by", "use", "using", "when", "user",
    "asks", "want", "wants", "please", "into", "from", "out", "web", "site", "page",
    "browser", "agent", "task", "excluding", "which", "requires",
}


def _commands_dirs() -> list[Path]:
    """Candidate locations for command files, most specific first."""
    dirs: list[Path] = []
    env = os.getenv("BROWSER_AGENT_COMMANDS_DIR")
    if env:
        dirs.append(Path(env))
    dirs.append(_PKG_DIR.parent / "commands")  # repo root, running from source
    dirs.append(Path.cwd() / "commands")
    seen: set[Path] = set()
    out: list[Path] = []
    for d in dirs:
        rd = d.resolve()
        if rd not in seen and d.is_dir():
            seen.add(rd)
            out.append(d)
    return out


def _tokens(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z]+", text.lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


def _section(md: str, title: str) -> str:
    """Return the body under the first heading whose text contains `title`.

    Stops at the next Markdown heading of any level.
    """
    out: list[str] = []
    capturing = False
    for line in md.splitlines():
        if line.lstrip().startswith("#"):
            if capturing:
                break
            heading = line.lstrip("#").strip().lower()
            if title.lower() in heading:
                capturing = True
            continue
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


@dataclass
class Skill:
    name: str
    body: str
    keywords: set[str] = field(default_factory=set)


@dataclass
class Command:
    name: str
    template: str
    param_names: list[str]


@lru_cache(maxsize=1)
def load_skills() -> tuple[Skill, ...]:
    if not _SKILLS_DIR.is_dir():
        return ()
    skills: list[Skill] = []
    for f in sorted(_SKILLS_DIR.glob("*.md")):
        body = f.read_text(encoding="utf-8")
        when = _section(body, "When to use")
        desc = _section(body, "Description")
        keywords = _tokens(f.stem.replace("_", " ") + " " + when + " " + desc)
        skills.append(Skill(name=f.stem, body=body, keywords=keywords))
    return tuple(skills)


@lru_cache(maxsize=1)
def load_commands() -> dict[str, Command]:
    commands: dict[str, Command] = {}
    for d in _commands_dirs():
        for f in sorted(d.glob("*.md")):
            if f.stem in commands:
                continue
            body = f.read_text(encoding="utf-8")
            template = _section(body, "Expansion") or _section(body, "Behavior")
            # Ordered, de-duplicated placeholder names, e.g. {url} -> ["url"].
            seen: set[str] = set()
            params: list[str] = []
            for m in re.findall(r"\{(\w+)\}", template):
                if m not in seen:
                    seen.add(m)
                    params.append(m)
            commands[f.stem] = Command(
                name=f.stem, template=template, param_names=params
            )
    return commands


def expand_command(task: str) -> tuple[str, str | None]:
    """If `task` is `/name args...`, return (expanded_task, name); else unchanged.

    Positional args fill the template's placeholders in order. Any leftover args
    are appended so nothing the user typed is silently dropped.
    """
    stripped = task.strip()
    if not stripped.startswith("/"):
        return task, None
    parts = stripped.split()
    name = parts[0][1:]
    cmd = load_commands().get(name)
    if not cmd or not cmd.template:
        return task, None
    args = parts[1:]
    filled = cmd.template
    for pname, val in zip(cmd.param_names, args):
        filled = filled.replace("{" + pname + "}", val)
    leftover = args[len(cmd.param_names):]
    if leftover:
        filled = filled + "\n\nAdditional arguments: " + " ".join(leftover)
    return filled.strip(), name


def select_skill(task: str, min_score: int = 2) -> Skill | None:
    """Best-matching skill for `task`, or None if nothing scores high enough."""
    toks = _tokens(task)
    best: Skill | None = None
    best_score = 0
    for s in load_skills():
        score = len(toks & s.keywords)
        if score > best_score:
            best, best_score = s, score
    return best if best_score >= min_score else None
