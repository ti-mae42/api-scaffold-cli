# api-scaffold-cli

`api-scaffold-cli` is an installable Python command line tool that generates a new Flask API project from the `base-api` template repository.

It clones the template into a new project directory, removes the cloned `.git` metadata, renames the template identity to your requested project name, and enables or removes optional template features such as PostgreSQL, Celery, and AWS.

## Requirements

- Python 3.10 or newer.
- Git available on `PATH`.
- Network access when cloning from GitHub.
- Access to the base API repository. By default this is `https://github.com/ti-mae42/python-flask-base-api`.

## Installation From Local Source

From this repository:

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e .
```

## Installation From GitHub

Install directly from a GitHub repository URL:

```bash
python -m pip install "git+https://github.com/ti-mae42/api-scaffold-cli.git"
```

For editable development from GitHub:

```bash
git clone https://github.com/ti-mae42/api-scaffold-cli.git
cd api-scaffold-cli
python -m pip install -e .
```

## Basic Usage

Generate a project without database support:

```bash
api-scaffold new my-api --database=none
```

Generate a project with PostgreSQL support:

```bash
api-scaffold new my-api --database=postgresql
```

Generate a project with MySQL support:

```bash
api-scaffold new my-api --database=mysql
```

Generate a project with PostgreSQL and Celery:

```bash
api-scaffold new my-api --database=postgresql --with-celery
```

Generate a project with PostgreSQL, AWS, and Celery:

```bash
api-scaffold new my-api --database=postgresql --with-cloud=aws --with-celery
```

Use a custom template repository and output directory:

```bash
api-scaffold new my-api \
  --base-repo-url=/path/to/local/base-api \
  --output-dir=./generated
```

The generated project path is `OUTPUT_DIR/PROJECT_NAME`. The command fails if that target directory already exists and is not empty.

## Options

- `PROJECT_NAME`: Required. The generated project directory and distribution name. Use letters, numbers, hyphens, or underscores, starting with a letter or number. Hyphens are allowed.
- `--database`: Optional. Accepted values are `none`, `postgresql`, and `mysql`. Defaults to `none`.
- `--with-celery`: Optional flag. Keeps Celery worker support when present. If omitted, Celery-specific code is removed.
- `--with-cloud`: Optional. Currently supports `aws`. If omitted, AWS-specific code is removed. Unsupported values are treated as cloud disabled and reported as warnings.
- `--base-repo-url`: Optional. Git URL or local git repository path for the template. Defaults to the `BASE_REPO_URL` value in this project’s `.env`.
- `--output-dir`: Optional. Directory where the generated project directory is created. Defaults to the current directory.

`--with-aws` is still accepted as a deprecated alias for `--with-cloud=aws`.

## Transformations

The scaffold applies these transformations after cloning:

- Removes the cloned template `.git` directory.
- Renames template identity strings:
  - `Base API` becomes a display name derived from `PROJECT_NAME`, such as `My API`.
  - `base_api` becomes a safe Python package name, such as `my`. A trailing `api` segment is omitted from the package name.
  - `base-api` becomes the requested project name, such as `my-api`.
  - `BASE_API` becomes an uppercase env/config prefix, such as `MY`.
- Renames files and directories that include `base_api` or `base-api`.
- Skips binary files and cache/build/virtualenv directories.
- Uses `TEMPLATE_FEATURES.md` from the cloned template as guidance for optional feature cleanup.
- Removes or keeps database files, dependencies, migrations, environment variables, and startup setup based on `--database`.
- For PostgreSQL, keeps the PostgreSQL driver and writes a `postgresql+psycopg2://` sample `DATABASE_URL`.
- For MySQL, keeps the MySQL driver and writes a `mysql+pymysql://` sample `DATABASE_URL`.
- Removes or keeps Celery worker files, dependencies, environment variables, startup setup, and worker docs based on `--with-celery`.
- Removes or keeps AWS adapter files, dependencies, environment variables, and AWS-only docs/config based on `--with-cloud=aws`.
- Preserves generic infrastructure folders and Flask bootstrap files such as `initialize.py`; only clearly optional feature code is removed.
- Prints transformation, database, Celery, and cloud logs, including warnings when a cleanup cannot be performed safely.

## Generated Project Checklist

After generating a project:

```bash
cd my-api
cp .env.sample .env
python -m pip install -e .
pytest
flask --app my.initialize:web_app run
```

If PostgreSQL or MySQL is enabled, configure `DATABASE_URL` in `.env`, then run migrations with Flask-Migrate:

```bash
flask --app my.initialize:web_app db upgrade
```

If Celery is enabled, configure the worker broker variables such as `REDIS_URL`, then start the worker:

```bash
celery -A my.initialize:celery_app worker
```

## Known Limitations

- Only the `base-api` template shape is currently supported.
- Cloud support is AWS-only for now.
- Optional feature cleanup depends on `TEMPLATE_FEATURES.md` and optional marker comments in the template.
- The tool avoids unsafe edits. If a file cannot be safely removed or edited, it is kept and a warning is printed.
- Dependency cleanup is line-based for `pyproject.toml` and requirements files. Complex dependency declarations may require manual review.
- The generated project is not automatically committed to git.
- The scaffold does not install generated project dependencies or run generated project tests automatically.

## Troubleshooting

`git clone` fails:

- Confirm Git is installed and available on `PATH`.
- Confirm `--base-repo-url` is reachable.
- For private repositories, confirm your SSH key or Git credentials work outside the scaffold command.

Target directory already exists:

- The command refuses to write into an existing non-empty target directory.
- Choose a different `PROJECT_NAME`, set a different `--output-dir`, or clear the existing directory yourself.

Invalid project name:

- Use only letters, numbers, hyphens, or underscores.
- Start the name with a letter or number.

Feature files were not removed:

- Check the scaffold log warnings.
- Confirm the cloned template contains `TEMPLATE_FEATURES.md`.
- Confirm optional feature blocks are marked in the template, for example `BASE_API_OPTIONAL: database`, `BASE_API_OPTIONAL: celery`, or `BASE_API_OPTIONAL: aws`.

Generated imports fail:

- Check whether an optional feature was disabled while application code still imports that feature.
- Review files listed in scaffold warnings.
- Re-run generation with the feature enabled if the project needs it.

System Python refuses installation:

- Some Linux distributions protect system Python environments.
- Use a virtual environment, `pipx`, or an editable install inside a project-specific environment.

## Tests

Run the CLI test suite:

```bash
python -m unittest discover
```
