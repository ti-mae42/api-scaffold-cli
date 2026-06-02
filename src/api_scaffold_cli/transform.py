from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


TEMPLATE_DISPLAY_NAME = "Base API"
TEMPLATE_PACKAGE_NAME = "base_api"
TEMPLATE_PROJECT_NAME = "base-api"
TEMPLATE_ENV_NAME = "BASE_API"
TEMPLATE_README_DESCRIPTION = """Reusable Flask API template for starting RESTful JSON service projects. It
provides a small generic shell with Flask-RESTful routing, camelCase JSON
request/response helpers, configuration loading, security primitives,
SQLAlchemy and Alembic foundation, optional Celery worker setup, and optional
AWS adapters.

The template is intentionally business-domain free. New projects should add
their own domain modules, repositories, resources, schemas, validators, and
migrations after the scaffold step."""
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
COMMON_INITIALISMS = {"api", "aws", "cli", "db", "http", "https", "id", "json", "sql", "url"}


@dataclass(frozen=True)
class ProjectNames:
    project_name: str
    package_name: str
    display_name: str


@dataclass
class TransformationLog:
    file_updates: list[str] = field(default_factory=list)
    path_renames: list[str] = field(default_factory=list)
    skipped_binary_files: list[str] = field(default_factory=list)

    @property
    def changed_file_count(self) -> int:
        return len(self.file_updates)

    @property
    def renamed_path_count(self) -> int:
        return len(self.path_renames)


def derive_project_names(project_name: str) -> ProjectNames:
    parts = [part for part in project_name.replace("_", "-").split("-") if part]
    package_name = project_name.replace("-", "_").lower()
    display_name = " ".join(_display_word(part) for part in parts)
    return ProjectNames(
        project_name=project_name,
        package_name=package_name,
        display_name=display_name,
    )


def transform_project_identity(project_dir: Path, project_name: str) -> TransformationLog:
    names = derive_project_names(project_name)
    log = TransformationLog()

    for path in _iter_candidate_files(project_dir):
        _replace_template_identity_in_file(project_dir, path, names, log)

    _rename_template_identity_paths(project_dir, names, log)
    return log


def _display_word(value: str) -> str:
    lowered = value.lower()
    if lowered in COMMON_INITIALISMS:
        return lowered.upper()

    return lowered.capitalize()


def _iter_candidate_files(project_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in project_dir.rglob("*"):
        if _is_in_skipped_directory(project_dir, path):
            continue

        if path.is_file():
            files.append(path)

    return files


def _replace_template_identity_in_file(
    project_dir: Path,
    path: Path,
    names: ProjectNames,
    log: TransformationLog,
) -> None:
    content_bytes = path.read_bytes()
    if b"\0" in content_bytes:
        log.skipped_binary_files.append(str(path.relative_to(project_dir)))
        return

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        log.skipped_binary_files.append(str(path.relative_to(project_dir)))
        return

    updated = content
    updated = updated.replace(TEMPLATE_DISPLAY_NAME, names.display_name)
    updated = updated.replace(TEMPLATE_PACKAGE_NAME, names.package_name)
    updated = updated.replace(TEMPLATE_PROJECT_NAME, names.project_name)
    updated = updated.replace(TEMPLATE_ENV_NAME, names.package_name.upper())
    if path.name == "README.md":
        updated = _replace_readme_template_description(updated, names)

    if updated == content:
        return

    path.write_text(updated, encoding="utf-8")
    log.file_updates.append(str(path.relative_to(project_dir)))


def _replace_readme_template_description(content: str, names: ProjectNames) -> str:
    replacement = f"""<your-project-description>

{names.display_name} is a Flask RESTful JSON API service. Use this README to
document what this project does, the domain it owns, the resources it exposes,
and the operational setup needed to run it.

The scaffold includes Flask-RESTful routing, camelCase JSON request/response
helpers, configuration loading, security primitives, and any optional
infrastructure selected during project generation."""
    return content.replace(TEMPLATE_README_DESCRIPTION, replacement)


def _rename_template_identity_paths(
    project_dir: Path,
    names: ProjectNames,
    log: TransformationLog,
) -> None:
    candidates = [
        path
        for path in project_dir.rglob("*")
        if not _is_in_skipped_directory(project_dir, path) and _renamed_path_name(path.name, names) != path.name
    ]

    for path in sorted(candidates, key=lambda candidate: len(candidate.parts), reverse=True):
        new_name = _renamed_path_name(path.name, names)
        target = path.with_name(new_name)
        path.rename(target)
        log.path_renames.append(f"{path.relative_to(project_dir)} -> {target.relative_to(project_dir)}")


def _renamed_path_name(path_name: str, names: ProjectNames) -> str:
    return path_name.replace(TEMPLATE_PACKAGE_NAME, names.package_name).replace(
        TEMPLATE_PROJECT_NAME, names.project_name
    )


def _is_in_skipped_directory(project_dir: Path, path: Path) -> bool:
    relative_parts = path.relative_to(project_dir).parts
    directories = relative_parts if path.is_dir() else relative_parts[:-1]
    return any(_should_skip_directory_name(part) for part in directories)


def _should_skip_directory_name(name: str) -> bool:
    return name in SKIPPED_DIRECTORY_NAMES or name.endswith(SKIPPED_DIRECTORY_SUFFIXES)
