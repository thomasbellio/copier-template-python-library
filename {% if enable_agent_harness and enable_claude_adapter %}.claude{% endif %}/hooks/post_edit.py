"""Claude Code PostToolUse hook: fast harness checks on the Python file just edited.

Exit 0 with no output on a pass. On a gate failure, print the findings to stderr and exit 2
so Claude sees them (the edit has already happened). On a harness error, exit 1: Claude Code
shows the message to the user and the agent carries on, so a broken harness never traps it.
"""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

DEFAULT_SCOPE_DIRS = ("src", "tests")


def project_root(payload: dict[str, object]) -> Path:
  """The project directory, from the environment or the hook payload."""
  root = os.environ.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or ".")
  return Path(root).resolve()


def scope_dirs(root: Path) -> tuple[str, ...]:
  """Directories the harness checks, from harness.toml."""
  try:
    with (root / "harness.toml").open("rb") as handle:
      dirs = tomllib.load(handle).get("harness", {}).get("scope_dirs")
  except (OSError, tomllib.TOMLDecodeError):
    return DEFAULT_SCOPE_DIRS
  return tuple(str(d).rstrip("/") for d in dirs) if isinstance(dirs, list) else DEFAULT_SCOPE_DIRS


def target_file(payload: dict[str, object], root: Path) -> str | None:
  """Repo-relative path of the edited file, if it is a Python file the harness checks."""
  tool_input = payload.get("tool_input")
  raw = tool_input.get("file_path") if isinstance(tool_input, dict) else None
  if not isinstance(raw, str) or not raw.endswith(".py"):
    return None
  path = Path(raw) if Path(raw).is_absolute() else root / raw
  try:
    relative = path.resolve().relative_to(root)
  except ValueError:
    return None
  return relative.as_posix() if relative.parts[0] in scope_dirs(root) else None


def main() -> int:
  """Run `scripts/check.sh --file` and translate its exit code for Claude Code."""
  try:
    payload = json.load(sys.stdin)
  except json.JSONDecodeError:
    print("post_edit hook: could not read the hook payload", file=sys.stderr)
    return 1
  root = project_root(payload)
  relative = target_file(payload, root)
  if relative is None:
    return 0
  command = [str(root / "scripts" / "check.sh"), "--file", relative]
  result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
  if result.returncode == 0:
    return 0
  if result.returncode == 1:
    print(result.stdout, file=sys.stderr)
    return 2
  detail = (result.stderr or result.stdout).strip()
  print(
    f"Agent harness could not check {relative} (exit {result.returncode}): {detail}",
    file=sys.stderr,
  )
  return 1


if __name__ == "__main__":
  sys.exit(main())
