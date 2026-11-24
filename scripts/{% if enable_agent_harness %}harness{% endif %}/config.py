"""Load and validate harness settings from harness.toml."""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from harness.errors import HarnessError

CONFIG_FILE = "harness.toml"


@dataclass(frozen=True)
class Config:
  """Typed view over harness.toml, one TOML table per section."""

  data: Mapping[str, object]

  def section(self, name: str) -> Mapping[str, object]:
    """Return a table from the config, or an empty mapping when absent."""
    value = self.data.get(name, {})
    if not isinstance(value, Mapping):
      raise HarnessError(f"{CONFIG_FILE}: [{name}] must be a table")
    return value

  def value(self, section: str, key: str, default: object = None) -> object:
    """Return a raw value, or the default when it is not set."""
    return self.section(section).get(key, default)

  def string(self, section: str, key: str, default: str = "") -> str:
    """Return a string setting."""
    value = self.value(section, key, default)
    if not isinstance(value, str):
      raise HarnessError(f"{CONFIG_FILE}: {section}.{key} must be a string")
    return value

  def integer(self, section: str, key: str, default: int) -> int:
    """Return an integer setting."""
    value = self.value(section, key, default)
    if not isinstance(value, int) or isinstance(value, bool):
      raise HarnessError(f"{CONFIG_FILE}: {section}.{key} must be an integer")
    return value

  def number(self, section: str, key: str, default: float) -> float:
    """Return a numeric setting as a float."""
    value = self.value(section, key, default)
    if not isinstance(value, int | float) or isinstance(value, bool):
      raise HarnessError(f"{CONFIG_FILE}: {section}.{key} must be a number")
    return float(value)

  def strings(self, section: str, key: str) -> tuple[str, ...]:
    """Return a list-of-strings setting."""
    value = self.value(section, key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
      raise HarnessError(f"{CONFIG_FILE}: {section}.{key} must be a list of strings")
    return tuple(str(item) for item in value)

  @property
  def default_branch(self) -> str:
    """Branch whose merge-base defines the changed set."""
    return self.string("harness", "default_branch", "master")

  @property
  def package(self) -> str:
    """Import name of the project's package under src/."""
    return self.string("harness", "package")

  @property
  def scope_dirs(self) -> tuple[str, ...]:
    """Directories whose Python files the harness checks."""
    return self.strings("harness", "scope_dirs") or ("src", "tests")

  @property
  def max_findings(self) -> int:
    """Cap on findings printed in the text report."""
    return self.integer("harness", "max_findings", 40)


def load_config(root: Path) -> Config:
  """Read harness.toml from the repository root."""
  path = root / CONFIG_FILE
  try:
    with path.open("rb") as handle:
      return Config(tomllib.load(handle))
  except FileNotFoundError as err:
    raise HarnessError(f"{CONFIG_FILE} not found at {root}") from err
  except tomllib.TOMLDecodeError as err:
    raise HarnessError(f"{CONFIG_FILE} is not valid TOML: {err}") from err
