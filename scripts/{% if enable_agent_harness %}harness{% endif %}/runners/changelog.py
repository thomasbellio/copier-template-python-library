"""Changelog reminder: advise when src/ changed but [Unreleased] gained no entry."""

from pathlib import Path

from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.scope import LEVEL_PROJECT, git, parse_diff, untracked_files

CHANGELOG = "CHANGELOG.md"
HEADING = "## [Unreleased]"
MESSAGE = (
  "src/ changed but CHANGELOG.md has no new entry under [Unreleased]. Add one if a user of "
  "the package would notice this change; otherwise say in your final message that the "
  "change is internal."
)


def unreleased_lines(lines: list[str]) -> range | None:
  """1-based line numbers of the body of the [Unreleased] section."""
  starts = [i for i, text in enumerate(lines, start=1) if text.strip().lower() == HEADING.lower()]
  if not starts:
    return None
  start = starts[0]
  following = [i for i, text in enumerate(lines, start=1) if i > start and text.startswith("## ")]
  end = following[0] if following else len(lines) + 1
  return range(start + 1, end)


def added_lines(ctx: Context, lines: list[str]) -> set[int]:
  """Lines of CHANGELOG.md added or modified since the base."""
  if CHANGELOG in untracked_files((CHANGELOG,)):
    return set(range(1, len(lines) + 1))
  diff = git("diff", "-U0", "--no-color", "--no-ext-diff", ctx.changes.base.ref, "--", CHANGELOG)
  changed, _ = parse_diff(diff).get(CHANGELOG, (set(), False))
  return changed


def run(ctx: Context) -> Outcome:
  """Check that a change to src/ comes with an [Unreleased] entry."""
  path = ctx.root / CHANGELOG
  if ctx.changes.whole_project or not path.is_file():
    return Outcome()
  if not any(p.startswith("src/") for p in ctx.paths):
    return Outcome()
  lines = Path(path).read_text(encoding="utf-8").splitlines()
  section = unreleased_lines(lines)
  if section is None:
    return Outcome()
  added = [n for n in added_lines(ctx, lines) if n in section and lines[n - 1].strip()]
  if added:
    return Outcome()
  finding = Finding(
    path=CHANGELOG,
    line=section.start - 1,
    rule="changelog",
    message=MESSAGE,
    tool="harness",
    blocking=False,
    level=LEVEL_PROJECT,
  )
  return Outcome([finding])


RUNNER = Runner(name="changelog", executables=(), fast=False, run=run)
