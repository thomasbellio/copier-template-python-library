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

# Initialize git and hooks
git init
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

## Generated Project Structure

```
your-project/
├── .editorconfig              # Editor configuration
├── .gitignore                 # Python-specific git ignores
├── pyproject.toml             # Poetry + tool configurations
├── README.md                  # Project documentation
├── CHANGELOG.md               # Version history
├── lefthook.yml               # Git hooks configuration
├── .github/
│   └── workflows/
│       ├── pr.yml             # PR validation workflow
│       └── push.yml           # Main branch build workflow
├── scripts/
│   └── build.sh               # Unified build script
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

To bypass hooks temporarily:
```bash
git commit --no-verify -m "message"
```

## GitHub Actions Workflows

### Pull Request Workflow (`pr.yml`)
Triggers on all PRs to the default branch and runs:
- Linting and formatting checks
- Type checking
- Unit tests

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

## Contributing

Contributions to improve this template are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test the template generation
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
