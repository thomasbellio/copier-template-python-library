"""Claude Code PreToolUse hook: ask the human before an agent edits harness configuration.

Stops an agent relaxing a gate to get a green result. pyproject.toml is not guarded, because
agents legitimately edit dependencies; CI flags changes to its tool sections instead.
"""

import json
import os
import sys
from pathlib import Path


def project_root(payload: dict[str, object]) -> Path:
  """The project directory, from the environment or the hook payload."""
  return Path(os.environ.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or ".")).resolve()


def guarded(root: Path, relative: str) -> bool:
  """Whether a path is harness configuration, per the shared list in scripts/harness."""
  # The harness package lives in scripts/, which is only known once the root is.
  sys.path.insert(0, str(root / "scripts"))
  try:
    from harness.guarded import is_guarded
  except ImportError:
    # Without the harness the list is unknown; asking is the safe answer.
    return True
  return is_guarded(relative)


def target(payload: dict[str, object], root: Path) -> str | None:
  """Repo-relative path the tool call would write, or None if outside the project."""
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
  root = project_root(payload)
  relative = target(payload, root)
  if relative is None or not guarded(root, relative):
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
