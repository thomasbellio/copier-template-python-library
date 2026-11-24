"""Error type for failures of the harness itself, as opposed to gate failures."""


class HarnessError(Exception):
  """The harness or one of its tools could not run; maps to exit code 3."""
