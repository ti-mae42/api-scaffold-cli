from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


TEMPLATE_FEATURES_FILE = "TEMPLATE_FEATURES.md"
SUPPORTED_CLOUD_PROVIDER = "aws"
AWS_DEPENDENCY_NAMES = {"boto3", "botocore", "aioboto3"}
AWS_ENV_KEYS = {"CLOUD_REGION", "SNS_PLATFORM_APPLICATION_ARN"}
OPTIONAL_FEATURE_PATTERN = re.compile(r"^\s*#\s*[A-Z0-9_]+_OPTIONAL:\s*aws\b", re.IGNORECASE)
AWS_TEXT_PATTERNS = ("aws", "boto3", "botocore", "cloud_region", "sns_platform_application_arn")
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
class CloudFeatureGuidance:
    aws_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CloudLog:
    provider: str | None
    enabled: bool
    removed_paths: list[str] = field(default_factory=list)
    updated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def apply_cloud_option(project_dir: Path, cloud_provider: str | None) -> CloudLog:
    normalized_provider = _normalize_cloud_provider(cloud_provider)
    enabled = normalized_provider == SUPPORTED_CLOUD_PROVIDER
    log = CloudLog(provider=normalized_provider, enabled=enabled)
    guidance = load_cloud_feature_guidance(project_dir)
    log.warnings.extend(guidance.warnings)

    if normalized_provider and not enabled:
        log.warnings.append(f"Unsupported cloud provider '{normalized_provider}' was treated as disabled.")

    if enabled:
        _append_readme_cloud_section(
            project_dir,
            [
                "This project was generated with AWS integration support.",
                "",
                "Configure AWS credentials with one of the standard AWS SDK mechanisms.",
                "For local development, use an AWS profile or exported credentials:",
                "",
                "```sh",
                "aws configure",
                "export AWS_PROFILE=default",
                "aws sts get-caller-identity",
                "```",
                "",
                "Configure the AWS environment used by the API:",
                "",
                "```sh",
                "cp .env.example .env",
                "printf 'CLOUD_REGION=us-east-1\\n' >> .env",
                "printf 'SNS_PLATFORM_APPLICATION_ARN=arn:aws:sns:us-east-1:123456789012:app/GCM/example\\n' >> .env",
                "```",
                "",
                "When running in AWS, prefer an IAM role for the runtime instead of static access keys.",
                "If static credentials are required for local development, set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN` in your shell or credential store.",
            ],
            log,
            heading="AWS",
        )
        return log

    for relative_path in guidance.aws_paths:
        _remove_guided_path(project_dir, relative_path, log)

    _remove_aws_optional_markers(project_dir, log)
    _remove_cloud_import_references(project_dir, log)
    _remove_aws_dependencies(project_dir, log)
    _remove_aws_env_vars(project_dir, log)
    _remove_aws_docs_and_configs(project_dir, log)
    return log


def load_cloud_feature_guidance(project_dir: Path) -> CloudFeatureGuidance:
    features_path = project_dir / TEMPLATE_FEATURES_FILE
    guidance = CloudFeatureGuidance()
    if not features_path.is_file():
        guidance.warnings.append(f"{TEMPLATE_FEATURES_FILE} not found; no AWS files were removed by guidance.")
        return guidance

    in_aws_section = False
    in_when_disabled = False
    fallback_paths: list[str] = []
    for raw_line in features_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        lowered = line.lower()

        if lowered.startswith("## "):
            in_aws_section = "aws" in lowered or "cloud" in lowered
            in_when_disabled = False
            continue

        if not in_aws_section:
            continue

        if lowered.endswith(":"):
            in_when_disabled = lowered == "when disabled:"

        path = _extract_guidance_path(line)
        if not path:
            continue

        if in_when_disabled and lowered.startswith("- remove"):
            if _is_safe_aws_removal_path(path):
                _append_unique(guidance.aws_paths, path)
            continue

        _append_unique(fallback_paths, path)

    for path in fallback_paths:
        if _is_safe_aws_removal_path(path):
            _append_unique(guidance.aws_paths, path)

    return guidance


def _extract_guidance_path(line: str) -> str | None:
    backtick_match = re.search(r"`([^`]+)`", line)
    if backtick_match:
        return backtick_match.group(1).strip().strip("/")

    return None


def _remove_guided_path(project_dir: Path, relative_path: str, log: CloudLog) -> None:
    target = project_dir / relative_path
    if not target.exists():
        log.warnings.append(f"AWS path listed in {TEMPLATE_FEATURES_FILE} was not found: {relative_path}")
        return

    if not target.resolve().is_relative_to(project_dir.resolve()):
        log.warnings.append(f"Refused to remove path outside generated project: {relative_path}")
        return

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    log.removed_paths.append(relative_path)


def _remove_aws_optional_markers(project_dir: Path, log: CloudLog) -> None:
    for path in _iter_candidate_text_files(project_dir):
        content = path.read_text(encoding="utf-8")
        updated, removed_count = _remove_aws_optional_lines(content)
        if removed_count == 0:
            continue

        path.write_text(updated, encoding="utf-8")
        _record_updated_file(log, str(path.relative_to(project_dir)))


def _remove_aws_optional_lines(content: str) -> tuple[str, int]:
    lines = content.splitlines(keepends=True)
    output_lines: list[str] = []
    removed_count = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        if not OPTIONAL_FEATURE_PATTERN.match(line):
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

            if not _line_looks_aws_specific(next_line):
                break

            removed_count += 1
            index += 1

    return "".join(output_lines), removed_count


