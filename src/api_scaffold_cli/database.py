from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_DATABASES = ("none", "postgresql", "mysql")
TEMPLATE_FEATURES_FILE = "TEMPLATE_FEATURES.md"
DB_DEPENDENCY_NAMES = {
    "alembic",
    "asyncpg",
    "flask-migrate",
    "flask-sqlalchemy",
    "mysql-connector-python",
    "mysqlclient",
    "psycopg",
    "psycopg2",
    "psycopg2-binary",
    "pymysql",
    "sqlalchemy",
    "sqlalchemy-utils",
}
DATABASE_DRIVER_DEPENDENCIES = {
    "postgresql": {"asyncpg", "psycopg", "psycopg2", "psycopg2-binary"},
    "mysql": {"mysql-connector-python", "mysqlclient", "pymysql"},
}
DATABASE_URLS = {
    "postgresql": "postgresql+psycopg2://user:pass@host/dbname",
    "mysql": "mysql+pymysql://user:pass@host/dbname",
}
ENV_FILE_NAMES = {".env", ".env.example", ".env.sample", "env.example"}
ENV_KEY_PATTERNS = ("DATABASE", "MYSQL", "POSTGRES", "POSTGRESQL", "SQLALCHEMY")
DATABASE_BLOCK_START = "# api-scaffold: database start"
DATABASE_BLOCK_END = "# api-scaffold: database end"
PROTECTED_STARTUP_FILE_NAMES = {"app.py", "application.py", "factory.py", "initialize.py", "main.py"}
OPTIONAL_FEATURE_PATTERN = re.compile(r"^\s*#\s*[A-Z0-9_]+_OPTIONAL:\s*(postgresql|mysql|database)\b", re.IGNORECASE)
DATABASE_TEXT_PATTERNS = (
    "database",
    "mysql",
    "pymysql",
    "postgres",
    "postgresql",
    "sqlalchemy",
    "migration",
    "migrate",
    "alembic",
    "psycopg",
    "orm",
)
SKIPPED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "build",
    "dist",
    "node_modules",
}
SKIPPED_DIRECTORY_SUFFIXES = (".egg-info",)


@dataclass
class TemplateFeatureGuidance:
    database_paths: list[str] = field(default_factory=list)
    startup_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DatabaseLog:
    database: str
    removed_paths: list[str] = field(default_factory=list)
    updated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def apply_database_option(project_dir: Path, database: str) -> DatabaseLog:
    log = DatabaseLog(database=database)
    guidance = load_template_feature_guidance(project_dir)
    log.warnings.extend(guidance.warnings)

    if database in ("postgresql", "mysql"):
        _apply_database_backend_selection(project_dir, database, log)
        database_name = "PostgreSQL" if database == "postgresql" else "MySQL"
        database_url = DATABASE_URLS[database]
        package_name = _derive_package_name(project_dir)
        _append_readme_database_section(
            project_dir,
            "Database",
            [
                f"This project was generated with {database_name} database support.",
                "",
                "Configure the database connection:",
                "",
                "```sh",
                "cp .env.example .env",
                f"# Edit .env and set DATABASE_URL={database_url}",
                "```",
                "",
                "Before creating migrations, import your repository model modules in",
                f"`{package_name}/infrastructure/database.py` inside `register_migration` so",
                "Flask-Migrate can discover the SQLAlchemy metadata:",
                "",
                "```python",
                "def register_migration(web_app):",
                "    # Update the line below for the migrate command to work.",
                f"    # from {package_name}.repositories import your_repositories_module  # noqa: F401",
                "    return Migrate(web_app, orm)",
                "```",
                "",
                "Run existing migrations before starting the API:",
                "",
                "```sh",
                f"flask --app {package_name}.initialize:web_app db upgrade",
                "```",
                "",
                "Create and apply a new migration after changing models:",
                "",
                "```sh",
                f'flask --app {package_name}.initialize:web_app db migrate -m "describe change"',
                f"flask --app {package_name}.initialize:web_app db upgrade",
                "```",
            ],
            log,
        )
        return log

    if database != "none":
        log.warnings.append(f"Unsupported database option '{database}' was ignored.")
        return log

    for relative_path in guidance.database_paths:
        _remove_guided_path(project_dir, relative_path, log)

    for relative_path in guidance.startup_files:
        _remove_database_blocks(project_dir, relative_path, log)

    _remove_all_database_optional_markers(project_dir, log)
    _remove_database_import_references(project_dir, log)
    _remove_database_dependencies(project_dir, log)
    _remove_database_env_vars(project_dir, log)
    return log


