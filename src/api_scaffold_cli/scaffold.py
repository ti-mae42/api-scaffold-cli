from __future__ import annotations

import re
import shutil
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from api_scaffold_cli.database import DatabaseLog, apply_database_option
from api_scaffold_cli.transform import TransformationLog, transform_project_identity


PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
VALID_URL_SCHEMES = {"file", "http", "https", "ssh"}


class ScaffoldError(Exception):
    """Base error for scaffold failures that should be shown to CLI users."""


class InvalidProjectNameError(ScaffoldError):
    pass


class InvalidRepositoryUrlError(ScaffoldError):
    pass


class TargetDirectoryExistsError(ScaffoldError):
    pass


class GitCloneError(ScaffoldError):
    pass


class ScaffoldPermissionError(ScaffoldError):
    pass


@dataclass(frozen=True)
class ScaffoldResult:
    path: Path
    transformation_log: TransformationLog
    database_log: DatabaseLog


def validate_project_name(project_name: str) -> None:
    if not PROJECT_NAME_PATTERN.fullmatch(project_name):
        raise InvalidProjectNameError(
            "Invalid PROJECT_NAME. Use letters, numbers, hyphens, or underscores, "
            "and start with a letter or number."
        )


def validate_repository_source(base_repo_url: str) -> None:
    if not base_repo_url or any(character.isspace() for character in base_repo_url):
        raise InvalidRepositoryUrlError(
            "Invalid base repository URL. Provide a valid URL or local git repository path."
        )

    if Path(base_repo_url).exists():
        return

    parsed = urlparse(base_repo_url)
    if parsed.scheme in VALID_URL_SCHEMES and (parsed.netloc or parsed.path):
        return

    if _is_scp_like_git_url(base_repo_url):
        return

    raise InvalidRepositoryUrlError(
        "Invalid base repository URL. Provide a valid URL or local git repository path."
    )


def create_project(
    *,
    project_name: str,
    output_dir: Path,
    base_repo_url: str,
    database: str = "none",
) -> ScaffoldResult:
    validate_project_name(project_name)
    validate_repository_source(base_repo_url)

    destination_root = output_dir.expanduser().resolve()
    target_dir = destination_root / project_name
    target_preexisted = target_dir.exists()

    try:
        destination_root.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        raise ScaffoldPermissionError(
            f"Permission denied while creating output directory: {destination_root}"
        ) from exc
    except OSError as exc:
        raise ScaffoldError(f"Could not create output directory {destination_root}: {exc}") from exc

    if target_dir.exists():
        if not target_dir.is_dir():
            raise TargetDirectoryExistsError(
                f"Target path already exists and is not a directory: {target_dir}"
            )

        if any(target_dir.iterdir()):
            raise TargetDirectoryExistsError(
                f"Target directory already exists and is not empty: {target_dir}"
            )

    try:
        _clone_repository(base_repo_url, target_dir)
        _remove_git_directory(target_dir)
        transformation_log = transform_project_identity(target_dir, project_name)
        database_log = apply_database_option(target_dir, database)
    except ScaffoldError:
        _cleanup_failed_clone(target_dir, keep_target_directory=target_preexisted)
        raise
    except PermissionError as exc:
        _cleanup_failed_clone(target_dir, keep_target_directory=target_preexisted)
        raise ScaffoldPermissionError(
            f"Permission denied while writing generated project: {target_dir}"
        ) from exc
    except OSError as exc:
        _cleanup_failed_clone(target_dir, keep_target_directory=target_preexisted)
        raise ScaffoldError(f"Could not generate project at {target_dir}: {exc}") from exc

    return ScaffoldResult(path=target_dir, transformation_log=transformation_log, database_log=database_log)


def _clone_repository(base_repo_url: str, target_dir: Path) -> None:
    result = subprocess.run(
        ["git", "clone", "--quiet", base_repo_url, str(target_dir)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        message = f"Git clone failed for {base_repo_url}"
        if detail:
            message = f"{message}: {detail}"
        raise GitCloneError(message)


def _remove_git_directory(target_dir: Path) -> None:
    git_dir = target_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)


def _cleanup_failed_clone(target_dir: Path, *, keep_target_directory: bool) -> None:
    if not target_dir.exists():
        return

    if keep_target_directory:
        with suppress(OSError):
            for child in target_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        return

    with suppress(OSError):
        shutil.rmtree(target_dir)


def _is_scp_like_git_url(value: str) -> bool:
    if value.startswith(("/", "./", "../")):
        return False

    return bool(re.match(r"^[^@\s]+@[^:\s]+:.+$", value))