def _remove_cloud_import_references(project_dir: Path, log: CloudLog) -> None:
    for path in _iter_candidate_text_files(project_dir):
        if path.suffix != ".py":
            continue

        original = path.read_text(encoding="utf-8")
        updated = _remove_import_name(original, "cloud")
        if updated == original:
            continue

        path.write_text(updated, encoding="utf-8")
        _record_updated_file(log, str(path.relative_to(project_dir)))


def _remove_import_name(content: str, name_to_remove: str) -> str:
    output_lines: list[str] = []
    for line in content.splitlines(keepends=True):
        if " import " not in line or name_to_remove not in line:
            output_lines.append(line)
            continue

        prefix, imported_names = line.split(" import ", 1)
        line_ending = "\n" if imported_names.endswith("\n") else ""
        imported_names = imported_names.rstrip("\n")
        names = [name.strip() for name in imported_names.split(",")]
        if name_to_remove not in names:
            output_lines.append(line)
            continue

        remaining_names = [name for name in names if name != name_to_remove]
        if not remaining_names:
            continue

        output_lines.append(f"{prefix} import {', '.join(remaining_names)}{line_ending}")

    return "".join(output_lines)


def _remove_aws_dependencies(project_dir: Path, log: CloudLog) -> None:
    for path in project_dir.iterdir():
        if path.name == "pyproject.toml" or path.name.startswith("requirements"):
            _remove_aws_dependency_lines(project_dir, path, log)


def _remove_aws_dependency_lines(project_dir: Path, path: Path, log: CloudLog) -> None:
    original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines = [line for line in original_lines if not _is_aws_dependency_line(line)]

    if updated_lines == original_lines:
        return

    path.write_text("".join(updated_lines), encoding="utf-8")
    _record_updated_file(log, str(path.relative_to(project_dir)))


def _is_aws_dependency_line(line: str) -> bool:
    stripped = line.strip().strip(",").strip("'\"")
    if not stripped or stripped.startswith("#"):
        return False

    match = re.match(r"^([A-Za-z0-9_.-]+)", stripped)
    if not match:
        return False

    return match.group(1).lower() in AWS_DEPENDENCY_NAMES


def _remove_aws_env_vars(project_dir: Path, log: CloudLog) -> None:
    for path in project_dir.iterdir():
        if path.name.startswith(".env") or path.name.endswith(".env.example"):
            _remove_aws_env_lines(project_dir, path, log)


def _remove_aws_env_lines(project_dir: Path, path: Path, log: CloudLog) -> None:
    original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines = [line for line in original_lines if not _is_aws_env_line(line)]

    if updated_lines == original_lines:
        return

    path.write_text("".join(updated_lines), encoding="utf-8")
    _record_updated_file(log, str(path.relative_to(project_dir)))


def _is_aws_env_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return False

    key = stripped.split("=", 1)[0].upper()
    return key in AWS_ENV_KEYS or key.startswith("AWS_")


def _remove_aws_docs_and_configs(project_dir: Path, log: CloudLog) -> None:
    for path in _iter_candidate_text_files(project_dir):
        if path.name == TEMPLATE_FEATURES_FILE:
            continue

        if not _is_command_doc_or_config_file(path):
            continue

        original = path.read_text(encoding="utf-8")
        updated = _remove_aws_config_lines(original)
        if updated == original:
            continue

        path.write_text(updated, encoding="utf-8")
        _record_updated_file(log, str(path.relative_to(project_dir)))


def _remove_aws_config_lines(content: str) -> str:
    output_lines: list[str] = []
    for line in content.splitlines(keepends=True):
        lowered = line.lower()
        if any(pattern in lowered for pattern in ("aws", "boto3", "cloud_region", "sns_platform_application_arn")):
            continue

        output_lines.append(line)

    return "".join(output_lines)


def _append_readme_cloud_section(project_dir: Path, lines: list[str], log: CloudLog, *, heading: str) -> None:
    readme_path = project_dir / "README.md"
    if not readme_path.is_file():
        log.warnings.append("README.md was not found; AWS usage notes were not written.")
        return

    section_lines = ["", f"## {heading}", "", *lines, ""]
    content = readme_path.read_text(encoding="utf-8").rstrip()
    if "## AWS" in content:
        log.warnings.append("README already contains AWS documentation; appended generated AWS notes.")

    readme_path.write_text(f"{content}\n{chr(10).join(section_lines)}", encoding="utf-8")
    _record_updated_file(log, str(readme_path.relative_to(project_dir)))


def _is_safe_aws_removal_path(relative_path: str) -> bool:
    path = Path(relative_path)
    if path.name in {"initialize.py", "config.py", "pyproject.toml", ".env", ".env.example", ".env.sample"}:
        return False

    return path.name in {"cloud.py", "aws.py"} or (bool(path.suffix) and "aws" in path.name.lower())


def _is_command_doc_or_config_file(path: Path) -> bool:
    return path.suffix in {".md", ".sh", ".yaml", ".yml"} or path.name in {
        "Dockerfile",
        "Makefile",
        "docker-compose.yml",
    }


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


def _line_looks_aws_specific(line: str) -> bool:
    lowered = line.lower()
    return any(pattern in lowered for pattern in AWS_TEXT_PATTERNS) or _is_aws_dependency_line(line)


def _normalize_cloud_provider(cloud_provider: str | None) -> str | None:
    if cloud_provider is None:
        return None

    normalized = cloud_provider.strip().lower()
    return normalized or None


def _record_updated_file(log: CloudLog, relative_path: str) -> None:
    if relative_path not in log.updated_files:
        log.updated_files.append(relative_path)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
