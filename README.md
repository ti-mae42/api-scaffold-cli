# api-scaffold-cli

Installable command line tool for generating a new API project from a base API repository.

The current implementation clones a base API repository into a new project directory, removes the cloned `.git` directory, and renames the template identity to match the requested project name.

## Installation

Install locally from this directory:

```bash
python -m pip install .
```

For development, install in editable mode:

```bash
python -m pip install -e .
```

## Usage

Create a new project using default options:

```bash
api-scaffold new new-project-api
```

Create a PostgreSQL project with Celery and AWS options enabled:

```bash
api-scaffold new new-project-api --database=postgresql --with-celery --with-aws
```

Use a custom base repository and output directory:

```bash
api-scaffold new new-project-api \
  --base-repo-url=https://github.com/ti-mae42/python-flask-base-api \
  --output-dir=./generated
```

Clone from a local git repository, useful for testing:

```bash
api-scaffold new new-project-api \
  --base-repo-url=/path/to/local/base-api \
  --output-dir=./generated
```

The generated project path will be `OUTPUT_DIR/PROJECT_NAME`. The command fails if that target directory already exists and is not empty.

After cloning, the command replaces template names such as `Base API`, `base_api`, `base-api`, and `BASE_API` with values derived from `PROJECT_NAME`.

Example:

- Project name: `new-project-api`
- Python package: `new_project_api`
- Display name: `New Project API`

## Options

- `PROJECT_NAME`: Required project name. Use letters, numbers, hyphens, or underscores, starting with a letter or number.
- `--database`: Database backend. Accepted values are `none` and `postgresql`. Defaults to `none`.
- `--with-celery`: Enable Celery-related generation flags. Defaults to disabled.
- `--with-aws`: Enable AWS-related generation flags. Defaults to disabled.
- `--base-repo-url`: Base API repository URL or local git repository path. Defaults to the `BASE_REPO_URL` value in `.env`.
- `--output-dir`: Directory where the project will be generated. Defaults to the current directory.

## Configuration

The default base repository is configured in `.env`:

```env
BASE_REPO_URL=https://github.com/ti-mae42/python-flask-base-api
```

## Database Mode

`--database=postgresql` keeps database-related files, PostgreSQL dependencies, environment variables, and Alembic/migration setup when present. It also adds PostgreSQL setup notes to the generated README.

`--database=none` removes database-specific files listed by the cloned template's `TEMPLATE_FEATURES.md`, removes marked optional database startup blocks, cleans common database dependencies and env example variables, and adds a README note that the project was generated without database support. Flask bootstrap files such as `initialize.py` are preserved even if listed in `TEMPLATE_FEATURES.md`; only their marked database setup blocks are removed.

If a database file or startup block cannot be removed safely, the CLI leaves it in place and prints a warning in the database log.

## Celery Mode

`--with-celery` keeps Celery worker files, Celery and Redis dependencies, worker environment variables, and worker startup documentation when present. It also adds generated README notes for starting a worker.

When `--with-celery` is omitted, the scaffold removes Celery-specific files listed by `TEMPLATE_FEATURES.md`, removes marked optional Celery setup from files such as `initialize.py`, removes Celery-specific worker imports, cleans Celery dependencies and env example variables, removes Celery worker commands from docs/scripts when they are clearly Celery-specific, and adds a README note that the project was generated without Celery support.

Generic worker or async settings are preserved unless they clearly reference Celery.

## Tests

```bash
python -m unittest discover
```
