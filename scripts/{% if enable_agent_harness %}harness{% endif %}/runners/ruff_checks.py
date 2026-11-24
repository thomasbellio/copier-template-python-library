"""Ruff: complexity, size and shape, exception hygiene and docstring presence."""

import json

from harness.errors import HarnessError
from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.tools import find_tool, run_tool


def _command(ctx: Context) -> list[str]:
  """Build the ruff invocation for the harness rule set."""
  rules = ctx.config.strings("ruff", "rules")
  preview = ctx.config.strings("ruff", "preview_rules")
  cmd = [find_tool("ruff"), "check", "--no-fix", "--exit-zero", "--output-format", "json"]
  if preview:
    # Preview is switched on for this invocation only, and only for rules named
    # explicitly, so the project's own `ruff check .` keeps stable behaviour.
    cmd += ["--preview", "--config", "lint.explicit-preview-rules = true"]
  cmd += ["--extend-select", ",".join((*rules, *preview)), "--force-exclude", *ctx.paths]
  return cmd


def run(ctx: Context) -> Outcome:
  """Run ruff with the harness rules and keep only those rules' findings."""
  wanted = {*ctx.config.strings("ruff", "rules"), *ctx.config.strings("ruff", "preview_rules")}
  try:
    items = json.loads(run_tool(_command(ctx)) or "[]")
  except json.JSONDecodeError as err:
    raise HarnessError(f"could not parse ruff JSON output: {err}") from err
  findings: list[Finding] = []
  for item in items:
    code = item.get("code") or "syntax-error"
    if code != "syntax-error" and code not in wanted:
      continue
    findings.append(
      Finding(
        path=ctx.relative(item["filename"]),
        line=int(item["location"]["row"]),
        rule=code,
        message=str(item["message"]),
        tool="ruff",
      )
    )
  return Outcome(findings)


RUNNER = Runner(name="ruff", executables=("ruff",), fast=True, run=run)
