"""import-linter: architecture contracts. Whole-project check; it must always pass."""

import re
from pathlib import Path

from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.scope import LEVEL_PROJECT
from harness.tools import find_tool, run_status, tool_failure

_IMPORT = re.compile(r"(?P<importer>[\w.]+) -> (?P<imported>[\w.]+) \(l\.(?P<line>\d+)")
_RULE = re.compile(r"^-{3,}$")

FIX = (
  "Remove the import or move the code so the dependency points the allowed way. "
  "Do not edit .importlinter to allow it."
)


def module_path(ctx: Context, module: str) -> str:
  """Find the file for a dotted module name under src/ or the repository root."""
  relative = Path(*module.split("."))
  for base in (ctx.root / "src", ctx.root):
    for candidate in (base / relative.with_suffix(".py"), base / relative / "__init__.py"):
      if candidate.is_file():
        return candidate.relative_to(ctx.root).as_posix()
  return ""


def parse(ctx: Context, output: str) -> list[Finding]:
  """Turn the 'Broken contracts' section into one finding per offending import."""
  lines = output.splitlines()
  findings: list[Finding] = []
  contract = ""
  for index, raw in enumerate(lines):
    text = raw.strip()
    if index + 1 < len(lines) and _RULE.match(lines[index + 1].strip()) and text:
      contract = text
      continue
    match = _IMPORT.search(text)
    if match is None or not contract or contract == "Broken contracts":
      continue
    findings.append(
      Finding(
        path=module_path(ctx, match["importer"]),
        line=int(match["line"]),
        rule="import-contract",
        message=f"{contract}: {match['importer']} -> {match['imported']}",
        tool="import-linter",
        level=LEVEL_PROJECT,
        fix=FIX,
      )
    )
  return findings


def run(ctx: Context) -> Outcome:
  """Check every contract in .importlinter."""
  cmd = [find_tool("lint-imports"), "--no-logo"]
  code, stdout, stderr = run_status(cmd)
  output = stdout + stderr
  if code == 0:
    return Outcome()
  findings = parse(ctx, output) if "Broken contracts" in output else []
  if code != 1 or not findings:
    raise tool_failure(cmd, code, output)
  return Outcome(findings)


RUNNER = Runner(name="import-linter", executables=("lint-imports",), fast=False, run=run)