def _derive_package_name(project_dir: Path) -> str:
    return project_dir.name.replace("-", "_").lower()


def _apply_database_backend_selection(project_dir: Path, database: str, log: DatabaseLog) -> None:
    for other_database in DATABASE_DRIVER_DEPENDENCIES:
        if other_database == database:
            continue
        _remove_database_optional_markers(project_dir, other_database, log)

    _remove_unselected_database_driver_dependencies(project_dir, database, log)
    _rewrite_database_urls(project_dir, database, log)


def load_template_feature_guidance(project_dir: Path) -> TemplateFeatureGuidance:
    features_path = project_dir / TEMPLATE_FEATURES_FILE
    guidance = TemplateFeatureGuidance()
    if not features_path.is_file():
        guidance.warnings.append(f"{TEMPLATE_FEATURES_FILE} not found; no database files were removed by guidance.")
        return guidance

    in_database_section = False
    in_when_disabled = False
    fallback_database_paths: list[str] = []
    current_group = "database_paths"
    for raw_line in features_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        lowered = line.lower()

        if lowered.startswith("## "):
            in_database_section = "database" in lowered
            in_when_disabled = False
            current_group = "database_paths"
            continue

        if not in_database_section:
            continue

        if lowered.endswith(":"):
            in_when_disabled = lowered == "when disabled:"

        if "startup" in lowered or "initialization" in lowered:
            current_group = "startup_files"
            continue

        if "file" in lowered or "path" in lowered or "remove" in lowered:
            current_group = "database_paths"

        path = _extract_guidance_path(line)
        if not path:
            continue

        if _is_protected_startup_file(path):
            _append_unique(guidance.startup_files, path)
            continue

        if in_when_disabled and lowered.startswith("- remove") and _is_safe_database_removal_path(path):
            _append_unique(guidance.database_paths, path)
        elif current_group == "startup_files":
            _append_unique(guidance.startup_files, path)
        else:
            _append_unique(fallback_database_paths, path)

    for path in fallback_database_paths:
        if _is_safe_database_removal_path(path):
            _append_unique(guidance.database_paths, path)

    return guidance


def _extract_guidance_path(line: str) -> str | None:
    backtick_match = re.search(r"`([^`]+)`", line)
    if backtick_match:
        return backtick_match.group(1).strip().strip("/")

    bullet_match = re.match(r"^[-*]\s+(.+)$", line)
    if not bullet_match:
        return None

    value = bullet_match.group(1).strip().strip("/")
    if not value or " " in value:
        return None

    return value


def _remove_guided_path(project_dir: Path, relative_path: str, log: DatabaseLog) -> None:
    target = project_dir / relative_path
    if not target.exists():
        log.warnings.append(f"Database path listed in {TEMPLATE_FEATURES_FILE} was not found: {relative_path}")
        return

    if not target.resolve().is_relative_to(project_dir.resolve()):
        log.warnings.append(f"Refused to remove path outside generated project: {relative_path}")
        return

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    log.removed_paths.append(relative_path)


def _remove_database_blocks(project_dir: Path, relative_path: str, log: DatabaseLog) -> None:
    target = project_dir / relative_path
    if not target.is_file():
        log.warnings.append(f"Database startup file was not found: {relative_path}")
        return

    content = target.read_text(encoding="utf-8")
    updated, removed_block_count = _remove_marked_blocks(content)
    if removed_block_count == 0:
        log.warnings.append(
            f"No optional database startup markers found in {relative_path}; left startup code unchanged."
        )
        return

    target.write_text(updated, encoding="utf-8")
    _record_updated_file(log, relative_path)


def _remove_marked_blocks(content: str) -> tuple[str, int]:
    output_lines: list[str] = []
    removing = False
    removed_block_count = 0

    for line in content.splitlines(keepends=True):
        if DATABASE_BLOCK_START in line:
            removing = True
            removed_block_count += 1
            continue

        if DATABASE_BLOCK_END in line and removing:
            removing = False
            continue

        if not removing:
            output_lines.append(line)

    return "".join(output_lines), removed_block_count


def _remove_all_database_optional_markers(project_dir: Path, log: DatabaseLog) -> None:
    for path in _iter_candidate_text_files(project_dir):
        content = path.read_text(encoding="utf-8")
        updated, removed_count = _remove_database_optional_lines(content)
        if removed_count == 0:
            continue

        path.write_text(updated, encoding="utf-8")
        _record_updated_file(log, str(path.relative_to(project_dir)))


