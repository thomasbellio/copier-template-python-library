"""Claude Code PreToolUse hook: ask the human before git changes what is staged or recorded.

Enforces the commit policy in AGENTS.md: agents leave changes unstaged unless asked. Read-only
git commands pass silently. Commands are parsed, not substring-matched, so `git log --grep
commit` passes while `ruff check . && git stash` asks. When parsing is uncertain, ask.
"""

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

RECORDING = frozenset(
  {"add", "commit", "push", "tag", "merge", "rebase", "cherry-pick", "revert", "am"}
)
DISCARDING = frozenset({"reset", "restore", "checkout", "clean", "stash", "switch"})
OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "(", ")", "\n"})
SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
WRAPPERS = frozenset({"sudo", "env", "command", "nohup", "time", "exec"})
READ_ONLY_STASH = frozenset({"list", "show"})
TAG_WRITE_FLAGS = frozenset({"-a", "-s", "-u", "-f", "-d", "--delete", "--force", "--annotate"})
SWITCH_DISCARD = frozenset({"-f", "--force", "--discard-changes"})


class Uncertain(Exception):
  """The command could not be parsed with confidence."""


def segments(command: str) -> Iterator[list[str]]:
  """Split a shell command into simple commands at control operators."""
  lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
  lexer.whitespace_split = True
  try:
    tokens = list(lexer)
  except ValueError as err:
    raise Uncertain(str(err)) from err
  current: list[str] = []
  for token in tokens:
    if token in SEPARATORS or set(token) <= set(";&|"):
      if current:
        yield current
      current = []
    else:
      current.append(token)
  if current:
    yield current


def strip_prefix(words: list[str]) -> list[str]:
  """Drop leading VAR=value assignments and wrappers such as sudo or env."""
  index = 0
  while index < len(words):
    word = words[index]
    if "=" in word and not word.startswith("-") and word.split("=", 1)[0].isidentifier():
      index += 1
    elif word in WRAPPERS:
      index += 1
    else:
      break
  return words[index:]


def git_arguments(words: list[str]) -> tuple[str, list[str]] | None:
  """Return (subcommand, arguments) for a git invocation, skipping global options."""
  if not words or Path(words[0]).name != "git":
    return None
  index = 1
  while index < len(words) and words[index].startswith("-"):
    index += 2 if words[index] in OPTIONS_WITH_VALUE else 1
  if index >= len(words):
    return None
  return words[index], words[index + 1 :]


def resolve_alias(subcommand: str) -> list[str] | None:
  """Expand a git alias into its words, or None when the subcommand is not an alias."""
  result = subprocess.run(
    ["git", "config", "--get", f"alias.{subcommand}"], capture_output=True, text=True, check=False
  )
  expansion = result.stdout.strip()
  if result.returncode != 0 or not expansion:
    return None
  if expansion.startswith("!"):
    raise Uncertain(f"git alias '{subcommand}' runs a shell command")
  return shlex.split(expansion)


def checkout_discards(arguments: list[str]) -> bool:
  """Whether a checkout restores paths (discarding work) rather than switching branch."""
  positional = [a for a in arguments if not a.startswith("-")]
  forced = any(a in ("-f", "--force") for a in arguments)
  return (
    "--" in arguments or forced or len(positional) > 1 or any(Path(a).exists() for a in positional)
  )


def tag_lists(arguments: list[str]) -> bool:
  """`git tag` with no tag name and no write flag only lists tags."""
  return not any(a in TAG_WRITE_FLAGS or not a.startswith("-") for a in arguments)


def stash_reads(arguments: list[str]) -> bool:
  """`git stash list` and `git stash show` only read."""
  return bool(arguments) and arguments[0] in READ_ONLY_STASH


def checkout_switches(arguments: list[str]) -> bool:
  """A checkout that switches branch rather than restoring paths."""
  return not checkout_discards(arguments)


def switch_keeps_work(arguments: list[str]) -> bool:
  """A switch without --force or --discard-changes carries local changes along."""
  return not SWITCH_DISCARD.intersection(arguments)


def clean_is_dry_run(arguments: list[str]) -> bool:
  """`git clean -n` only lists what it would remove."""
  return any(a in ("-n", "--dry-run") for a in arguments)


READ_ONLY_FORMS: dict[str, Callable[[list[str]], bool]] = {
  "tag": tag_lists,
  "stash": stash_reads,
  "checkout": checkout_switches,
  "switch": switch_keeps_work,
  "clean": clean_is_dry_run,
}


def risk(subcommand: str, arguments: list[str]) -> str | None:
  """Why a git subcommand needs approval, or None when it is safe to run."""
  if subcommand not in RECORDING | DISCARDING:
    return None
  read_only = READ_ONLY_FORMS.get(subcommand)
  if read_only is not None and read_only(arguments):
    return None
  if subcommand in RECORDING:
    return f"`git {subcommand}` changes what is staged or recorded"
  return f"`git {subcommand}` can discard unreviewed work"


def command_risk(command: str, depth: int = 0) -> str | None:
  """Why a shell command needs approval, or None when it contains no risky git call."""
  if "git" in command and ("$(" in command or "`" in command):
    raise Uncertain("the command uses command substitution")
  for words in segments(command):
    words = strip_prefix(words)
    if words and words[0] in SHELLS and "-c" in words and depth < 3:
      inner = words[words.index("-c") + 1 :]
      found = command_risk(inner[0], depth + 1) if inner else None
    else:
      found = git_risk(words)
    if found:
      return found
  return None


def git_risk(words: list[str]) -> str | None:
  """Risk of one simple command, expanding git aliases."""
  parsed = git_arguments(words)
  if parsed is None:
    return None
  subcommand, arguments = parsed
  expansion = resolve_alias(subcommand)
  if expansion:
    subcommand, arguments = expansion[0], [*expansion[1:], *arguments]
  return risk(subcommand, arguments)


def ask(reason: str) -> int:
  """Print a PreToolUse "ask" decision."""
  message = f"{reason}. AGENTS.md: agents leave changes unstaged unless you asked for this."
  decision = {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": message,
  }
  print(json.dumps({"hookSpecificOutput": decision}))
  return 0


def main() -> int:
  """Ask about risky git commands; stay silent for everything else."""
  try:
    payload = json.load(sys.stdin)
  except json.JSONDecodeError:
    return 0
  tool_input = payload.get("tool_input")
  command = tool_input.get("command") if isinstance(tool_input, dict) else None
  if not isinstance(command, str) or "git" not in command:
    return 0
  os.chdir(os.environ.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or "."))
  try:
    reason = command_risk(command)
  except Uncertain as err:
    return ask(f"Could not parse this git command with confidence ({err})")
  return ask(reason) if reason else 0


if __name__ == "__main__":
  sys.exit(main())
