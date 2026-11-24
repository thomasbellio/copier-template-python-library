"""Decide which code counts as changed, and therefore which findings are in scope.

A finding is in scope when it sits on an added or modified line, or anywhere inside a
function or class whose line span contains such a line. New files are entirely in scope.
"""

import ast
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from harness.errors import HarnessError

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

LEVEL_LINE = "line"
LEVEL_DEF = "def"
LEVEL_CLASS = "class"
LEVEL_PROJECT = "project"


def git(*args: str) -> str:
  """Run a git command and return stdout, raising HarnessError on failure."""
  result = subprocess.run(
    ["git", "-c", "core.quotePath=false", *args], capture_output=True, text=True, check=False
  )
  if result.returncode != 0:
    raise HarnessError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
  return result.stdout


def try_git(*args: str) -> str | None:
  """Run a git command, returning stripped stdout, or None when it fails."""
  try:
    return git(*args).strip()
  except HarnessError:
    return None


@dataclass(frozen=True)
class Base:
  """The commit or tree that changes are measured against."""

  ref: str
  reason: str

  @property
  def label(self) -> str:
    """Short form of the base for report headers."""
    if self.ref == EMPTY_TREE:
      return "empty tree"
    return self.ref[:7]


def resolve_base(default_branch: str) -> Base:
  """Resolve the diff base: HARNESS_BASE, merge-base with the default branch, or HEAD."""
  override = os.environ.get("HARNESS_BASE", "").strip()
  if override:
    if override == EMPTY_TREE:
      return Base(EMPTY_TREE, "HARNESS_BASE")
    sha = try_git("rev-parse", "--verify", "--quiet", f"{override}^{{commit}}")
    if not sha:
      raise HarnessError(f"HARNESS_BASE={override} is not a commit in this repository")
    return Base(sha, "HARNESS_BASE")
  if try_git("rev-parse", "--verify", "--quiet", "HEAD") is None:
    return Base(EMPTY_TREE, "no commits yet")
  for candidate in (f"origin/{default_branch}", default_branch):
    sha = try_git("merge-base", "HEAD", candidate)
    if sha:
      return Base(sha, f"merge-base with {candidate}")
  return Base(git("rev-parse", "HEAD").strip(), "HEAD (no merge-base found)")


@dataclass(frozen=True)
class Span:
  """Line span of a function or class definition, decorators included."""

  kind: str
  name: str
  start: int
  end: int
  def_line: int

  def contains(self, line: int) -> bool:
    """Whether a line number falls inside this definition."""
    return self.start <= line <= self.end


def definition_spans(source: str) -> tuple[Span, ...]:
  """Collect the spans of every function and class in a module."""
  try:
    tree = ast.parse(source)
  except SyntaxError:
    return ()
  spans: list[Span] = []
  for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
      kind = LEVEL_CLASS if isinstance(node, ast.ClassDef) else "function"
      start = min([node.lineno, *(dec.lineno for dec in node.decorator_list)])
      end = node.end_lineno or node.lineno
      spans.append(Span(kind, node.name, start, end, node.lineno))
  return tuple(spans)


@dataclass(frozen=True)
class FileChange:
  """Changed lines of one file plus the definitions it contains."""

  path: str
  lines: frozenset[int]
  is_new: bool
  spans: tuple[Span, ...] = ()

  def enclosing(self, line: int, kinds: tuple[str, ...] = ("function", LEVEL_CLASS)) -> Span | None:
    """Return the innermost definition of the given kinds containing a line."""
    candidates = [s for s in self.spans if s.kind in kinds and s.contains(line)]
    return max(candidates, key=lambda span: span.start, default=None)

  def touches(self, span: Span) -> bool:
    """Whether any changed line falls inside a definition."""
    return self.is_new or any(span.contains(line) for line in self.lines)

  def in_scope(self, line: int, level: str) -> bool:
    """Whether a finding reported at a line, with a scope level, is in scope."""
    if self.is_new or level == LEVEL_PROJECT or line in self.lines:
      return True
    if level == LEVEL_LINE:
      return False
    kinds = (LEVEL_CLASS,) if level == LEVEL_CLASS else ("function", LEVEL_CLASS)
    span = self.enclosing(line, kinds)
    return span is not None and self.touches(span)


