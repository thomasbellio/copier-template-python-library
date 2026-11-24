"""Locate and run the external tools the harness drives."""

import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from harness.errors import HarnessError

INSTALL_HINT = "Install the dev dependencies with: uv run poetry install"


def find_tool(name: str) -> str:
  """Return the path of an executable, preferring the running virtualenv."""
  venv_candidate = Path(sys.executable).parent / name
  if venv_candidate.is_file():
    return str(venv_candidate)
  found = shutil.which(name)
  if found is None:
    raise HarnessError(f"required tool '{name}' was not found. {INSTALL_HINT}")
  return found


def tool_failure(cmd: Sequence[str], code: int, output: str) -> HarnessError:
  """Build the error for a tool that exited unexpectedly, with the tail of its output."""
  detail = output.strip().splitlines()[-5:]
  return HarnessError(f"{Path(cmd[0]).name} exited with {code}: " + " | ".join(detail))


def run_status(cmd: Sequence[str]) -> tuple[int, str, str]:
  """Run a tool and return its exit code, stdout and stderr, whatever the exit code."""
  result = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
  return result.returncode, result.stdout, result.stderr


def run_tool(cmd: Sequence[str], ok_codes: Sequence[int] = (0,)) -> str:
  """Run a tool and return stdout; any exit code outside ok_codes is a harness error."""
  result = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
  if result.returncode not in ok_codes:
    raise tool_failure(cmd, result.returncode, result.stderr or result.stdout)
  return result.stdout
