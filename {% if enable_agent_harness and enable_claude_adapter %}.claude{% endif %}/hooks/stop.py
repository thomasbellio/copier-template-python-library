"""Claude Code Stop hook: run the harness gate before the agent finishes.

Stop fires after every response, so this is cheap when nothing changed: the changed set is
fingerprinted and compared with the last passing run. Otherwise the full gate runs.

- Blocking findings, or advisories, on the first stop: report on stderr and exit 2, so the
  agent fixes them or justifies the advisories.
- On the forced retry (stop_hook_active): never block again. Advisories are ignored, and if
  the gate still fails the human gets a systemMessage instead.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

INSTRUCTION = (
  "Fix the blocking findings in the definitions you changed. Do not refactor code you did "
  "not touch. For each advisory, either fix it or justify it in your final message. If a fix "
  "needs changes outside the code you touched, stop and explain instead."
)
_HEADER = re.compile(
  r"HARNESS (?:PASSED|FAILED): (?P<blocking>\d+) blocking, (?P<advisory>\d+) advisory"
)
STATE_FILE = Path(".harness") / "last-pass"


def project_root(payload: dict[str, object]) -> Path:
  """The project directory, from the environment or the hook payload."""
  root = os.environ.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or ".")
  return Path(root).resolve()


def current_fingerprint(root: Path) -> str | None:
  """Fingerprint of the changed set, or None when there are no changed Python files."""
  # The harness package lives in scripts/, which is only known once the root is.
  sys.path.insert(0, str(root / "scripts"))
  from harness.config import load_config
  from harness.scope import compute_changes, fingerprint, resolve_base

  config = load_config(root)
  base = resolve_base(config.default_branch)
  if not compute_changes(base, config.scope_dirs).files:
    return None
  return fingerprint(base)


def tell_human(message: str) -> int:
  """Show a message to the user without blocking the agent."""
  print(json.dumps({"systemMessage": message}))
  return 0


def run_gate(root: Path) -> tuple[int, str, int, int]:
  """Run scripts/check.sh; return exit code, report, blocking count and advisory count."""
  command = [str(root / "scripts" / "check.sh")]
  result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
  match = _HEADER.search(result.stdout)
  blocking = int(match["blocking"]) if match else 0
  advisory = int(match["advisory"]) if match else 0
  return result.returncode, result.stdout + result.stderr, blocking, advisory


def judge(root: Path, fingerprint: str, retry: bool) -> int:
  """Run the gate and decide: let the agent stop, block it once, or tell the human."""
  state = root / STATE_FILE
  if state.is_file() and state.read_text() == fingerprint:
    return 0
  code, report, blocking, advisory = run_gate(root)
  if code not in (0, 1):
    return tell_human(f"Agent harness error (exit {code}); the gate did not run.\n{report.strip()}")
  if code == 0 and (advisory == 0 or retry):
    state.parent.mkdir(exist_ok=True)
    state.write_text(fingerprint)
    return 0
  if retry:
    return tell_human(
      f"Agent harness still fails after one retry: {blocking} blocking finding(s). "
      "Run scripts/check.sh to see them."
    )
  print(f"{report.rstrip()}\n\n{INSTRUCTION}", file=sys.stderr)
  return 2


def main() -> int:
  """Read the hook payload and judge the changed set, if there is one."""
  try:
    payload = json.load(sys.stdin)
  except json.JSONDecodeError:
    return tell_human("Agent harness Stop hook: could not read the hook payload.")
  root = project_root(payload)
  os.chdir(root)
  try:
    fingerprint = current_fingerprint(root)
  except Exception as err:  # noqa: BLE001  # reason: hook boundary; a broken harness must not trap the agent
    return tell_human(f"Agent harness Stop hook could not inspect the changes: {err}")
  if fingerprint is None:
    return 0
  return judge(root, fingerprint, retry=bool(payload.get("stop_hook_active")))


if __name__ == "__main__":
  sys.exit(main())
