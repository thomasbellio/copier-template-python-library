"""Claude Code PreToolUse hook: ask the human before an agent edits harness configuration.

Stops an agent relaxing a gate to get a green result. pyproject.toml is not guarded, because
agents legitimately edit dependencies; CI flags changes to its tool sections instead.
"""

import json
import os
import sys
from fnmatch import fnmatch
from pathlib import Path

GUARDED = (
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


def guarded(relative: str) -> bool:
  """Whether a repo-relative path is harness configuration."""
  return any(fnmatch(relative, pattern) for pattern in GUARDED)


def target(payload: dict[str, object]) -> str | None:
  """Repo-relative path the tool call would write, or None if outside the project."""
  root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or ".")).resolve()
  tool_input = payload.get("tool_input")
  raw = tool_input.get("file_path") if isinstance(tool_input, dict) else None
  if not isinstance(raw, str):
    return None
  path = Path(raw) if Path(raw).is_absolute() else root / raw
  try:
    return path.resolve().relative_to(root).as_posix()
  except ValueError:
    return None


def main() -> int:
  """Print an "ask" decision for guarded paths; stay silent otherwise."""
  try:
    payload = json.load(sys.stdin)
  except json.JSONDecodeError:
    return 0
  relative = target(payload)
  if relative is None or not guarded(relative):
    return 0
  reason = (
    f"{relative} is agent-harness configuration. Agents must not relax a gate to pass it; "
    "approve only if you asked for this change."
  )
  decision = {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": reason,
  }
  print(json.dumps({"hookSpecificOutput": decision}))
  return 0


if __name__ == "__main__":
  sys.exit(main())
