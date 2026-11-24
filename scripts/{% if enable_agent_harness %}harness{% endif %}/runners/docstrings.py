"""pydoclint: docstrings that document arguments, returns or raises must match the signature."""

import re

from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.tools import find_tool, run_status, tool_failure

_VIOLATION = re.compile(r"^(?P<path>.+?\.py):(?P<line>\d+): (?P<code>DOC\d+): (?P<msg>.*)$")

FIX = "Make the docstring's Args/Returns/Raises match the signature, or cut it to a summary line."


def run(ctx: Context) -> Outcome:
  """Run pydoclint on changed source files, using [tool.pydoclint] in pyproject.toml."""
  paths = [p for p in ctx.paths if not p.startswith("tests/")]
  if not paths:
    return Outcome()
  cmd = [find_tool("pydoclint"), "--config=pyproject.toml", "--quiet"]
  cmd += ["--show-filenames-in-every-violation-message=True", *paths]
  code, stdout, stderr = run_status(cmd)
  findings: list[Finding] = []
  for raw in (stdout + stderr).splitlines():
    match = _VIOLATION.match(raw.strip())
    if match is None:
      continue
    findings.append(
      Finding(
        path=ctx.relative(match["path"]),
        line=int(match["line"]),
        rule=match["code"],
        message=match["msg"],
        tool="pydoclint",
        fix=FIX,
      )
    )
  # pydoclint prints violations on stderr; exit 1 with nothing parsed means the format moved.
  if code not in (0, 1) or (code == 1 and not findings):
    raise tool_failure(cmd, code, stderr or stdout)
  return Outcome(findings)


RUNNER = Runner(name="pydoclint", executables=("pydoclint",), fast=False, run=run)
