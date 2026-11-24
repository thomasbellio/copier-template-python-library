"""Suppression policy: every suppression added in the diff needs a code and a reason.

Blocks on added lines only: a bare `# type: ignore` or `# noqa`, and any suppression
without `# reason: <text>` on the same line or the line above.
"""

import io
import re
import tokenize
from pathlib import Path

from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.scope import LEVEL_LINE, FileChange

_SUPPRESSION = re.compile(
  r"#\s*(type:\s*ignore|noqa|pragma:\s*no\s+(cover|mutate)|complexipy:\s*ignore)", re.IGNORECASE
)
_BARE_TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore(?!\[)", re.IGNORECASE)
_BARE_NOQA = re.compile(r"#\s*noqa(?!\s*:)", re.IGNORECASE)
_REASON = re.compile(r"#\s*reason:\s*\S", re.IGNORECASE)


def comments_by_line(source: str) -> dict[int, str]:
  """Map line numbers to the comment text on that line, ignoring strings."""
  comments: dict[int, str] = {}
  try:
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
      if token.type == tokenize.COMMENT:
        comments[token.start[0]] = token.string
  except (tokenize.TokenError, SyntaxError):
    return {}
  return comments


def classify(comment: str, previous: str) -> str | None:
  """Return the rule a suppression comment breaks, or None if it is acceptable."""
  if _BARE_TYPE_IGNORE.search(comment):
    return "bare-type-ignore"
  if _BARE_NOQA.search(comment):
    return "bare-noqa"
  if not (_REASON.search(comment) or _REASON.search(previous)):
    return "unjustified-suppression"
  return None


def _check_file(change: FileChange) -> tuple[list[Finding], int]:
  """Return findings and the number of suppressions added in one file."""
  comments = comments_by_line(Path(change.path).read_text(encoding="utf-8"))
  findings: list[Finding] = []
  added = 0
  for line, comment in sorted(comments.items()):
    if not (change.is_new or line in change.lines) or not _SUPPRESSION.search(comment):
      continue
    added += 1
    rule = classify(comment, comments.get(line - 1, ""))
    if rule is not None:
      findings.append(
        Finding(change.path, line, rule, comment.strip(), "harness", level=LEVEL_LINE)
      )
  return findings, added


def run(ctx: Context) -> Outcome:
  """Check suppression comments on every added line of the changed files."""
  outcome = Outcome()
  total = 0
  for change in ctx.changes.files.values():
    findings, added = _check_file(change)
    outcome.findings.extend(findings)
    total += added
  if total and not ctx.changes.whole_project:
    unjustified = len(outcome.findings)
    status = "all justified" if not unjustified else f"{unjustified} not acceptable"
    outcome.notes.append(f"Suppressions added in this diff: {total} ({status})")
  return outcome


RUNNER = Runner(name="suppressions", executables=(), fast=True, run=run)
