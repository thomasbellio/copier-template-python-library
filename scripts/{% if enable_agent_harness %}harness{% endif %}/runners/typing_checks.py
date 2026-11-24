"""mypy: type precision. Runs on the whole package, reports only touched definitions."""

import re

from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.tools import find_tool, run_status, tool_failure

_ERROR = re.compile(
  r"^(?P<path>[^:\n]+\.pyi?):(?P<line>\d+)(?::\d+)?: error: "
  r"(?P<msg>.*?)(?:  \[(?P<code>[a-z0-9-]+)\])?$"
)

FIX = "Give the code precise types. Do not add Any, casts or ignores to silence the error."


def run(ctx: Context) -> Outcome:
  """Type-check the package with project settings plus any flags from harness.toml."""
  package = ctx.config.package
  cmd = [find_tool("mypy"), f"src/{package}", *ctx.config.strings("mypy", "flags")]
  cmd += ["--show-error-codes", "--no-error-summary", "--no-pretty", "--no-color-output"]
  code, stdout, stderr = run_status(cmd)
  findings: list[Finding] = []
  for raw in stdout.splitlines():
    match = _ERROR.match(raw)
    if match is None:
      continue
    findings.append(
      Finding(
        path=ctx.relative(match["path"]),
        line=int(match["line"]),
        rule=f"mypy:{match['code'] or 'error'}",
        message=match["msg"],
        tool="mypy",
        fix=FIX,
      )
    )
  if code not in (0, 1) or (code == 1 and not findings):
    raise tool_failure(cmd, code, stderr or stdout)
  return Outcome(findings)


RUNNER = Runner(name="mypy", executables=("mypy",), fast=False, run=run)
