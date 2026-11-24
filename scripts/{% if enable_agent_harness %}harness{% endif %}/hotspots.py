"""Churn x complexity report: the files that change most often and are hardest to change.

Run through scripts/hotspots.sh. Report only: it never fails. Churn is the number of commits
touching each file under src/ in the window; complexity is the file's total cognitive
complexity from complexipy.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from harness.errors import HarnessError
from harness.scope import git
from harness.tools import find_tool, run_tool


@dataclass(frozen=True)
class Hotspot:
  """One file's churn, complexity and most complex functions."""

  path: str
  churn: int
  complexity: int
  functions: tuple[tuple[str, int], ...]

  @property
  def score(self) -> int:
    """Churn multiplied by complexity."""
    return self.churn * self.complexity


def churn(days: int, source_dir: str) -> Counter[str]:
  """Commits touching each existing Python file under source_dir in the last `days` days."""
  log = git("log", f"--since={days}.days", "--name-only", "--format=", "--", source_dir)
  return Counter(p for p in log.splitlines() if p.endswith(".py") and Path(p).is_file())


def complexity(source_dir: str) -> dict[str, list[tuple[str, int]]]:
  """Cognitive complexity of every function, grouped by file."""
  cmd = [find_tool("complexipy"), source_dir, "--output-format", "json", "--output", "-"]
  try:
    entries = json.loads(run_tool([*cmd, "--quiet"], ok_codes=(0, 1)) or "[]")
  except json.JSONDecodeError as err:
    raise HarnessError(f"could not parse complexipy JSON output: {err}") from err
  by_file: dict[str, list[tuple[str, int]]] = defaultdict(list)
  for entry in entries:
    by_file[str(entry["path"])].append((str(entry["function_name"]), int(entry["complexity"])))
  return by_file


def hotspots(days: int, top: int, source_dir: str = "src") -> list[Hotspot]:
  """Files ranked by churn x complexity, highest first."""
  commits = churn(days, source_dir)
  functions = complexity(source_dir)
  rows = [
    Hotspot(
      path=path,
      churn=commits[path],
      complexity=sum(c for _, c in functions.get(path, [])),
      functions=tuple(sorted(functions.get(path, []), key=lambda f: -f[1])[:3]),
    )
    for path in commits
  ]
  ranked = sorted((r for r in rows if r.score > 0), key=lambda r: (-r.score, r.path))
  return ranked[:top]


def render(rows: Sequence[Hotspot], days: int) -> str:
  """Markdown report."""
  lines = [
    "# Hotspots: churn x cognitive complexity",
    "",
    f"Commits in the last {days} days multiplied by total cognitive complexity per file.",
    "High scores mark code that changes often and is hard to change: refactor these first.",
    "",
  ]
  if not rows:
    return "\n".join([*lines, "No file under src/ both changed and has complexity above 0."]) + "\n"
  lines += ["| Rank | File | Commits | Complexity | Score | Most complex functions |"]
  lines += ["|---:|---|---:|---:|---:|---|"]
  for rank, row in enumerate(rows, start=1):
    named = ", ".join(f"`{name}` ({value})" for name, value in row.functions)
    lines.append(
      f"| {rank} | `{row.path}` | {row.churn} | {row.complexity} | {row.score} | {named} |"
    )
  return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
  """Write the hotspots report and print it."""
  parser = argparse.ArgumentParser(prog="hotspots.sh", description=__doc__)
  parser.add_argument("--days", type=int, default=90, help="churn window in days (default 90)")
  parser.add_argument("--top", type=int, default=10, help="number of files to list (default 10)")
  parser.add_argument("--output", default="reports/hotspots.md", help="where to write the report")
  args = parser.parse_args(argv)
  try:
    os.chdir(git("rev-parse", "--show-toplevel").strip())
    report = render(hotspots(args.days, args.top), args.days)
  except HarnessError as err:
    print(f"HOTSPOTS ERROR: {err}", file=sys.stderr)
    return 3
  output = Path(args.output)
  output.parent.mkdir(parents=True, exist_ok=True)
  output.write_text(report, encoding="utf-8")
  sys.stdout.write(report)
  return 0


if __name__ == "__main__":
  sys.exit(main())
