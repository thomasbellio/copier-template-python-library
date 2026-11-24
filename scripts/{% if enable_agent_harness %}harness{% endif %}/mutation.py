"""Mutation testing with cosmic-ray, limited to changed lines (`check.sh --mutation`).

cosmic-ray's git filter diffs a fixed branch against tracked files only, so the harness
points it at the resolved base and makes new files visible through a temporary git index
(intent-to-add entries; the real index is never touched). The survival rate is computed
from executed mutants only: cr-rate counts filtered mutants as completed, which dilutes it.
"""

import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from harness.config import Config
from harness.errors import HarnessError
from harness.scope import ChangeSet, git, untracked_files
from harness.tools import find_tool, run_status, tool_failure

CONFIG_FILE = "cosmic-ray.toml"
WORK_DIR = Path(".harness")
SESSION = WORK_DIR / "mutation.sqlite"
SESSION_CONFIG = WORK_DIR / "cosmic-ray.toml"
INDEX = WORK_DIR / "mutation.index"
_GIT_FILTER = re.compile(r"(?ms)^\[cosmic-ray\.filters\.git-filter\]\s*\n.*?(?=^\[|\Z)")
_JOB = re.compile(r"^(?P<path>\S+\.py) (?P<operator>\S+) (?P<occurrence>\d+)$")
_OUTCOME = re.compile(r"test outcome: TestOutcome\.(?P<outcome>[A-Z]+)")
_HUNK = re.compile(r"^@@ -(?P<line>\d+)")

FIX = "Add an assertion that fails for this mutant: test the behaviour the changed line controls."


@dataclass(frozen=True)
class Survivor:
  """A mutant the tests did not kill."""

  path: str
  line: int
  operator: str
  before: str
  after: str


@dataclass
class _Job:
  """One job block from `cr-report --show-diff` while it is being parsed."""

  path: str
  operator: str
  outcome: str = ""
  line: int = 0
  before: str = ""
  after: str = ""


def session_config(base_ref: str) -> Path:
  """Write a copy of cosmic-ray.toml whose git filter compares against the harness base."""
  text = Path(CONFIG_FILE).read_text(encoding="utf-8")
  section = f'[cosmic-ray.filters.git-filter]\nbranch = "{base_ref}"\n\n'
  text = _GIT_FILTER.sub(section, text) if _GIT_FILTER.search(text) else f"{text}\n{section}"
  WORK_DIR.mkdir(exist_ok=True)
  SESSION_CONFIG.write_text(text, encoding="utf-8")
  return SESSION_CONFIG


def filter_environment(scope_dirs: tuple[str, ...]) -> dict[str, str]:
  """Environment whose git index also lists untracked files, so the git filter sees them."""
  git_index = Path(git("rev-parse", "--git-path", "index").strip())
  if git_index.is_file():
    shutil.copyfile(git_index, INDEX)
  else:
    INDEX.unlink(missing_ok=True)
  env = {**os.environ, "GIT_INDEX_FILE": str(INDEX.resolve())}
  new_files = [p for p in untracked_files(scope_dirs) if p.endswith(".py")]
  if new_files:
    subprocess.run(["git", "add", "--intent-to-add", "--", *new_files], env=env, check=True)
  return env


def run_step(cmd: Sequence[str], env: dict[str, str] | None = None) -> str:
  """Run one cosmic-ray command; any non-zero exit is a harness error."""
  result = subprocess.run(list(cmd), capture_output=True, text=True, check=False, env=env)
  if result.returncode != 0:
    raise tool_failure(cmd, result.returncode, result.stderr or result.stdout)
  return result.stdout


def _apply_diff_line(job: _Job, raw: str, old_line: int) -> int:
  """Record the first removed and added lines of a mutation diff; return the next line number."""
  if raw.startswith("-") and not raw.startswith("---"):
    if not job.before:
      job.line, job.before = old_line, raw[1:].strip()
    return old_line + 1
  if raw.startswith("+") and not raw.startswith("+++"):
    job.after = job.after or raw[1:].strip()
    return old_line
  return old_line + 1