def _remove_database_optional_markers(project_dir: Path, database: str, log: DatabaseLog) -> None:
    pattern = re.compile(rf"^\s*#\s*[A-Z0-9_]+_OPTIONAL:\s*{re.escape(database)}\b", re.IGNORECASE)
    for path in _iter_candidate_text_files(project_dir):
        content = path.read_text(encoding="utf-8")
        updated, removed_count = _remove_database_optional_lines(content, marker_pattern=pattern)
        if removed_count == 0:
            continue

        path.write_text(updated, encoding="utf-8")
        _record_updated_file(log, str(path.relative_to(project_dir)))


def _remove_database_optional_lines(
    content: str,
    *,
    marker_pattern: re.Pattern[str] = OPTIONAL_FEATURE_PATTERN,
) -> tuple[str, int]:
    lines = content.splitlines(keepends=True)
    output_lines: list[str] = []
    removed_count = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        if not marker_pattern.match(line):
            output_lines.append(line)
            index += 1
            continue

        removed_count += 1
        marker_indent = _line_indent(line)
        index += 1

        while index < len(lines):
            next_line = lines[index]
            if OPTIONAL_FEATURE_PATTERN.match(next_line):
                break

            if not next_line.strip():
                output_lines.append(next_line)
                index += 1
                break

            if _line_indent(next_line) < marker_indent:
                break

            if not _line_looks_database_specific(next_line):
                break

            removed_count += 1
            index += 1

    return "".join(output_lines), removed_count


def _remove_database_import_references(project_dir: Path, log: DatabaseLog) -> None:
    for path in _iter_candidate_text_files(project_dir):
        if path.suffix != ".py":
            continue

        original = path.read_text(encoding="utf-8")
        updated = _remove_database_from_python_imports(original)
        if updated == original:
            continue

        path.write_text(updated, encoding="utf-8")
        _record_updated_file(log, str(path.relative_to(project_dir)))


def _remove_database_from_python_imports(content: str) -> str:
    output_lines: list[str] = []
    for line in content.splitlines(keepends=True):
        if " import " not in line or "database" not in line:
            output_lines.append(line)
            continue

        prefix, imported_names = line.split(" import ", 1)
        line_ending = "\n" if imported_names.endswith("\n") else ""
        imported_names = imported_names.rstrip("\n")
        names = [name.strip() for name in imported_names.split(",")]
        if "database" not in names:
            output_lines.append(line)
            continue

        remaining_names = [name for name in names if name != "database"]
        if not remaining_names:
            continue

        output_lines.append(f"{prefix} import {', '.join(remaining_names)}{line_ending}")

    return "".join(output_lines)


def _remove_database_dependencies(project_dir: Path, log: DatabaseLog) -> None:
    for path in project_dir.iterdir():
        if path.name == "pyproject.toml" or path.name.startswith("requirements"):
            _remove_database_dependency_lines(project_dir, path, log)


def _remove_database_dependency_lines(project_dir: Path, path: Path, log: DatabaseLog) -> None:
    original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines: list[str] = []

    for line in original_lines:
        if _is_database_dependency_line(line):
            continue
        updated_lines.append(line)

    if updated_lines == original_lines:
        return

    path.write_text("".join(updated_lines), encoding="utf-8")
    _record_updated_file(log, str(path.relative_to(project_dir)))


def _is_database_dependency_line(line: str) -> bool:
    stripped = line.strip().strip(",").strip("'\"")
    if not stripped or stripped.startswith("#"):
        return False

    match = re.match(r"^([A-Za-z0-9_.-]+)", stripped)
    if not match:
        return False

    return match.group(1).lower() in DB_DEPENDENCY_NAMES


def _remove_unselected_database_driver_dependencies(project_dir: Path, database: str, log: DatabaseLog) -> None:
    dependencies_to_remove = set[str]()
    for driver_database, dependency_names in DATABASE_DRIVER_DEPENDENCIES.items():
        if driver_database != database:
            dependencies_to_remove.update(dependency_names)

    for path in project_dir.iterdir():
        if path.name == "pyproject.toml" or path.name.startswith("requirements"):
            _remove_named_dependency_lines(project_dir, path, dependencies_to_remove, log)


def _remove_named_dependency_lines(
    project_dir: Path,
    path: Path,
    dependency_names: set[str],
    log: DatabaseLog,
) -> None:
    original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines: list[str] = []

    for line in original_lines:
        stripped = line.strip().strip(",").strip("'\"")
        match = re.match(r"^([A-Za-z0-9_.-]+)", stripped)
        if match and match.group(1).lower() in dependency_names:
            continue
        updated_lines.append(line)

    if updated_lines == original_lines:
        return

    path.write_text("".join(updated_lines), encoding="utf-8")
    _record_updated_file(log, str(path.relative_to(project_dir)))


