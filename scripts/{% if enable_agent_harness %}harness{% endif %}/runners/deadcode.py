"""vulture: dead code.

A library's public API looks unused from inside the package, so confidence is graded:
high-confidence findings and abandoned private helpers block; unused public names advise.
"""

import re
from pathlib import Path

from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.tools import find_tool, run_status, tool_failure

_FINDING = re.compile(r"^(?P<path>.+?):(?P<line>\d+): (?P<msg>.*) \((?P<conf>\d+)% confidence")
_NAME = re.compile(r"'([^']+)'")
WHITELIST = "vulture_whitelist.py"

FIX_BLOCK = "Delete it. If it is used dynamically, add it to vulture_whitelist.py with a comment."
FIX_PUBLIC = "If this is public API, cover it with a test; otherwise delete it."


def _is_private(name: str) -> bool:
  """Underscore names, excluding dunders such as __version__."""
  return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _finding(ctx: Context, path: str, line: int, message: str, confidence: int) -> Finding:
  """Grade one vulture result as blocking or advisory."""
  name_match = _NAME.search(message)
  name = name_match.group(1) if name_match else ""
  block_at = ctx.config.integer("vulture", "block_confidence", 80)
  blocking = confidence >= block_at or _is_private(name)
  return Finding(
    path=ctx.relative(path),
    line=line,
    rule="dead-code",
    message=f"{message} ({confidence}% confidence)",
    tool="vulture",
    blocking=blocking,
    fix=FIX_BLOCK if blocking else FIX_PUBLIC,
  )


def run(ctx: Context) -> Outcome:
  """Run vulture over sources, tests and the whitelist, so tested API counts as used."""
  min_confidence = ctx.config.integer("vulture", "min_confidence", 60)
  targets = [d for d in ctx.config.scope_dirs if (ctx.root / d).is_dir()]
  if Path(ctx.root / WHITELIST).is_file():
    targets.append(WHITELIST)
  cmd = [find_tool("vulture"), *targets, "--min-confidence", str(min_confidence)]
  code, stdout, stderr = run_status(cmd)
  findings: list[Finding] = []
  for raw in stdout.splitlines():
    match = _FINDING.match(raw)
    if match is not None:
      line, confidence = int(match["line"]), int(match["conf"])
      findings.append(_finding(ctx, match["path"], line, match["msg"], confidence))
  # vulture exits 3 when it found dead code; anything else non-zero is an error.
  if code not in (0, 3) or (code == 3 and not findings):
    raise tool_failure(cmd, code, stderr or stdout)
  return Outcome(findings)


RUNNER = Runner(name="vulture", executables=("vulture",), fast=False, run=run)