@dataclass(frozen=True)
class ChangeSet:
  """Every Python file the harness considers changed, keyed by repo-relative path."""

  base: Base
  files: dict[str, FileChange] = field(default_factory=dict)
  whole_project: bool = False

  @property
  def paths(self) -> list[str]:
    """Sorted paths of the changed files."""
    return sorted(self.files)

  def in_scope(self, path: str, line: int, level: str) -> bool:
    """Whether a finding belongs to code the current change touched."""
    if level == LEVEL_PROJECT or self.whole_project:
      return True
    change = self.files.get(path)
    return change is not None and change.in_scope(line, level)

  def symbol(self, path: str, line: int) -> Span | None:
    """Return the innermost definition containing a line, for report headings."""
    change = self.files.get(path)
    return change.enclosing(line) if change else None

  def restricted_to(self, path: str) -> ChangeSet:
    """Return a copy holding only one file, for --file mode."""
    kept = {p: c for p, c in self.files.items() if p == path}
    return ChangeSet(self.base, kept, self.whole_project)


def parse_diff(diff: str) -> dict[str, tuple[set[int], bool]]:
  """Map each file in a -U0 diff to (added or modified lines, whether it is new)."""
  result: dict[str, tuple[set[int], bool]] = {}
  current: str | None = None
  is_new = False
  for raw in diff.splitlines():
    if raw.startswith("diff --git "):
      current, is_new = None, False
    elif raw.startswith("--- "):
      is_new = raw == "--- /dev/null"
    elif raw.startswith("+++ "):
      current = None if raw == "+++ /dev/null" else raw[len("+++ b/") :]
      if current is not None:
        result.setdefault(current, (set(), is_new))
    elif current is not None and (match := _HUNK.match(raw)):
      start, count = int(match.group(1)), int(match.group(2) or "1")
      result[current][0].update(range(start, start + count))
  return result


def _python_files(paths: list[str], scope_dirs: tuple[str, ...]) -> list[str]:
  """Keep Python files that live under one of the scope directories."""
  prefixes = tuple(f"{d.rstrip('/')}/" for d in scope_dirs)
  return [p for p in paths if p.endswith(".py") and p.startswith(prefixes)]


def _with_spans(path: str, lines: set[int], is_new: bool) -> FileChange | None:
  """Build a FileChange, reading the file to index its definitions."""
  try:
    source = Path(path).read_text(encoding="utf-8")
  except FileNotFoundError:
    return None
  return FileChange(path, frozenset(lines), is_new, definition_spans(source))


def untracked_files(scope_dirs: tuple[str, ...]) -> list[str]:
  """Untracked, non-ignored files under the scope directories."""
  out = git("ls-files", "--others", "--exclude-standard", "-z", "--", *scope_dirs)
  return [p for p in out.split("\0") if p]


def compute_changes(base: Base, scope_dirs: tuple[str, ...]) -> ChangeSet:
  """Diff the base against the working tree, including staged, unstaged and untracked."""
  diff = git(
    "diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "-M", base.ref, "--", *scope_dirs
  )
  parsed = parse_diff(diff)
  for path in untracked_files(scope_dirs):
    parsed[path] = (set(), True)
  files: dict[str, FileChange] = {}
  for path in _python_files(list(parsed), scope_dirs):
    lines, is_new = parsed[path]
    if not lines and not is_new:
      continue
    change = _with_spans(path, lines, is_new)
    if change is not None:
      files[path] = change
  return ChangeSet(base, files)


def whole_project(base: Base, scope_dirs: tuple[str, ...]) -> ChangeSet:
  """Treat every Python file under the scope directories as new, for --all audits."""
  listed = git("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *scope_dirs)
  files: dict[str, FileChange] = {}
  for path in _python_files([p for p in listed.split("\0") if p], scope_dirs):
    change = _with_spans(path, set(), is_new=True)
    if change is not None:
      files[path] = change
  return ChangeSet(base, files, whole_project=True)