def _rewrite_database_urls(project_dir: Path, database: str, log: DatabaseLog) -> None:
    database_url = DATABASE_URLS[database]
    for path in project_dir.iterdir():
        if path.name in ENV_FILE_NAMES or path.name.endswith(".env.example"):
            _rewrite_database_url_file(project_dir, path, database_url, log)


def _rewrite_database_url_file(project_dir: Path, path: Path, database_url: str, log: DatabaseLog) -> None:
    original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines: list[str] = []

    for line in original_lines:
        if line.strip().startswith("DATABASE_URL="):
            line_ending = "\n" if line.endswith("\n") else ""
            updated_lines.append(f"DATABASE_URL={database_url}{line_ending}")
            continue
        updated_lines.append(line)

    if updated_lines == original_lines:
        return

    path.write_text("".join(updated_lines), encoding="utf-8")
    _record_updated_file(log, str(path.relative_to(project_dir)))


def _remove_database_env_vars(project_dir: Path, log: DatabaseLog) -> None:
    for path in project_dir.iterdir():
        if path.name in ENV_FILE_NAMES or path.name.endswith(".env.example"):
            _remove_database_env_lines(project_dir, path, log)


def _remove_database_env_lines(project_dir: Path, path: Path, log: DatabaseLog) -> None:
    original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines = [line for line in original_lines if not _is_database_env_line(line)]

    if updated_lines == original_lines:
        return

    path.write_text("".join(updated_lines), encoding="utf-8")
    _record_updated_file(log, str(path.relative_to(project_dir)))


def _is_database_env_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return False

    key = stripped.split("=", 1)[0].upper()
    return any(pattern in key for pattern in ENV_KEY_PATTERNS)


def _append_readme_database_section(
    project_dir: Path,
    heading: str,
    lines: list[str],
    log: DatabaseLog,
) -> None:
    readme_path = project_dir / "README.md"
    if not readme_path.is_file():
        log.warnings.append("README.md was not found; database usage notes were not written.")
        return

    section_lines = ["", f"## {heading}", "", *lines, ""]
    content = readme_path.read_text(encoding="utf-8").rstrip()
    if "## Database" in content or "## PostgreSQL" in content:
        log.warnings.append("README already contains database documentation; appended generated database notes.")

    readme_path.write_text(f"{content}\n{chr(10).join(section_lines)}", encoding="utf-8")
    _record_updated_file(log, str(readme_path.relative_to(project_dir)))


def _record_updated_file(log: DatabaseLog, relative_path: str) -> None:
    if relative_path not in log.updated_files:
        log.updated_files.append(relative_path)


def _is_protected_startup_file(relative_path: str) -> bool:
    return Path(relative_path).name in PROTECTED_STARTUP_FILE_NAMES


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _is_safe_database_removal_path(relative_path: str) -> bool:
    path = Path(relative_path)
    if _is_protected_startup_file(relative_path):
        return False

    if path.name in {"config.py", "pyproject.toml", ".env", ".env.example", ".env.sample", "env.example"}:
        return False

    return (
        path.name == "db.py"
        or "database" in path.name
        or "migration" in path.parts
        or "migrations" in path.parts
        or "repositories" in path.parts
        or path.name in {"alembic.ini", "env.py", "script.py.mako"}
    )


def _iter_candidate_text_files(project_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in project_dir.rglob("*"):
        if _is_in_skipped_directory(project_dir, path) or not path.is_file():
            continue

        content = path.read_bytes()
        if b"\0" in content:
            continue

        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            continue

        files.append(path)

    return files


def _is_in_skipped_directory(project_dir: Path, path: Path) -> bool:
    relative_parts = path.relative_to(project_dir).parts
    directories = relative_parts if path.is_dir() else relative_parts[:-1]
    return any(_should_skip_directory_name(part) for part in directories)


def _should_skip_directory_name(name: str) -> bool:
    return name in SKIPPED_DIRECTORY_NAMES or name.endswith(SKIPPED_DIRECTORY_SUFFIXES)


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _line_looks_database_specific(line: str) -> bool:
    lowered = line.lower()
    return (
        any(pattern in lowered for pattern in DATABASE_TEXT_PATTERNS)
        or bool(re.search(r"(\.|\b)db\b", lowered))
        or _is_database_dependency_line(line)
    )
