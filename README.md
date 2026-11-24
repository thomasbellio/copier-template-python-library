# Python Library Copier Template

A [Copier](https://copier.readthedocs.io/) template for creating production-ready Python libraries with modern tooling and best practices.

## Features

This template generates a Python library project with:

- **📦 Package Management**: Poetry for dependency management, uv for virtual environments
- **✅ Code Quality**: Ruff for linting and formatting, MyPy for type checking
- **🧪 Testing**: pytest with sensible defaults
- **🔧 Git Hooks**: Lefthook for pre-commit validation
- **🚀 CI/CD**: GitHub Actions workflows for PR checks and main branch builds
- **📝 Documentation**: Pre-configured README, CHANGELOG, and project structure
- **🎯 Source Layout**: Uses `src/` layout pattern for proper package isolation
- **⌨️ Editor Config**: EditorConfig with 2-space indentation defaults
- **🧭 Agent Harness** (optional, on by default): maintainability gates on changed code only, `AGENTS.md`, and Claude Code, lefthook and CI adapters ([details](#agent-harness))

## Prerequisites

Before using this template, ensure you have the following installed:

### Required
- **[Copier](https://copier.readthedocs.io/)** (9.0.0 or higher) - Template rendering engine
  ```bash
  uv tool install copier
  # or
  pipx install copier
  ```
- **[uv](https://github.com/astral-sh/uv)** - Fast Python package installer and environment manager
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **[Git](https://git-scm.com/)** - Version control system

### Installed by Template Tasks
The following tools are automatically installed during template generation (if using `--trust`):
- Poetry - Python dependency management
- Lefthook - Git hooks manager

## Usage

### Basic Generation (with automated setup)

Generate a new Python library project with all automated setup tasks:

```bash
copier copy --trust gh:thomasbellio/python-library-template /path/to/new-project
```

The `--trust` flag allows the template to run post-generation tasks including:
1. Virtual environment creation
2. Poetry dependency installation
3. Git repository initialization
4. Lefthook git hooks installation
5. Initial git commit

### Generation without Automated Tasks

If you prefer to run setup steps manually:

```bash
copier copy --skip-tasks gh:thomasbellio/python-library-template /path/to/new-project
```

Then manually run setup:

```bash
cd /path/to/new-project

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate     # On Windows

# Install dependencies
uv pip install poetry
poetry install

# Initialize git (use your default_branch answer) and hooks
git init -b master
lefthook install

# Create initial commit
git add .
git commit -m "Initial commit from template"
```

### Updating an Existing Project

To update a project previously generated from this template:

```bash
cd /path/to/existing-project
copier update
```

`copier update` needs the `.copier-answers.yml` file that generated projects now include.
Projects generated before it was added have no answers file; add the agent harness to those
with the retrofit checklist in the generated `docs/agent-harness.md`.

## Template Configuration

During generation, you'll be prompted for:

| Variable | Description | Default |
|----------|-------------|---------|
| `project_name` | Project name (lowercase, underscores) | - |
| `project_description` | Short project description | "A Python library" |
| `author_name` | Package author name | "" |
| `author_email` | Package author email | "" |
| `python_version` | Python version for development | "3.14.2" |
| `min_python_version` | Minimum Python version required | "3.14" |
| `default_branch` | Default git branch name | "master" |
| `github_username` | GitHub username (for CI badges) | "" |
| `enable_agent_harness` | Generate the agent harness | `true` |
| `enable_claude_adapter` | Generate `.claude/` hooks and `CLAUDE.md` (asked only with the harness) | `true` |
| `docstring_style` | Docstring style for Ruff and pydoclint: `google`, `numpy` or `sphinx` (asked only with the harness) | `google` |

If `author_name` or `author_email` is left empty, it is taken from your git config
(`user.name`, `user.email`) when the project is generated. With no name from either source,
`authors` is left out of `pyproject.toml`.

## Generated Project Structure

```
your-project/
├── .copier-answers.yml        # Answers, used by `copier update`
├── .editorconfig              # Editor configuration
├── .gitignore                 # Python-specific git ignores
├── pyproject.toml             # Poetry + tool configurations
├── README.md                  # Project documentation
├── CHANGELOG.md               # Version history
├── lefthook.yml               # Git hooks configuration
├── AGENTS.md                  # Agent instructions (harness)
├── CLAUDE.md                  # Imports AGENTS.md (Claude adapter)
├── harness.toml               # Harness thresholds (harness)
├── complexipy.toml, .pyscn.toml, .importlinter,
│   cosmic-ray.toml, vulture_whitelist.py   # Tool configs (harness)
├── .claude/                   # Claude Code hooks (Claude adapter)
├── docs/                      # agent-harness.md, troubleshooting.md, adr/ (harness)
├── .github/
│   └── workflows/
│       ├── pr.yml             # PR validation workflow
│       ├── push.yml           # Main branch build workflow
│       └── hotspots.yml       # Weekly hotspots report (harness)
├── scripts/
│   ├── build.sh               # Unified build script
│   ├── check.sh               # Harness entry point (harness)
│   ├── hotspots.sh            # Churn x complexity report (harness)
│   └── harness/               # Harness implementation (harness)
├── src/
│   └── your_project/
│       ├── __init__.py        # Package initialization
│       ├── __about__.py       # Version information
│       └── py.typed           # Type hints marker
└── tests/
    ├── __init__.py
    └── test_your_project.py   # Example tests
```

## Post-Generation Development

### Running Tests

```bash
pytest
```

### Code Quality Checks

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type check
mypy src/your_project
```

### Run All Checks (same as CI)

```bash
./scripts/build.sh
```

### Git Hooks

The template includes Lefthook for pre-commit validation. All commits automatically run:
- Linting (ruff check)
- Formatting checks (ruff format --check)
- Type checking (mypy)
- Unit tests (pytest)
- Agent harness checks on changed code (`scripts/check.sh`, when the harness is enabled)

With the harness, a `pre-push` hook runs `scripts/check.sh` again, so commits made with
`--no-verify` are still checked before they leave your machine.

To bypass hooks temporarily:
```bash
git commit --no-verify -m "message"
```

## Agent Harness

With `enable_agent_harness` (the default), generated projects get maintainability checks that
run **only on new and changed code**, measured from the merge-base with the default branch.
Agents and people fix the functions and classes they touch, and are never pushed into
codebase-wide refactors.

- **Checks:** cognitive and cyclomatic complexity, size limits, exception hygiene, docstring
  presence and consistency, strict typing, suppression policy, dead code, import contracts and
  cycles, class coupling and cohesion, clone advisories and a changelog reminder; mutation
  testing on changed lines in CI; a weekly churn × complexity report.
- **One entry point:** `scripts/check.sh` (exit 0 pass, 1 fail, 3 harness error). `build.sh`,
  lefthook (pre-commit and pre-push), CI and the Claude Code hooks all call it.
- **`AGENTS.md`** is the canonical guide for any coding agent; `CLAUDE.md` imports it.
- **Claude Code adapter:** hooks check each edit, gate the end of a turn with one forced
  retry, and ask you before an agent edits harness configuration or runs git commands that
  stage, commit or discard work.

The generated `docs/agent-harness.md` describes every check and threshold, how to add another
agent, and a checklist for retrofitting the harness into an existing repository. Its source is
`{% if enable_agent_harness %}docs{% endif %}/agent-harness.md.jinja` in this repository.

## GitHub Actions Workflows

### Pull Request Workflow (`pr.yml`)
Triggers on all PRs to the default branch and runs:
- Linting and formatting checks
- Type checking
- Unit tests

With the harness it also fetches full history, runs the harness against the PR's merge-base,
notes changes to harness configuration and a cognitive complexity diff in the job summary, and
runs mutation testing on changed lines as a separate, non-required job. A weekly
`hotspots.yml` workflow publishes a churn × complexity report.

### Push Workflow (`push.yml`)
Triggers on pushes to the default branch and runs:
- All PR checks
- Package build (`poetry build`)

## Customization

### Modify Template Defaults

Edit `copier.yml` to change default values or add new configuration options.

### Customize Generated Files

Template files use Jinja2 syntax and end with `.jinja`:
- `pyproject.toml.jinja` - Modify dependencies or tool configurations
- `README.md.jinja` - Adjust project documentation template
- `.github/workflows/*.yml.jinja` - Customize CI/CD pipelines

### Skip Specific Files

Add paths to `_skip_if_exists` in `copier.yml` to preserve files during updates.

## Testing the Template

`template-tests/smoke.sh` generates a project from your working copy (uncommitted changes
included) into a temporary directory and runs the harness scenarios against it: every gate,
the scope model, the Claude Code hooks, lefthook pre-push, the CI notice, mutation testing,
hotspots and `copier update`.

```bash
template-tests/smoke.sh               # all scenarios
template-tests/smoke.sh 2 11 12       # selected scenarios
SMOKE_WORK_DIR=/tmp/smoke SMOKE_REUSE=1 template-tests/smoke.sh 5   # reuse a generated project
```

It needs `copier`, `uv` and network access for the first dependency install. `briefs/` and
`template-tests/` are excluded from generated projects.

## Contributing

Contributions to improve this template are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run `template-tests/smoke.sh`
5. Submit a pull request

## License

This code is licensed under [The Modified Anti-Dick 3-Clause BSD 2 License](https://gist.github.com/thomasbellio/99a998d391ad4cd1bf350845627e956c)

## Acknowledgments

Built with:
- [Copier](https://copier.readthedocs.io/) - Template engine
- [uv](https://github.com/astral-sh/uv) - Python package installer
- [Poetry](https://python-poetry.org/) - Dependency management
- [Ruff](https://github.com/astral-sh/ruff) - Fast Python linter
- [MyPy](http://mypy-lang.org/) - Static type checker
- [pytest](https://pytest.org/) - Testing framework
- [Lefthook](https://github.com/evilmartians/lefthook) - Git hooks manager
