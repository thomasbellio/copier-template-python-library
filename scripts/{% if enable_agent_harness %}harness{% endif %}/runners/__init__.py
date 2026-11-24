"""Registry of check runners. Add a runner module and list its RUNNER here."""

from harness.runners import (
  changelog,
  cognitive,
  deadcode,
  docstrings,
  imports,
  ruff_checks,
  structure,
  suppressions,
  typing_checks,
)
from harness.runners.base import Context, Outcome, Runner

RUNNERS: tuple[Runner, ...] = (
  ruff_checks.RUNNER,
  cognitive.RUNNER,
  suppressions.RUNNER,
  typing_checks.RUNNER,
  docstrings.RUNNER,
  deadcode.RUNNER,
  imports.RUNNER,
  structure.RUNNER,
  changelog.RUNNER,
)

__all__ = ["RUNNERS", "Context", "Outcome", "Runner"]
