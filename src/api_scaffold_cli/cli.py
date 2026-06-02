from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from api_scaffold_cli.config import get_default_base_repo_url
from api_scaffold_cli.scaffold import ScaffoldError, create_project

DEFAULT_BASE_REPO_URL = get_default_base_repo_url()
VALID_DATABASES = ("none", "postgresql", "mysql")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="api-scaffold",
        description="Generate API projects from a base repository.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser(
        "new",
        help="Create a new API project.",
        description="Create a new API project from the base repository.",
    )
    new_parser.add_argument("project_name", metavar="PROJECT_NAME")
    new_parser.add_argument(
        "--database",
        choices=VALID_DATABASES,
        default="none",
        help="Database backend to configure.",
    )
    new_parser.add_argument(
        "--with-celery",
        action="store_true",
        help="Enable Celery project options.",
    )
    new_parser.add_argument(
        "--with-aws",
        action="store_true",
        help="Enable AWS project options. Deprecated; use --with-cloud=aws.",
    )
    new_parser.add_argument(
        "--with-cloud",
        default=None,
        help="Enable a cloud provider integration. Currently supports aws.",
    )
    new_parser.add_argument(
        "--base-repo-url",
        default=DEFAULT_BASE_REPO_URL,
        help="GitHub repository URL to use as the base API project.",
    )
    new_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory where the project should be generated.",
    )
    new_parser.set_defaults(handler=handle_new)

    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def handle_new(args: argparse.Namespace) -> int:
    try:
        result = create_project(
            project_name=args.project_name,
            output_dir=args.output_dir,
            base_repo_url=args.base_repo_url,
            database=args.database,
            with_celery=args.with_celery,
            cloud=_resolve_cloud_option(args),
        )
    except ScaffoldError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _print_transformation_log(result.transformation_log)
    _print_database_log(result.database_log)
    _print_celery_log(result.celery_log)
    _print_cloud_log(result.cloud_log)
    print(f"Created project '{args.project_name}' at {result.path}")
    return 0


def _resolve_cloud_option(args: argparse.Namespace) -> str | None:
    if args.with_cloud:
        return args.with_cloud

    if args.with_aws:
        return "aws"

    return None


def _print_transformation_log(log) -> None:
    print("Transformation log:")
    print(f"- Updated text files: {log.changed_file_count}")
    for file_path in log.file_updates:
        print(f"  - {file_path}")

    print(f"- Renamed paths: {log.renamed_path_count}")
    for rename in log.path_renames:
        print(f"  - {rename}")

    if log.skipped_binary_files:
        print(f"- Skipped binary files: {len(log.skipped_binary_files)}")


def _print_database_log(log) -> None:
    print("Database log:")
    print(f"- Mode: {log.database}")

    if log.removed_paths:
        print(f"- Removed paths: {len(log.removed_paths)}")
        for path in log.removed_paths:
            print(f"  - {path}")

    if log.updated_files:
        print(f"- Updated files: {len(log.updated_files)}")
        for path in log.updated_files:
            print(f"  - {path}")

    if log.warnings:
        print(f"- Warnings: {len(log.warnings)}")
        for warning in log.warnings:
            print(f"  - {warning}")


def _print_celery_log(log) -> None:
    print("Celery log:")
    print(f"- Enabled: {log.enabled}")

    if log.removed_paths:
        print(f"- Removed paths: {len(log.removed_paths)}")
        for path in log.removed_paths:
            print(f"  - {path}")

    if log.updated_files:
        print(f"- Updated files: {len(log.updated_files)}")
        for path in log.updated_files:
            print(f"  - {path}")

    if log.warnings:
        print(f"- Warnings: {len(log.warnings)}")
        for warning in log.warnings:
            print(f"  - {warning}")


def _print_cloud_log(log) -> None:
    print("Cloud log:")
    print(f"- Provider: {log.provider or 'none'}")
    print(f"- Enabled: {log.enabled}")

    if log.removed_paths:
        print(f"- Removed paths: {len(log.removed_paths)}")
        for path in log.removed_paths:
            print(f"  - {path}")

    if log.updated_files:
        print(f"- Updated files: {len(log.updated_files)}")
        for path in log.updated_files:
            print(f"  - {path}")

    if log.warnings:
        print(f"- Warnings: {len(log.warnings)}")
        for warning in log.warnings:
            print(f"  - {warning}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
