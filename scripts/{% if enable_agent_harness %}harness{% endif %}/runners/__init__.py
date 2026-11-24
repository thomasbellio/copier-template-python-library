"""Registry of check runners. Add a runner module and list its RUNNER here."""

from harness.runners import cognitive, ruff_checks
from harness.runners.base import Context, Runner

RUNNERS: tuple[Runner, ...] = (
  ruff_checks.RUNNER,
  cognitive.RUNNER,
)

__all__ = ["RUNNERS", "Context", "Runner"]
