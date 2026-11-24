"""complexipy: cognitive complexity per function."""

import json
import tomllib
from collections.abc import Mapping

from harness.errors import HarnessError
from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.tools import find_tool, run_tool

CONFIG_FILE = "complexipy.toml"
DEFAULT_MAX = 15


def max_complexity(ctx: Context) -> int:
  """Read the threshold from complexipy.toml so the tool and harness agree."""
  try:
    with (ctx.root / CONFIG_FILE).open("rb") as handle:
      value = tomllib.load(handle).get("max-complexity-allowed", DEFAULT_MAX)
  except FileNotFoundError:
    return DEFAULT_MAX
  if not isinstance(value, int):
    raise HarnessError(f"{CONFIG_FILE}: max-complexity-allowed must be an integer")
  return value


def _hint(entry: Mapping[str, object]) -> str:
  """Turn complexipy's first refactor suggestion into a Fix line, if it has one."""
  plans = entry.get("refactor_plans")
  if not isinstance(plans, list) or not plans or not isinstance(plans[0], dict):
    return ""
  plan = plans[0]
  return f"{plan.get('title', '')} (lines {plan.get('line_start')}-{plan.get('line_end')}). " + (
    "Then extract remaining nested blocks into named helpers."
  )


def run(ctx: Context) -> Outcome:
  """Report functions whose cognitive complexity is over the threshold."""
  limit = max_complexity(ctx)
  cmd = [find_tool("complexipy"), *ctx.paths, "--output-format", "json", "--output", "-"]
  cmd += ["--quiet", "--suggest-refactors", "--force-exclude"]
  try:
    entries = json.loads(run_tool(cmd, ok_codes=(0, 1)) or "[]")
  except json.JSONDecodeError as err:
    raise HarnessError(f"could not parse complexipy JSON output: {err}") from err
  findings: list[Finding] = []
  for entry in entries:
    complexity = int(entry["complexity"])
    if complexity <= limit:
      continue
    findings.append(
      Finding(
        path=ctx.relative(str(entry["path"])),
        line=int(entry["line_start"]),
        rule="cognitive-complexity",
        message=f"{complexity} > {limit}",
        tool="complexipy",
        fix=_hint(entry),
      )
    )
  return Outcome(findings)


RUNNER = Runner(name="complexipy", executables=("complexipy",), fast=True, run=run)