def parse_report(report: str) -> tuple[Counter[str], list[Survivor]]:
  """Count test outcomes and collect survivors from `cr-report --show-diff` output."""
  jobs: list[_Job] = []
  old_line = 0
  for raw in report.splitlines():
    if job_match := _JOB.match(raw.strip()):
      jobs.append(_Job(job_match["path"], job_match["operator"]))
      old_line = 0
    elif jobs and (outcome := _OUTCOME.search(raw)):
      jobs[-1].outcome = outcome["outcome"]
    elif jobs and (hunk := _HUNK.match(raw)):
      old_line = int(hunk["line"])
    elif jobs and old_line:
      old_line = _apply_diff_line(jobs[-1], raw, old_line)
  outcomes = Counter(job.outcome for job in jobs if job.outcome)
  survivors = [
    Survivor(j.path, j.line, j.operator, j.before, j.after) for j in jobs if j.outcome == "SURVIVED"
  ]
  return outcomes, survivors


def execute_session(base_ref: str, scope_dirs: tuple[str, ...]) -> str:
  """Create, filter and run the mutation session; return the full report."""
  tool = find_tool("cosmic-ray")
  config_path = str(session_config(base_ref))
  path_env = {
    **os.environ,
    "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
  }
  run_step([tool, "init", "--force", config_path, str(SESSION)], path_env)
  run_step([find_tool("cr-filter-pragma"), str(SESSION)], path_env)
  git_env = filter_environment(scope_dirs) | {"PATH": path_env["PATH"]}
  run_step([find_tool("cr-filter-git"), "--config", config_path, str(SESSION)], git_env)
  run_step([tool, "exec", config_path, str(SESSION)], path_env)
  code, stdout, stderr = run_status([find_tool("cr-report"), "--show-diff", str(SESSION)])
  if code != 0:
    raise tool_failure(["cr-report"], code, stderr or stdout)
  return stdout


def render(survivors: list[Survivor], outcomes: Counter[str], limit: float, base: str) -> str:
  """Plain-text mutation report."""
  executed = outcomes["KILLED"] + outcomes["SURVIVED"]
  rate = 100.0 * outcomes["SURVIVED"] / executed if executed else 0.0
  verdict = "MUTATION FAILED" if rate > limit else "MUTATION PASSED"
  lines = [
    f"{verdict}: {outcomes['SURVIVED']} of {executed} mutants survived ({rate:.0f}%, "
    f"limit {limit:.0f}%) (base: {base})"
  ]
  if outcomes["INCOMPETENT"]:
    lines.append(f"{outcomes['INCOMPETENT']} mutants broke the code and were not counted.")
  by_line: dict[tuple[str, int], list[Survivor]] = defaultdict(list)
  for survivor in survivors:
    by_line[(survivor.path, survivor.line)].append(survivor)
  for (path, line), group in by_line.items():
    lines += ["", f"{path}:{line}  `{group[0].before}` survives {len(group)} mutation(s):"]
    lines += [f"  [{s.operator}] -> `{s.after}`" for s in group]
    lines.append(f"  Fix: {FIX}")
  return "\n".join(lines) + "\n"


def run_mutation(config: Config, changes: ChangeSet) -> int:
  """Run mutation testing on changed source lines; return the harness exit code."""
  if not Path(CONFIG_FILE).is_file():
    raise HarnessError(f"{CONFIG_FILE} not found")
  if not any(p.startswith("src/") for p in changes.paths):
    print(f"MUTATION PASSED: no changed source files (base: {changes.base.label})")
    return 0
  report = execute_session(changes.base.ref, config.scope_dirs)
  outcomes, survivors = parse_report(report)
  executed = outcomes["KILLED"] + outcomes["SURVIVED"]
  if outcomes["SURVIVED"] and not survivors:
    raise HarnessError("cr-report listed surviving mutants that could not be parsed")
  limit = config.number("mutation", "max_survival_percent", 20.0)
  sys.stdout.write(render(survivors[: config.max_findings], outcomes, limit, changes.base.label))
  if executed and 100.0 * outcomes["SURVIVED"] / executed > limit:
    return 1
  return 0
