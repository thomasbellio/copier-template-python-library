"""Skip cosmic-ray mutants inside annotations that Python never evaluates.

Run after cr-filter-git: `python -m harness.annotation_filter <session.sqlite>`.

Python 3.14 evaluates no function annotation, no annotation of a target inside a
function body and no `type` alias value unless something reads it (PEP 649/695),
so a mutant there (`X | None` -> `X + None`) cannot change behaviour and no test
can kill it. Class-body annotations are left alone: pydantic models and dataclasses
evaluate them, so mutants there are killable.
"""

import ast
import sys
from functools import cache
from pathlib import Path

from cosmic_ray.work_db import WorkDB, use_db
from cosmic_ray.work_item import WorkerOutcome, WorkResult

type Position = tuple[int, int]
type Span = tuple[Position, Position]

_SKIPPED = WorkResult(
  output=None, test_outcome=None, diff=None, worker_outcome=WorkerOutcome.SKIPPED
)


def _span(node: ast.expr) -> Span:
  """Start and end of `node` as (1-based line, 0-based column), like cosmic-ray."""
  return (node.lineno, node.col_offset), (node.end_lineno or node.lineno, node.end_col_offset or 0)


def _function_annotations(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.expr]:
  """Parameter and return annotations, and annotations of targets in the body."""
  args = fn.args
  params = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
  found = [p.annotation for p in params if p is not None and p.annotation is not None]
  if fn.returns is not None:
    found.append(fn.returns)
  found += [
    node.annotation
    for stmt in fn.body
    for node in ast.walk(stmt)
    if isinstance(node, ast.AnnAssign)
  ]
  return found


@cache
def unevaluated_spans(path: Path) -> tuple[Span, ...]:
  """Source spans in `path` that hold never-evaluated annotations."""
  tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
  spans: list[Span] = []
  for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
      spans += [_span(a) for a in _function_annotations(node)]
    elif isinstance(node, ast.TypeAlias):
      spans.append(_span(node.value))
  return tuple(spans)


def _inside(start: Position, end: Position, spans: tuple[Span, ...]) -> bool:
  return any(s <= start and end <= e for s, e in spans)


def skip_annotation_mutants(db: WorkDB) -> int:
  """Mark every work item whose mutations all sit in unevaluated annotations as
  skipped; return how many were marked."""
  skipped = 0
  for item in db.work_items:
    if all(
      _inside(tuple(m.start_pos), tuple(m.end_pos), unevaluated_spans(Path(m.module_path)))
      for m in item.mutations
    ):
      db.set_result(item.job_id, _SKIPPED)
      skipped += 1
  return skipped


def main(argv: list[str]) -> int:
  """Filter the session at `argv[0]`."""
  with use_db(argv[0], WorkDB.Mode.open) as db:
    print(f"annotation filter: skipped {skip_annotation_mutants(db)} mutants")
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
