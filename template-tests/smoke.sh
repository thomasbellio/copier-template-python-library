#!/usr/bin/env bash
# Smoke test for the agent harness.
#
# Generates a project from this template (including uncommitted changes) into a temporary
# directory and runs the scenarios from briefs/agent-harness-implementation-brief.md §13.
# All commits happen inside the temporary project only.
#
# Usage: template-tests/smoke.sh [scenario ...]     e.g. smoke.sh 2 3 11
# Env:   SMOKE_WORK_DIR=<dir>  keep the generated project there (default: mktemp)
#        SMOKE_REUSE=1         reuse an already generated project in SMOKE_WORK_DIR
set -uo pipefail

TEMPLATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${SMOKE_WORK_DIR:-$(mktemp -d)}"
PKG="smoke_pkg"
PROJECT="${WORK_DIR}/${PKG}"
DEFAULT_BRANCH="master"
EMPTY_TREE="4b825dc642cb6eb9a060e54bf8d69288fbee4904"
FILE_BUDGET_MS=2000

export GIT_AUTHOR_NAME="Smoke Test" GIT_AUTHOR_EMAIL="smoke@example.com"
export GIT_COMMITTER_NAME="Smoke Test" GIT_COMMITTER_EMAIL="smoke@example.com"
# Isolate from the caller's git config so generation takes the "no author anywhere" path.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1

PASSED=0
FAILURES=()
OUT=""
CODE=0

# --- helpers -------------------------------------------------------------------------------

generate() {
  if [[ -n "${SMOKE_REUSE:-}" && -d "${PROJECT}/.git" ]]; then
    echo "Reusing ${PROJECT}"
    return
  fi
  rm -rf "${PROJECT}"
  echo "Generating project into ${PROJECT}"
  if ! copier copy --trust --defaults --quiet --data "project_name=${PKG}" \
    "${TEMPLATE_DIR}" "${PROJECT}"; then
    echo "FATAL: copier copy failed (the initial commit must pass every gate)" >&2
    exit 2
  fi
}

# Reset the project to the generated initial commit on a new branch.
fresh() {
  local name="$1"
  cd "${PROJECT}" || exit 2
  git checkout -q -f -B "${DEFAULT_BRANCH}" "${INITIAL}"
  git clean -fdq
  rm -rf .harness
  git checkout -q -b "scenario-${name}"
}

# Commit the working tree on the default branch, then branch off it again.
commit_on_default() {
  local name="$1"
  git checkout -q "${DEFAULT_BRANCH}"
  git add -A
  git commit -q --no-verify -m "smoke: setup for scenario ${name}"
  git checkout -q -B "scenario-${name}"
}

check() {
  OUT="$(cd "${PROJECT}" && ./scripts/check.sh "$@" 2>&1)"
  CODE=$?
}

