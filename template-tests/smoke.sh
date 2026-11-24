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

ALL_SCENARIOS=(0 1 2 3 11 12 13)

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
