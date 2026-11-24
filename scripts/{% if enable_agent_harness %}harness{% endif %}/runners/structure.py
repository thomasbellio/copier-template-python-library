"""pyscn: dependency cycles, class coupling (CBO), class cohesion (LCOM4) and clones.

One `pyscn analyze` run feeds all four. pyscn has no CBO or LCOM gate flags, so the
thresholds from harness.toml are applied here.
"""

import ast
import json
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path

from harness.report import Finding
from harness.runners.base import Context, Outcome, Runner
from harness.runners.imports import module_path
from harness.scope import LEVEL_CLASS, LEVEL_DEF, LEVEL_PROJECT, definition_spans
from harness.tools import find_tool, run_status, tool_failure

type Json = Mapping[str, object]

EXEMPT_BASES = frozenset(
  {"Protocol", "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "NamedTuple", "TypedDict"}
)
FIX_CYCLE = "Break the cycle: move the shared code into a module both can import."
FIX_CBO = "The class depends on too many other classes. Split it or inject collaborators."
FIX_LCOM = "The class holds unrelated groups of methods. Split it along those groups."
FIX_CLONE = "Reuse or merge the two fragments, or say in your final message why both are needed."


def analyze(ctx: Context) -> Json:
  """Run pyscn once and return its JSON report."""
  cmd = [find_tool("pyscn"), "analyze", "--json", "--output", "-"]
  cmd += ["--select", "cbo,lcom,clones,deps", "src"]
  code, stdout, stderr = run_status(cmd)
  try:
    data = json.loads(stdout)
  except json.JSONDecodeError:
    data = None
  if not isinstance(data, Mapping):
    raise tool_failure(cmd, code, stderr or stdout)
  return data


def section(data: Json, *keys: str) -> Json:
  """Walk nested JSON objects, returning an empty mapping when a key is missing."""
  current: object = data
  for key in keys:
    current = current.get(key) if isinstance(current, Mapping) else None
  return current if isinstance(current, Mapping) else {}


def items(data: Json, key: str) -> list[Json]:
  """Return a list of JSON objects stored under a key."""
  value = data.get(key)
  return [v for v in value if isinstance(v, Mapping)] if isinstance(value, list) else []


def number(data: Json, *keys: str) -> float:
  """Read a nested numeric value, defaulting to 0."""
  *parents, last = keys
  value = section(data, *parents).get(last)
  return float(value) if isinstance(value, int | float) else 0.0


def _base_name(node: ast.expr) -> str:
  """Name of a base class or decorator expression, ignoring module prefixes and calls."""
  if isinstance(node, ast.Call):
    node = node.func
  if isinstance(node, ast.Attribute):
    return node.attr
  return node.id if isinstance(node, ast.Name) else ""


def _is_exempt(node: ast.ClassDef) -> bool:
  """Dataclasses, protocols, enums and exceptions give false CBO/LCOM positives."""
  if any(_base_name(d) == "dataclass" for d in node.decorator_list):
    return True
  bases = {_base_name(b) for b in node.bases}
  return bool(bases & EXEMPT_BASES) or any(b.endswith(("Error", "Exception")) for b in bases)


@cache
def exempt_class_lines(path: str) -> frozenset[int]:
  """Line numbers of class definitions in a file that are exempt from CBO and LCOM."""
  try:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
  except (OSError, SyntaxError):
    return frozenset()
  classes = (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
  return frozenset(n.lineno for n in classes if _is_exempt(n))


def cycle_findings(ctx: Context, data: Json) -> list[Finding]:
  """Block when the project has more import cycles than harness.toml allows."""
  circular = section(data, "system", "dependency_analysis", "circular_dependencies")
  allowed = ctx.config.integer("pyscn", "allowed_cycles", 0)
  total = int(number(circular, "total_cycles"))
  if total <= allowed:
    return []
  findings: list[Finding] = []
  for cycle in items(circular, "circular_dependencies"):
    raw_modules = cycle.get("modules")
    modules = [str(m) for m in raw_modules] if isinstance(raw_modules, list) else []
    chain = " -> ".join([*modules, modules[0]]) if modules else "unknown modules"
    findings.append(
      Finding(
        path=module_path(ctx, modules[0]) if modules else "",
        line=1,
        rule="import-cycle",
        message=f"{chain} ({total} cycles, {allowed} allowed)",
        tool="pyscn",
        level=LEVEL_PROJECT,
        fix=FIX_CYCLE,
      )
    )
  return findings


def _class_finding(ctx: Context, entry: Json, rule: str, message: str, blocking: bool) -> Finding:
  """Build a class-level finding from a pyscn class entry."""
  fix = FIX_CBO if rule == "coupling" else FIX_LCOM
  return Finding(
    path=ctx.relative(str(entry.get("file_path", ""))),
    line=int(number(entry, "start_line")),
    rule=rule,
    message=message,
    tool="pyscn",
    blocking=blocking,
    level=LEVEL_CLASS,
    fix=fix,
  )


def class_findings(ctx: Context, data: Json) -> list[Finding]:
  """Coupling above the limit blocks; high LCOM4 blocks and medium LCOM4 advises."""
  max_cbo = ctx.config.integer("pyscn", "max_cbo", 7)
  lcom_block = ctx.config.integer("pyscn", "lcom_block_above", 5)
  lcom_advise = ctx.config.integer("pyscn", "lcom_advise_above", 2)
  findings: list[Finding] = []
  for entry in items(section(data, "cbo"), "classes"):
    cbo = int(number(entry, "metrics", "coupling_count"))
    if cbo > max_cbo and not _exempt(ctx, entry):
      message = f"class {entry.get('name')} couples to {cbo} classes > {max_cbo}"
      findings.append(_class_finding(ctx, entry, "coupling", message, blocking=True))
  for entry in items(section(data, "lcom"), "classes"):
    lcom = int(number(entry, "metrics", "lcom4"))
    if lcom > lcom_advise and not _exempt(ctx, entry):
      message = f"class {entry.get('name')} has LCOM4 {lcom} (limit {lcom_block})"
      findings.append(_class_finding(ctx, entry, "cohesion", message, lcom > lcom_block))
  return findings


def _exempt(ctx: Context, entry: Json) -> bool:
  """Whether a pyscn class entry is a dataclass, protocol, enum or exception."""
  path = ctx.root / ctx.relative(str(entry.get("file_path", "")))
  return int(number(entry, "start_line")) in exempt_class_lines(str(path))


type Fragment = tuple[str, int, int]


def _fragment(ctx: Context, clone: Json) -> Fragment:
  """(path, start line, end line) of one side of a clone pair."""
  location = section(clone, "location")
  path = ctx.relative(str(location.get("file_path", "")))
  return path, int(number(location, "start_line")), int(number(location, "end_line"))


def _inside(inner: Fragment, outer: Fragment) -> bool:
  """Whether one fragment lies within another."""
  return inner[0] == outer[0] and outer[1] <= inner[1] and inner[2] <= outer[2]


def _covered(pair: tuple[Fragment, Fragment], kept: Sequence[tuple[Fragment, Fragment]]) -> bool:
  """Whether a pair repeats a larger pair already reported, or overlaps itself."""
  first, second = pair
  if _inside(first, second) or _inside(second, first):
    return True
  return any(
    (_inside(first, a) and _inside(second, b)) or (_inside(first, b) and _inside(second, a))
    for a, b in kept
  )


def _describe(path: str, line: int) -> str:
  """Location of a fragment with its enclosing definition name, when there is one."""
  try:
    spans = definition_spans(Path(path).read_text(encoding="utf-8"))
  except OSError:
    spans = ()
  inside = [s for s in spans if s.contains(line)]
  name = max(inside, key=lambda s: s.start).name if inside else ""
  return f"{path}:{line} {name}()" if name else f"{path}:{line}"


def clone_findings(ctx: Context, data: Json) -> list[Finding]:
  """Advise on clone pairs above the similarity threshold with at least one side touched."""
  threshold = ctx.config.number("pyscn", "clone_similarity", 0.80)
  pairs: list[tuple[float, Fragment, Fragment]] = []
  for pair in items(section(data, "clone"), "clone_pairs"):
    similarity = number(pair, "similarity")
    if similarity >= threshold:
      left, right = section(pair, "clone1"), section(pair, "clone2")
      pairs.append((similarity, _fragment(ctx, left), _fragment(ctx, right)))
  pairs.sort(key=lambda p: -((p[1][2] - p[1][1]) + (p[2][2] - p[2][1])))
  kept: list[tuple[Fragment, Fragment]] = []
  findings: list[Finding] = []
  for similarity, first, second in pairs:
    touched = [f for f in (first, second) if ctx.changes.in_scope(f[0], f[1], LEVEL_DEF)]
    if not touched or _covered((first, second), kept):
      continue
    kept.append((first, second))
    here, other = (first, second) if touched[0] == first else (second, first)
    findings.append(
      Finding(
        path=here[0],
        line=here[1],
        rule="clone",
        message=f"is {similarity:.0%} similar to {_describe(other[0], other[1])}",
        tool="pyscn",
        blocking=False,
        level=LEVEL_PROJECT,
        fix=FIX_CLONE,
      )
    )
  return findings


def run(ctx: Context) -> Outcome:
  """Run pyscn and apply every structural threshold."""
  data = analyze(ctx)
  findings = cycle_findings(ctx, data) + class_findings(ctx, data) + clone_findings(ctx, data)
  return Outcome(findings)


RUNNER = Runner(name="pyscn", executables=("pyscn",), fast=False, run=run)