# expect <scenario> <description> <exit-code> [pattern ...]; a pattern starting with ! must not match.
expect() {
  local id="$1" desc="$2" want="$3"
  shift 3
  local problems=()
  [[ "${CODE}" == "${want}" ]] || problems+=("exit ${CODE}, wanted ${want}")
  local pattern
  for pattern in "$@"; do
    if [[ "${pattern}" == !* ]]; then
      grep -qiE -- "${pattern:1}" <<<"${OUT}" && problems+=("output matches '${pattern:1}'")
    else
      grep -qiE -- "${pattern}" <<<"${OUT}" || problems+=("output lacks '${pattern}'")
    fi
  done
  if ((${#problems[@]} == 0)); then
    PASSED=$((PASSED + 1))
    echo "PASS  ${id}: ${desc}"
  else
    FAILURES+=("${id}")
    echo "FAIL  ${id}: ${desc} -- ${problems[*]}"
    sed 's/^/      | /' <<<"${OUT}"
  fi
}

write() {
  mkdir -p "$(dirname "$1")"
  cat >"$1"
}

# --- fixtures ------------------------------------------------------------------------------

TANGLED='

def tangled(values: list[int]) -> int:
  """Sum values through deliberately nested logic."""
  total = 0
  for value in values:
    if value > 0:
      for step in range(value):
        if step % 2 == 0:
          while step > 0:
            if step % 3 == 0:
              total += step
            step -= 1
  return total
'

SHOUT='

def shout(text: str) -> str:
  """Return the text in upper case."""
  return text.upper()
'

# --- scenarios -----------------------------------------------------------------------------

scenario_0() {
  fresh 0
  HARNESS_BASE="${EMPTY_TREE}" check
  expect 0 "generated skeleton passes with every file treated as new" 0 "HARNESS PASSED"
}

scenario_1() {
  fresh 1
  check
  expect 1 "no changes" 0 "no changed files"
}

scenario_2() {
  fresh 2
  printf '"""Feature module."""\n%s' "${TANGLED}" | write "src/${PKG}/feature.py"
  check
  expect 2 "cognitive complexity above 15" 1 "\[cognitive-complexity\] 2[0-9] > 15" "Fix: "
}

scenario_3() {
  fresh 3
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""


def configure(a: int, b: int, c: int, d: int, e: int, f: int, g: int) -> int:
  """Add seven numbers."""
  return a + b + c + d + e + f + g
EOF
  check
  expect 3 "function with 7 arguments" 1 "\[PLR0913\]"
}

scenario_11() {
  fresh 11
  printf '"""Feature module."""\n%s%s' "${TANGLED}" "${SHOUT}" | write "src/${PKG}/feature.py"
  commit_on_default 11
  sed -i 's/return text.upper()/return text.upper() + "!"/' "src/${PKG}/feature.py"
  check
  expect 11 "editing a different function leaves the complex one out of scope" 0 \
    "HARNESS PASSED" "!tangled"
}

scenario_12() {
  fresh 12
  printf '"""Feature module."""\n%s%s' "${TANGLED}" "${SHOUT}" | write "src/${PKG}/feature.py"
  commit_on_default 12
  sed -i 's/total += step/total += step * 2/' "src/${PKG}/feature.py"
  check
  expect 12 "editing a line inside the complex function brings it into scope" 1 \
    "tangled\(\)" "cognitive-complexity"
}

scenario_13() {
  fresh 13
  printf '"""Feature module."""\n%s' "${TANGLED}" | write "src/${PKG}/feature.py"
  local started elapsed
  started=$(date +%s%N)
  check --file "src/${PKG}/feature.py"
  elapsed=$((($(date +%s%N) - started) / 1000000))
  OUT="${OUT}"$'\n'"elapsed_ms=${elapsed}"
  expect 13 "--file mode fails fast (${elapsed} ms)" 1 "cognitive-complexity"
  if ((elapsed > FILE_BUDGET_MS)); then
    FAILURES+=("13-budget")
    echo "FAIL  13: --file took ${elapsed} ms, budget ${FILE_BUDGET_MS} ms"
  fi
}

scenario_4() {
  fresh 4
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""


def risky() -> None:
  """Try something and ignore any failure."""
  try:
    print("working")
  except Exception:
    pass
EOF
  check
  expect 4 "except Exception: pass" 1 "\[BLE001\]" "\[S110\]"
}

scenario_5() {
  fresh 5
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""


def _unused() -> int:
  """Return one."""
  return 1
EOF
  check
  expect 5 "unused private helper" 1 "\[dead-code\] unused function '_unused'"
}

scenario_6() {
  fresh 6
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""


def scale(value: int) -> int:
  """Scale a value.

  Args:
    value: The value to scale.
    factor: An argument that does not exist.

  Returns:
    The scaled value.
  """
  return value * 2
EOF
  check
  expect 6 "docstring lists an argument that does not exist" 1 "\[DOC10[0-9]\]"
}

scenario_7() {
  fresh 7
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""

from typing import Any


def describe(x: Any) -> str:
  """Describe a value."""
  return repr(x)
EOF
  check
  expect 7 "explicit Any" 1 "\[mypy:explicit-any\]"
}

scenario_8() {
  fresh 8
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""


def answer() -> int:
  """Return the answer."""
  return "42"  # type: ignore
EOF
  check
  expect 8 "bare type: ignore" 1 "\[bare-type-ignore\]"
}

scenario_9() {
  fresh 9
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""

import tests


def suite_name() -> str:
  """Name of the test package."""
  return tests.__name__
EOF
  check
  expect 9 "import breaking the shipped forbidden contract" 1 "\[import-contract\].*-> tests"
}

ORDERS='

def order_total(items: list[tuple[str, float, int]]) -> float:
  """Total an order, applying a bulk discount per line."""
  result = 0.0
  for name, price, qty in items:
    if not name:
      continue
    if qty <= 0:
      raise ValueError(name)
    discount = 0.1 if qty > 10 else 0.0
    line = price * qty * (1 - discount)
    result += round(line, 2)
  return result


def invoice_total(entries: list[tuple[str, float, int]]) -> float:
  """Total an invoice, applying a bulk rebate per entry."""
  acc = 0.0
  for label, cost, count in entries:
    if not label:
      continue
    if count <= 0:
      raise ValueError(label)
    rebate = 0.1 if count > 10 else 0.0
    amount = cost * count * (1 - rebate)
    acc += round(amount, 2)
  return acc
'

add_changelog_entry() {
  sed -i "0,/^- Initial project setup$/s//- Initial project setup\n- $1/" CHANGELOG.md
}

scenario_10() {
  fresh 10
  printf '"""Order maths."""\n%s' "${ORDERS}" | write "src/${PKG}/orders.py"
  add_changelog_entry "Order and invoice totals"
  check
  expect 10 "near-identical functions give one clone advisory" 0 "HARNESS PASSED" "\[clone\]" \
    "!\[changelog\]"
  local clones
  clones=$(grep -c "\[clone\]" <<<"${OUT}")
  if ((clones != 1)); then
    FAILURES+=("10-count")
    echo "FAIL  10: expected exactly one clone advisory, got ${clones}"
  fi
}

scenario_19() {
  fresh 19
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""


def undocumented(value: int) -> int:
  return value + 1
EOF
  check
  expect 19 "public function without a docstring" 1 "\[D103\]"
}

scenario_20() {
  fresh 20
  write "src/${PKG}/feature.py" <<'EOF'
"""Feature module."""


def _helper(value: int) -> int:
  return value + 1


def increment(value: int) -> int:
  """Add one to a value."""
  return _helper(value)
EOF
  check
  expect 20 "private helper without a docstring" 0 "HARNESS PASSED" "!\[D10[0-9]\]"
}

scenario_21() {
  fresh 21
  write "src/${PKG}/cli.py" <<'EOF'
"""Command-line entry point."""

import logging

logger = logging.getLogger(__name__)


def main() -> int:
  """Run the command and turn any failure into an exit code."""
  try:
    return run()
  except Exception:  # noqa: BLE001  # reason: top-level CLI boundary, error is logged
    logger.exception("command failed")
    return 1


def run() -> int:
  """Do the work."""
  return 0
EOF
  check
  expect 21 "justified broad handler" 0 "HARNESS PASSED" \
    "Suppressions added in this diff: 1 \(all justified\)"
}

SIMPLE_MODULE='"""Greeting helpers."""


def greet(name: str) -> str:
  """Return a greeting for a name."""
  return f"Hello, {name}"
'

scenario_22() {
  fresh 22
  printf '%s' "${SIMPLE_MODULE}" | write "src/${PKG}/greeting.py"
  check
  expect 22 "src change without a changelog entry" 0 "HARNESS PASSED" "\[changelog\]"
}

scenario_23() {
  fresh 23
  printf '%s' "${SIMPLE_MODULE}" | write "src/${PKG}/greeting.py"
  add_changelog_entry "A greeting helper"
  check
  expect 23 "src change with a changelog entry" 0 "HARNESS PASSED" "!\[changelog\]"
}

# --- Claude Code hook adapters ---------------------------------------------------------------

# hook <script> <json-payload>: run a hook as Claude Code would; sets OUT (stdout+stderr), CODE.
hook() {
  local script="$1" payload="$2"
  OUT="$(cd "${PROJECT}" && CLAUDE_PROJECT_DIR="${PROJECT}" \
    uv run --no-sync python ".claude/hooks/${script}" <<<"${payload}" 2>&1)"
  CODE=$?
}

bash_payload() {
  python3 -c 'import json, sys; print(json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}}))' "$1"
}

file_payload() {
  printf '{"tool_name": "%s", "tool_input": {"file_path": "%s"}}' "$1" "$2"
}

scenario_15() {
  fresh 15
  printf '"""Feature module."""\n%s' "${TANGLED}" | write "src/${PKG}/feature.py"
  hook stop.py '{"hook_event_name": "Stop", "stop_hook_active": false}'
  expect 15 "stop.py blocks on a failing gate" 2 "HARNESS FAILED" "cognitive-complexity" \
    "Fix the blocking findings in the definitions you changed"
}

scenario_16() {
  fresh 16
  printf '"""Feature module."""\n%s' "${TANGLED}" | write "src/${PKG}/feature.py"
  hook stop.py '{"hook_event_name": "Stop", "stop_hook_active": true}'
  expect 16 "stop.py does not block twice; tells the human" 0 '^\{"systemMessage": ".*still fails'
}

scenario_17() {
  fresh 17
  printf '%s' "${SIMPLE_MODULE}" | write "src/${PKG}/greeting.py"
  write "tests/test_greeting.py" <<EOF
"""Tests for the greeting helpers."""

from ${PKG}.greeting import greet


def test_greet_names_the_person() -> None:
  """The greeting includes the name it was given."""
  assert greet("Ada") == "Hello, Ada"
EOF
  add_changelog_entry "A greeting helper"
  hook stop.py '{"hook_event_name": "Stop", "stop_hook_active": false}'
  expect 17a "stop.py passes a clean change and records it" 0 "!."
  # Hide a tool. If the second run reached the gate it would report a harness error.
  mv .venv/bin/mypy .venv/bin/mypy.hidden
  hook stop.py '{"hook_event_name": "Stop", "stop_hook_active": false}'
  mv .venv/bin/mypy.hidden .venv/bin/mypy
  expect 17b "stop.py skips the tools for an unchanged passing tree" 0 "!."
}

scenario_18() {
  fresh 18
  hook guard_config.py "$(file_payload Edit "${PROJECT}/complexipy.toml")"
  expect 18 "guard_config asks before editing complexipy.toml" 0 '"permissionDecision": "ask"'
  hook guard_config.py "$(file_payload Write "${PROJECT}/.claude/hooks/stop.py")"
  expect 18b "guard_config asks before editing .claude/" 0 '"permissionDecision": "ask"'
  hook guard_config.py "$(file_payload Edit "${PROJECT}/src/${PKG}/__init__.py")"
  expect 18c "guard_config ignores ordinary source files" 0 "!."
}

scenario_24() {
  fresh 24
  local command
  for command in "git commit -m x" "git add ." "git -C . push" "ruff check . && git stash" \
    "bash -c 'git commit -am wip'" "GIT_PAGER=cat git reset --hard" "git checkout -- src"; do
    hook guard_git.py "$(bash_payload "${command}")"
    expect 24 "guard_git asks for: ${command}" 0 '"permissionDecision": "ask"'
  done
}

scenario_25() {
  fresh 25
  local command
  for command in "git status" "git diff" "git log --grep commit" "git stash list" \
    "git checkout -b feature" "echo commit && ls" "git tag"; do
    hook guard_git.py "$(bash_payload "${command}")"
    expect 25 "guard_git lets through: ${command}" 0 "!."
  done
}

scenario_post() {
  fresh post
  printf '"""Feature module."""\n%s' "${TANGLED}" | write "src/${PKG}/feature.py"
  hook post_edit.py "$(file_payload Edit "${PROJECT}/src/${PKG}/feature.py")"
  expect post "post_edit reports findings for the edited file" 2 "cognitive-complexity"
  hook post_edit.py "$(file_payload Edit "${PROJECT}/README.md")"
  expect post-b "post_edit ignores non-Python files" 0 "!."
}

# --- lefthook and CI adapters ----------------------------------------------------------------

notice() {
  OUT="$(cd "${PROJECT}" && PYTHONPATH=scripts uv run --no-sync python -m harness.ci_notice 2>&1)"
  CODE=$?
}

scenario_notice() {
  fresh notice
  printf '%s' "${SIMPLE_MODULE}" | write "src/${PKG}/greeting.py"
  notice
  expect notice "CI notice stays quiet for an ordinary change" 0 "No harness configuration changed"
  sed -i 's/^max-complexity-allowed = 15$/max-complexity-allowed = 25/' complexipy.toml
  sed -i 's/^line-length = 100$/line-length = 120/' pyproject.toml
  notice
  expect notice-b "CI notice flags guarded files and tool tables" 0 \
    "::notice title=Agent harness configuration changed::" "complexipy.toml" \
    "pyproject.toml \[tool.ruff\]" "!\[tool.mypy\]"
}

# A commit made with --no-verify is still stopped when it is pushed.
scenario_prepush() {
  fresh prepush
  local remote="${WORK_DIR}/remote.git"
  rm -rf "${remote}"
  git init -q --bare "${remote}"
  git remote remove origin 2>/dev/null
  git remote add origin "${remote}"
  git push -q origin "${DEFAULT_BRANCH}" 2>/dev/null
  printf '"""Feature module."""\n%s' "${TANGLED}" | write "src/${PKG}/feature.py"
  git add -A
  git commit -q --no-verify -m "feat: tangled"
  OUT="$(git push origin "scenario-prepush" 2>&1)"
  CODE=$?
  [[ "${CODE}" != 0 ]] && CODE=1
  expect prepush "lefthook pre-push refuses a --no-verify commit that fails the gate" 1 \
    "cognitive-complexity"
  git remote remove origin
}

scenario_delta() {
  fresh delta
  printf '"""Feature module."""\n%s' "${TANGLED}" | write "src/${PKG}/feature.py"
  OUT="$(.venv/bin/complexipy src --diff-only "${INITIAL}" --color no 2>&1 | sed -n '/Complexity diff/,$p')"
  CODE=0
  expect delta "complexity delta for the PR summary lists the new function" 0 \
    "Complexity diff" "feature.py::tangled"
}

# --- mutation testing and hotspots -----------------------------------------------------------

DISCOUNT_MODULE='"""Bulk discounts."""


def discount(qty: int) -> float:
  """Discount rate for an order quantity: 10% above ten items."""
  if qty > 10:
    return 0.1
  return 0.0
'

scenario_mutation() {
  fresh mutation
  printf '%s' "${DISCOUNT_MODULE}" | write "src/${PKG}/discount.py"
  write "tests/test_discount.py" <<EOF
"""Weak tests: they only check the type, so mutants survive."""

from ${PKG}.discount import discount


def test_discount_is_a_rate() -> None:
  """The discount is a float."""
  assert isinstance(discount(5), float)
EOF
  check --mutation
  expect mutation "weak tests let mutants survive on new, untracked files" 1 \
    "MUTATION FAILED" 'discount.py:[0-9]+  `if qty > 10:` survives [0-9]+ mutation' \
    '\[core/[A-Za-z_]+\] -> `' "Fix: Add an assertion"
  local index_state
  index_state="$(git status --porcelain -- "src/${PKG}/discount.py")"
  OUT="${index_state}"
  CODE=0
  expect mutation-index "the real git index is untouched (file still untracked)" 0 '^\?\? '
}

scenario_mutation_b() {
  fresh mutation-b
  printf '%s' "${DISCOUNT_MODULE}" | write "src/${PKG}/discount.py"
  write "tests/test_discount.py" <<EOF
"""Tests pinning the discount boundary."""

from ${PKG}.discount import discount


def test_no_discount_up_to_ten_items() -> None:
  """Ten items or fewer get no discount."""
  assert discount(10) == 0.0
  assert discount(1) == 0.0


def test_ten_percent_above_ten_items() -> None:
  """More than ten items get 10%."""
  assert discount(11) == 0.1
EOF
  check --mutation
  expect mutation-b "boundary tests kill the mutants" 0 "MUTATION PASSED"
}

scenario_mutation_c() {
  fresh mutation-c
  check --mutation
  expect mutation-c "no source change means nothing to mutate" 0 \
    "MUTATION PASSED: no changed source files"
}

scenario_hotspots() {
  fresh hotspots
  local round
  for round in 1 2 3; do
    printf '"""Feature module."""\n%s\n\nREVISION = %s\n' "${TANGLED}" "${round}" \
      | write "src/${PKG}/feature.py"
    git add -A
    git commit -q --no-verify -m "chore: revision ${round}"
  done
  OUT="$(cd "${PROJECT}" && ./scripts/hotspots.sh 2>&1)"
  CODE=$?
  expect hotspots "hotspots ranks a churned, complex file first" 0 \
    "\| 1 \| \`src/${PKG}/feature.py\` \| 3 \| 21 \| 63 \|" "\`tangled\` \(21\)"
  [[ -f reports/hotspots.md ]] || { FAILURES+=("hotspots-file"); echo "FAIL  hotspots: no report file"; }
}

# --- copier update ---------------------------------------------------------------------------

# `copier update` keeps project-owned files (_skip_if_exists) and merges local AGENTS.md edits
# with template changes. Uses a scratch clone of the template with two committed versions.
scenario_update() {
  local clone="${WORK_DIR}/template-clone" target="${WORK_DIR}/update_pkg"
  rm -rf "${clone}" "${target}"
  git clone -q "${TEMPLATE_DIR}" "${clone}"
  (cd "${TEMPLATE_DIR}" && git ls-files -co --exclude-standard -z) \
    | (cd "${TEMPLATE_DIR}" && xargs -0 cp --parents -t "${clone}")
  git -C "${clone}" add -A && git -C "${clone}" commit -qm "v1" --allow-empty && git -C "${clone}" tag v1
  copier copy --trust --defaults --quiet --vcs-ref v1 --data project_name=update_pkg \
    "${clone}" "${target}" >/dev/null 2>&1 || { FAILURES+=("update-gen"); echo "FAIL  update: copy"; return; }
  cd "${target}" || return
  printf '\n- Local convention: prefer pathlib over os.path.\n' >> AGENTS.md
  printf '\n# Local contract marker\n' >> .importlinter
  git add -A && git commit -qm "chore: local edits" --no-verify
  local importlinter="{% if enable_agent_harness %}.importlinter{% endif %}.jinja"
  local agents="{% if enable_agent_harness %}AGENTS.md{% endif %}.jinja"
  sed -i 's/^## Commands$/## Commands\n\n- Template v2 note./' "${clone}/${agents}"
  printf '\n# Template v2 comment\n' >> "${clone}/${importlinter}"
  git -C "${clone}" commit -qam "v2" && git -C "${clone}" tag v2
  OUT="$(copier update --trust --defaults --skip-tasks --quiet --vcs-ref v2 2>&1)"
  CODE=$?
  OUT="${OUT}"$'\n'"$(cat AGENTS.md .importlinter)"$'\n'"conflicts: $(git diff --name-only --diff-filter=U)"
  expect update "copier update merges AGENTS.md and keeps project-owned .importlinter" 0 \
    "Template v2 note" "Local convention: prefer pathlib" "Local contract marker" \
    "!Template v2 comment" "!<<<<<<<"
  cd "${PROJECT}" || exit 2
}

# The harness code must pass the harness's own rules, even though it lives outside src/.
scenario_self() {
  fresh self
  local bin=".venv/bin" problems=0 preview="PLR0904,PLR0914,PLR0916,PLR0917,PLR1702"
  OUT="$(
    {
      local strict=(--strict --warn-unreachable --disallow-any-explicit
        --enable-error-code ignore-without-code --enable-error-code redundant-expr
        --enable-error-code truthy-bool)
      MYPYPATH=scripts "${bin}/mypy" "${strict[@]}" -p harness || echo "SELF-FAIL mypy harness"
      MYPYPATH=scripts "${bin}/mypy" "${strict[@]}" .claude/hooks || echo "SELF-FAIL mypy hooks"
      "${bin}/ruff" check --preview --config 'lint.explicit-preview-rules = true' \
        --extend-select "${preview}" scripts .claude || echo "SELF-FAIL ruff"
      "${bin}/complexipy" scripts .claude --max-complexity-allowed 15 --quiet \
        || echo "SELF-FAIL complexipy"
      "${bin}/pydoclint" --config=pyproject.toml --quiet scripts .claude/hooks 2>&1 \
        || echo "SELF-FAIL pydoclint"
    } 2>&1
  )"
  CODE=0
  grep -q "SELF-FAIL" <<<"${OUT}" && CODE=1
  expect self "harness code passes strict mypy, preview Ruff rules, complexipy, pydoclint" 0
}

ALL_SCENARIOS=(0 1 2 3 4 5 6 7 8 9 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 post notice prepush delta mutation mutation_b mutation_c hotspots update self)

main() {
  generate
  INITIAL="$(git -C "${PROJECT}" rev-parse HEAD)"
  local selected=("$@")
  ((${#selected[@]})) || selected=("${ALL_SCENARIOS[@]}")
  local id
  for id in "${selected[@]}"; do
    "scenario_${id}"
  done
  cd "${PROJECT}" && git checkout -q -f -B "${DEFAULT_BRANCH}" "${INITIAL}" && git clean -fdq
  echo
  echo "${PASSED} passed, ${#FAILURES[@]} failed${FAILURES:+: ${FAILURES[*]}}"
  echo "Project kept at ${PROJECT}"
  ((${#FAILURES[@]} == 0))
}

main "$@"
