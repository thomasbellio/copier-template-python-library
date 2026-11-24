"""Findings and how they are reported: plain text for agents and humans, JSON for tools."""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from harness.scope import LEVEL_DEF, ChangeSet

DEFAULT_FIX = "Fix the finding in the code you changed; do not suppress it."

FIX_HINTS: dict[str, str] = {
  "cognitive-complexity": (
    "Extract nested blocks into named helpers and use guard clauses to flatten nesting."
  ),
  "C901": "Too many paths through this function. Split it into helpers with clear names.",
  "PLR0904": "The class has too many public methods. Split responsibilities into smaller classes.",
  "PLR0911": "Too many returns. Consolidate exit points or extract the decision into a helper.",
  "PLR0912": "Too many branches. Replace if/elif chains with a lookup or extract helpers.",
  "PLR0913": "Too many arguments. Group related arguments into a dataclass or split the function.",
  "PLR0914": "Too many locals. Extract a helper that owns part of the computation.",
  "PLR0915": "Too many statements. Extract cohesive blocks into named helpers.",
  "PLR0916": "Boolean expression is too long. Name the parts as variables or a helper predicate.",
  "PLR0917": "Too many positional arguments. Make the trailing ones keyword-only (after *).",
  "PLR1702": "Blocks nest too deeply. Use guard clauses or extract the inner loop body.",
  "BLE001": "Catch the specific exception, or re-raise. A top-level boundary uses "
  "`# noqa: BLE001  # reason: <why>`.",
  "S110": "Catch the specific exception, or log and re-raise. Never swallow it.",
  "S112": "Catch the specific exception, or log why skipping is safe and narrow the handler.",
  "E722": "Name the exception type; a bare except also catches KeyboardInterrupt.",
  "B904": "Re-raise with `raise NewError(...) from err` to keep the cause.",
  "B012": "Move return/break/continue out of `finally`; it silently discards exceptions.",
  "TRY002": "Raise a specific exception class, or define one for this error.",
  "TRY203": "Remove the try/except: a handler that only re-raises adds nothing.",
  "TRY400": "Use logging.exception (or exc_info=True) inside a handler to keep the traceback.",
  "TRY401": "Drop the exception object from the message; logging.exception already records it.",
  "D100": "Add a module docstring saying what the module is for.",
  "D101": "Add a class docstring: its responsibility and constructor arguments.",
  "D102": "Add a docstring saying what the method does and what a caller must know.",
  "D103": "Add a docstring saying what the function does and what a caller must know.",
  "D104": "Add a docstring to the package's __init__.py.",
  "D106": "Add a docstring to the nested class.",
  "syntax-error": "Fix the syntax error before anything else.",
  "bare-type-ignore": "Fix the type error. If you must ignore it, name the code: "
  "`# type: ignore[code]  # reason: <why>`.",
  "bare-noqa": "Fix the finding. If you must suppress it, name the rule: "
  "`# noqa: CODE  # reason: <why>`.",
  "unjustified-suppression": "Add `# reason: <why>` on this line or the line above, "
  "or remove the suppression and fix the finding.",
  "changelog": "Add a line under [Unreleased], or explain in your final message why none is needed.",
}

ADVISORY_HEADER = "ADVISORY (review once, then fix or justify in your final message)"


@dataclass(frozen=True)
class Finding:
  """One problem reported by a check, located at a file and line."""

  path: str
  line: int
  rule: str
  message: str
  tool: str
  blocking: bool = True
  level: str = LEVEL_DEF
  fix: str = ""
  symbol: str = ""
  symbol_line: int = 0

  @property
  def hint(self) -> str:
    """The Fix line for this finding."""
    return self.fix or FIX_HINTS.get(self.rule, DEFAULT_FIX)


@dataclass(frozen=True)
class Summary:
  """Facts about the run shown in the report header."""

  changes: ChangeSet
  notes: tuple[str, ...] = ()


def counts(findings: Sequence[Finding]) -> tuple[int, int]:
  """Return (blocking, advisory) counts."""
  blocking = sum(1 for f in findings if f.blocking)
  return blocking, len(findings) - blocking


def _header(findings: Sequence[Finding], summary: Summary) -> str:
  """First report line: verdict, counts and what was compared."""
  blocking, advisory = counts(findings)
  changes = summary.changes
  if changes.whole_project:
    verdict, where = "HARNESS AUDIT", f"whole project, {len(changes.files)} files"
  else:
    verdict = "HARNESS FAILED" if blocking else "HARNESS PASSED"
    count = len(changes.files)
    where = f"base: {changes.base.label}, {count} file{'' if count == 1 else 's'} changed"
  return f"{verdict}: {blocking} blocking, {advisory} advisory ({where})"


def _group_heading(finding: Finding) -> str:
  """Heading for a group: the file and, when known, the enclosing definition."""
  if not finding.path:
    return "(whole project)"
  if finding.symbol:
    return f"{finding.path}:{finding.symbol_line}  {finding.symbol}"
  return finding.path


def _blocking_lines(findings: Sequence[Finding]) -> list[str]:
  """Render blocking findings grouped by file and definition."""
  lines: list[str] = []
  heading = None
  for finding in findings:
    current = _group_heading(finding)
    if current != heading:
      lines.extend(["", current])
      heading = current
    where = "" if finding.line == finding.symbol_line else f"line {finding.line}: "
    if not finding.path:
      where = ""
    lines.append(f"  [{finding.rule}] {where}{finding.message}")
    lines.append(f"  Fix: {finding.hint}")
  return lines


def _advisory_line(finding: Finding) -> str:
  """Render one advisory on a single line."""
  location = f"{finding.path}:{finding.line}" if finding.path else "(whole project)"
  symbol = f"  {finding.symbol}" if finding.symbol else ""
  return f"{location}{symbol}  [{finding.rule}] {finding.message}"


def render_text(findings: Sequence[Finding], summary: Summary, limit: int) -> str:
  """Plain-text report, capped at `limit` findings to protect agent context."""
  ordered = sorted(findings, key=lambda f: (not f.blocking, f.path, f.symbol_line, f.line))
  shown, omitted = ordered[:limit], len(ordered) - limit
  lines = [_header(findings, summary), *summary.notes]
  lines.extend(_blocking_lines([f for f in shown if f.blocking]))
  advisories = [f for f in shown if not f.blocking]
  if advisories:
    lines.extend(["", ADVISORY_HEADER, *(_advisory_line(f) for f in advisories)])
  if omitted > 0:
    lines.extend(["", f"... {omitted} more findings omitted. Run with --json for all of them."])
  return "\n".join(lines) + "\n"


def render_json(findings: Sequence[Finding], summary: Summary) -> str:
  """Every finding, uncapped, as JSON."""
  blocking, advisory = counts(findings)
  payload = {
    "passed": blocking == 0,
    "blocking": blocking,
    "advisory": advisory,
    "base": summary.changes.base.ref,
    "files": summary.changes.paths,
    "notes": list(summary.notes),
    "findings": [asdict(f) | {"fix": f.hint} for f in findings],
  }
  return json.dumps(payload, indent=2) + "\n"
