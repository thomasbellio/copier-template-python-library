"""Harness configuration that agents must not change to get a passing result.

Shared by the Claude Code PreToolUse guard and the CI notice, so both protect the same files.
"""

from fnmatch import fnmatch

GUARDED_PATHS = (
  "harness.toml",
  "complexipy.toml",
  ".pyscn.toml",
  ".importlinter",
  "cosmic-ray.toml",
  "vulture_whitelist.py",
  "lefthook.yml",
  "scripts/check.sh",
  "scripts/harness/*",
  ".claude/*",
)

# pyproject.toml is not guarded as a file, because agents legitimately edit dependencies.
# CI reports changes to these tool tables instead.
GUARDED_TOOL_TABLES = ("ruff", "mypy", "pydoclint")


def is_guarded(path: str) -> bool:
  """Whether a repo-relative POSIX path is harness configuration."""
  return any(fnmatch(path, pattern) for pattern in GUARDED_PATHS)
