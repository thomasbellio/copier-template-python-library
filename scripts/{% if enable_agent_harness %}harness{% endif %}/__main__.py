"""Entry point: run the harness checks on changed code and report.

Exit codes: 0 passed, 1 gate failed, 3 the harness or a tool could not run.
"""

import argparse
import os
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from harness.config import Config, load_config
from harness.errors import HarnessError
from harness.report import Finding, Summary, counts, render_json, render_text
from harness.runners import RUNNERS, Context, Runner
from harness.scope import ChangeSet, compute_changes, git, resolve_base, whole_project
from harness.tools import find_tool

EXIT_PASS, EXIT_FAIL, EXIT_ERROR = 0, 1, 3


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
  """Parse command-line options."""
  parser = argparse.ArgumentParser(prog="check.sh", description=__doc__)
  mode = parser.add_mutually_exclusive_group()
  mode.add_argument("--file", help="fast checks for one file (used by post-edit hooks)")
  mode.add_argument("--all", action="store_true", help="audit the whole codebase; always exits 0")
  parser.add_argument("--json", action="store_true", help="emit findings as JSON")
  parser.add_argument("--timings", action="store_true", help="print per-tool timings to stderr")
  return parser.parse_args(argv)


def build_changes(config: Config, args: argparse.Namespace) -> ChangeSet:
  """Compute the changed set for the requested mode."""
  base = resolve_base(config.default_branch)
  if args.all:
    return whole_project(base, config.scope_dirs)
  changes = compute_changes(base, config.scope_dirs)
  if args.file:
    target = Path(args.file).resolve()
    root = Path.cwd().resolve()
    relative = target.relative_to(root).as_posix() if target.is_relative_to(root) else args.file
    return changes.restricted_to(relative)
  return changes


def _timed(runner: Runner, ctx: Context) -> tuple[list[Finding], float]:
  """Run one runner and measure its wall-clock time."""
  started = time.monotonic()
  findings = runner.run(ctx)
  return findings, time.monotonic() - started


def execute(runners: Sequence[Runner], ctx: Context) -> tuple[list[Finding], dict[str, float]]:
  """Run every runner in parallel; collect findings, timings and errors from all of them."""
  for runner in runners:
    for executable in runner.executables:
      find_tool(executable)
  findings: list[Finding] = []
  timings: dict[str, float] = {}
  errors: list[str] = []
  with ThreadPoolExecutor(max_workers=max(1, len(runners))) as pool:
    futures = {runner.name: pool.submit(_timed, runner, ctx) for runner in runners}
    for name, future in futures.items():
      try:
        result, elapsed = future.result()
      except HarnessError as err:
        errors.append(f"{name}: {err}")
        continue
      findings.extend(result)
      timings[name] = elapsed
  if errors:
    raise HarnessError("\n".join(errors))
  return findings, timings


def in_scope(findings: Sequence[Finding], changes: ChangeSet) -> list[Finding]:
  """Keep findings in touched code and label each with its enclosing definition."""
  kept: list[Finding] = []
  for finding in findings:
    if finding.path and not changes.in_scope(finding.path, finding.line, finding.level):
      continue
    span = changes.symbol(finding.path, finding.line) if finding.path else None
    if span is not None:
      label = f"class {span.name}" if span.kind == "class" else f"{span.name}()"
      finding = replace(finding, symbol=label, symbol_line=span.def_line)
    kept.append(finding)
  return kept


def run(args: argparse.Namespace) -> int:
  """Run the harness and return the exit code."""
  root = Path(git("rev-parse", "--show-toplevel").strip())
  os.chdir(root)
  config = load_config(root)
  changes = build_changes(config, args)
  if not changes.files:
    print(f"HARNESS PASSED: no changed files (base: {changes.base.label})")
    return EXIT_PASS
  runners = [r for r in RUNNERS if r.fast or not args.file]
  ctx = Context(root=root, config=config, changes=changes, file_mode=bool(args.file))
  raw, timings = execute(runners, ctx)
  findings = in_scope(raw, changes)
  summary = Summary(changes=changes)
  if args.json:
    sys.stdout.write(render_json(findings, summary))
  else:
    sys.stdout.write(render_text(findings, summary, config.max_findings))
  if args.timings:
    for name, elapsed in sorted(timings.items(), key=lambda item: -item[1]):
      print(f"timing {name}: {elapsed:.2f}s", file=sys.stderr)
  blocking, _ = counts(findings)
  return EXIT_FAIL if blocking and not args.all else EXIT_PASS


def main(argv: Sequence[str] | None = None) -> int:
  """Command-line entry point."""
  args = parse_args(argv)
  try:
    return run(args)
  except HarnessError as err:
    print(f"HARNESS ERROR: {err}", file=sys.stderr)
    return EXIT_ERROR


if __name__ == "__main__":
  sys.exit(main())
