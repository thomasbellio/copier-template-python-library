"""Shared types for check runners.

A runner wraps one tool. It runs the tool on the changed files and returns findings;
the orchestrator applies the scope filter, so runners report everything the tool says.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from harness.config import Config
from harness.report import Finding
from harness.scope import ChangeSet


@dataclass(frozen=True)
class Context:
  """What a runner needs to know about the current run."""

  root: Path
  config: Config
  changes: ChangeSet
  file_mode: bool = False

  @property
  def paths(self) -> list[str]:
    """Changed Python files, repo-relative."""
    return self.changes.paths

  def relative(self, path: str) -> str:
    """Convert a tool-reported path to a repo-relative POSIX path."""
    candidate = Path(path)
    if candidate.is_absolute():
      try:
        candidate = candidate.relative_to(self.root)
      except ValueError:
        return candidate.as_posix()
    return candidate.as_posix().removeprefix("./")


@dataclass(frozen=True)
class Runner:
  """A named check: its executables, whether it is fast enough for --file mode, and run."""

  name: str
  executables: tuple[str, ...]
  fast: bool
  run: Callable[[Context], list[Finding]]
