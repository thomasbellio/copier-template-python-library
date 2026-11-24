"""CI notice: flag a change that touches harness configuration or tool settings.

Run as `python -m harness.ci_notice` with scripts/ on PYTHONPATH. It never fails the job:
it appends a note to the GitHub job summary and emits a ::notice:: annotation for reviewers.
"""

import os
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path

from harness.config import load_config
from harness.errors import HarnessError
from harness.guarded import GUARDED_TOOL_TABLES, is_guarded
from harness.scope import Base, git, resolve_base, try_git

PYPROJECT = "pyproject.toml"


def changed_guarded_paths(base: Base) -> list[str]:
  """Guarded files that differ between the base and the working tree."""
  names = git("diff", "--name-only", "--no-renames", base.ref).splitlines()
  return sorted(name for name in names if is_guarded(name))


def tool_tables(text: str | None) -> Mapping[str, object]:
  """The [tool.*] tables of a pyproject.toml, or an empty mapping if it is missing or invalid."""
  if text is None:
    return {}
  try:
    tool = tomllib.loads(text).get("tool", {})
  except tomllib.TOMLDecodeError:
    return {}
  return tool if isinstance(tool, Mapping) else {}


def changed_tool_tables(base: Base) -> list[str]:
  """Guarded [tool.*] tables of pyproject.toml whose settings changed since the base."""
  before = tool_tables(try_git("show", f"{base.ref}:{PYPROJECT}"))
  path = Path(PYPROJECT)
  after = tool_tables(path.read_text(encoding="utf-8") if path.is_file() else None)
  return [f"[tool.{name}]" for name in GUARDED_TOOL_TABLES if before.get(name) != after.get(name)]


def render(paths: list[str], tables: list[str]) -> str:
  """Markdown for the job summary."""
  lines = [
    "### Agent harness configuration changed",
    "",
    "This change touches files or settings that control the quality gates. Check that no "
    "threshold was relaxed just to make the gate pass.",
    "",
  ]
  lines += [f"- `{p}`" for p in paths]
  lines += [f"- `{PYPROJECT}` {t}" for t in tables]
  return "\n".join(lines) + "\n"


def main() -> int:
  """Write the notice when guarded configuration changed; always exit 0."""
  try:
    config = load_config(Path.cwd())
    base = resolve_base(config.default_branch)
    paths, tables = changed_guarded_paths(base), changed_tool_tables(base)
  except HarnessError as err:
    print(f"::warning title=Harness notice skipped::{err}")
    return 0
  if not paths and not tables:
    print("No harness configuration changed.")
    return 0
  summary = render(paths, tables)
  summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
  if summary_file:
    with Path(summary_file).open("a", encoding="utf-8") as handle:
      handle.write(summary)
  changed = ", ".join([*paths, *(f"{PYPROJECT} {t}" for t in tables)])
  print(f"::notice title=Agent harness configuration changed::{changed}")
  print(summary)
  return 0


if __name__ == "__main__":
  sys.exit(main())
