import shutil
import subprocess
import sys
import tempfile
import unittest
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api_scaffold_cli.scaffold import (
    InvalidProjectNameError,
    InvalidRepositoryUrlError,
    TargetDirectoryExistsError,
    create_project,
    validate_project_name,
    validate_repository_source,
)
from api_scaffold_cli.transform import derive_project_names


class TestScaffoldValidation(unittest.TestCase):
    def test_validate_project_name_accepts_supported_names(self) -> None:
        for project_name in ("new-project-api", "api_42", "Api42"):
            with self.subTest(project_name=project_name):
                validate_project_name(project_name)

    def test_validate_project_name_rejects_invalid_names(self) -> None:
        for project_name in ("", "../api", "/tmp/api", ".api", "api name", "api.name"):
            with self.subTest(project_name=project_name), self.assertRaises(InvalidProjectNameError):
                validate_project_name(project_name)

    def test_validate_repository_source_accepts_urls_and_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            validate_repository_source("https://github.com/ti-mae42/python-flask-base-api")
            validate_repository_source("git@github.com:ti-mae42/python-flask-base-api.git")
            validate_repository_source(tmp_dir)

    def test_validate_repository_source_rejects_invalid_values(self) -> None:
        for repo_source in ("", "not a url", "://missing-scheme"):
            with self.subTest(repo_source=repo_source), self.assertRaises(InvalidRepositoryUrlError):
                validate_repository_source(repo_source)

    def test_create_project_rejects_existing_non_empty_target_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            target_dir = output_dir / "new-project-api"
            target_dir.mkdir()
            (target_dir / "existing.txt").write_text("existing\n", encoding="utf-8")

            with self.assertRaises(TargetDirectoryExistsError):
                create_project(
                    project_name="new-project-api",
                    output_dir=output_dir,
                    base_repo_url="https://github.com/ti-mae42/python-flask-base-api",
                )


class TestNameConversion(unittest.TestCase):
    def test_derive_project_names_converts_project_name(self) -> None:
        names = derive_project_names("new-project-api")

        self.assertEqual(names.project_name, "new-project-api")
        self.assertEqual(names.package_name, "new_project_api")
        self.assertEqual(names.display_name, "New Project API")

    def test_derive_project_names_handles_underscores_and_initialisms(self) -> None:
        names = derive_project_names("aws_api_cli")

        self.assertEqual(names.package_name, "aws_api_cli")
        self.assertEqual(names.display_name, "AWS API CLI")

    def test_create_project_rejects_existing_target_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            target_path = output_dir / "new-project-api"
            target_path.write_text("existing\n", encoding="utf-8")

            with self.assertRaises(TargetDirectoryExistsError):
                create_project(
                    project_name="new-project-api",
                    output_dir=output_dir,
                    base_repo_url="https://github.com/ti-mae42/python-flask-base-api",
                )


@unittest.skipUnless(shutil.which("git"), "git is required for clone integration tests")
class TestScaffoldCloneIntegration(unittest.TestCase):
    def test_create_project_clones_local_git_repo_without_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_repo = create_local_git_repo(tmp_path / "base-api")
            output_dir = tmp_path / "output"

            result = create_project(
                project_name="new-project-api",
                output_dir=output_dir,
                base_repo_url=str(source_repo),
            )
            generated_project = result.path

            self.assertEqual(generated_project, output_dir / "new-project-api")
            self.assertTrue((generated_project / "app.py").is_file())
            self.assertFalse((generated_project / ".git").exists())

    def test_create_project_can_clone_into_existing_empty_target_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_repo = create_local_git_repo(tmp_path / "base-api")
            output_dir = tmp_path / "output"
            target_dir = output_dir / "new-project-api"
            target_dir.mkdir(parents=True)

            result = create_project(
                project_name="new-project-api",
                output_dir=output_dir,
                base_repo_url=str(source_repo),
            )
            generated_project = result.path

            self.assertEqual(generated_project, target_dir)
            self.assertTrue((generated_project / "app.py").is_file())
            self.assertFalse((generated_project / ".git").exists())

    def test_create_project_transforms_fake_base_api_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_repo = create_fake_base_api_repo(tmp_path / "base-api")
            output_dir = tmp_path / "output"

            result = create_project(
                project_name="my-awesome-api",
                output_dir=output_dir,
                base_repo_url=str(source_repo),
            )
            generated_project = result.path

            self.assertTrue((generated_project / "my_awesome_api" / "__init__.py").is_file())
            self.assertFalse((generated_project / "base_api").exists())
            self.assertFalse((generated_project / ".git").exists())

            readme = (generated_project / "README.md").read_text(encoding="utf-8")
            pyproject = (generated_project / "pyproject.toml").read_text(encoding="utf-8")
            docker_compose = (generated_project / "docker-compose.yml").read_text(encoding="utf-8")
            env_example = (generated_project / ".env.example").read_text(encoding="utf-8")
            app_file = (generated_project / "my_awesome_api" / "app.py").read_text(encoding="utf-8")
            initialize_file = (generated_project / "my_awesome_api" / "initialize.py").read_text(encoding="utf-8")

            self.assertIn("# My Awesome API", readme)
            self.assertIn('name = "my-awesome-api"', pyproject)
            self.assertIn("container_name: my-awesome-api-web", docker_compose)
            self.assertIn("APP_NAME=My Awesome API", env_example)
            self.assertIn("MY_AWESOME_API_SERVICE_NAME=my-awesome-api-web", env_example)
            self.assertIn("from my_awesome_api.config import APP_NAME", app_file)
            self.assertIn("from my_awesome_api.initialize import create_app", app_file)
            self.assertNotIn("from my_awesome_api.db import db", initialize_file)
            self.assertIn("from my_awesome_api.infrastructure import apm, security", initialize_file)
            self.assertNotIn("from my_awesome_api.infrastructure import apm, database, security", initialize_file)
            self.assertNotIn("db.init_app", initialize_file)
            self.assertIn('"My Awesome API"', app_file)
            self.assertEqual(
                (generated_project / "image.bin").read_bytes(),
                b"\0Base API\0base_api\0base-api",
            )
            self.assert_template_identity_removed(generated_project)
            self.assertIn("README.md", result.transformation_log.file_updates)
            self.assertIn("base_api -> my_awesome_api", result.transformation_log.path_renames)

            sys.path.insert(0, str(generated_project))
            try:
                module = importlib.import_module("my_awesome_api.app")
                self.assertEqual(module.get_app_name(), "My Awesome API")
                self.assertEqual(module.create_app(), {"name": "My Awesome API"})
            finally:
                sys.path.remove(str(generated_project))
                sys.modules.pop("my_awesome_api.app", None)
                sys.modules.pop("my_awesome_api.initialize", None)
                sys.modules.pop("my_awesome_api.config", None)
                sys.modules.pop("my_awesome_api", None)

    def test_create_project_keeps_database_support_for_postgresql(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_repo = create_fake_base_api_repo(tmp_path / "base-api")
            output_dir = tmp_path / "output"

            result = create_project(
                project_name="my-awesome-api",
                output_dir=output_dir,
                base_repo_url=str(source_repo),
                database="postgresql",
            )
            generated_project = result.path

            self.assertTrue((generated_project / "my_awesome_api" / "db.py").is_file())
            self.assertTrue((generated_project / "my_awesome_api" / "infrastructure" / "database.py").is_file())
            self.assertTrue((generated_project / "my_awesome_api" / "initialize.py").is_file())
            self.assertTrue((generated_project / "migrations" / "env.py").is_file())
            self.assertTrue((generated_project / "alembic.ini").is_file())

            pyproject = (generated_project / "pyproject.toml").read_text(encoding="utf-8")
            requirements = (generated_project / "requirements.txt").read_text(encoding="utf-8")
            env_example = (generated_project / ".env.example").read_text(encoding="utf-8")
            readme = (generated_project / "README.md").read_text(encoding="utf-8")

            self.assertIn("SQLAlchemy", pyproject)
            self.assertIn("psycopg", requirements)
            self.assertIn("DATABASE_URL=", env_example)
            self.assertIn("PostgreSQL database support", readme)
            self.assertEqual(result.database_log.database, "postgresql")
            self.assertEqual(result.database_log.removed_paths, [])

            sys.path.insert(0, str(generated_project))
            try:
                module = importlib.import_module("my_awesome_api.app")
                self.assertEqual(
                    module.create_app(),
                    {"name": "My Awesome API", "db_initialized": True},
                )
            finally:
                sys.path.remove(str(generated_project))
                sys.modules.pop("my_awesome_api.app", None)
                sys.modules.pop("my_awesome_api.initialize", None)
                sys.modules.pop("my_awesome_api.db", None)
                sys.modules.pop("my_awesome_api.config", None)
                sys.modules.pop("my_awesome_api", None)

    def test_create_project_removes_database_support_for_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_repo = create_fake_base_api_repo(tmp_path / "base-api")
            output_dir = tmp_path / "output"

            result = create_project(
                project_name="my-awesome-api",
                output_dir=output_dir,
                base_repo_url=str(source_repo),
                database="none",
            )
            generated_project = result.path

            self.assertFalse((generated_project / "my_awesome_api" / "db.py").exists())
            self.assertFalse((generated_project / "my_awesome_api" / "infrastructure" / "database.py").exists())
            self.assertTrue((generated_project / "my_awesome_api" / "initialize.py").is_file())
            self.assertFalse((generated_project / "migrations").exists())
            self.assertFalse((generated_project / "alembic.ini").exists())

            pyproject = (generated_project / "pyproject.toml").read_text(encoding="utf-8")
            requirements = (generated_project / "requirements.txt").read_text(encoding="utf-8")
            env_example = (generated_project / ".env.example").read_text(encoding="utf-8")
            readme = (generated_project / "README.md").read_text(encoding="utf-8")
            app_file = (generated_project / "my_awesome_api" / "app.py").read_text(encoding="utf-8")
            initialize_file = (generated_project / "my_awesome_api" / "initialize.py").read_text(encoding="utf-8")

            self.assertNotIn("SQLAlchemy", pyproject)
            self.assertNotIn("Alembic", pyproject)
            self.assertNotIn("psycopg", requirements)
            self.assertNotIn("DATABASE_URL", env_example)
            self.assertNotIn("POSTGRES_HOST", env_example)
            self.assertNotIn("from my_awesome_api.db import db", app_file)
            self.assertNotIn("from my_awesome_api.db import db", initialize_file)
            self.assertIn("from my_awesome_api.infrastructure import apm, security", initialize_file)
            self.assertNotIn("from my_awesome_api.infrastructure import apm, database, security", initialize_file)
            self.assertNotIn("db.init_app", app_file)
            self.assertNotIn("db.init_app", initialize_file)
            self.assertIn("without database support", readme)
            self.assertIn("my_awesome_api/db.py", result.database_log.removed_paths)
            self.assertIn("my_awesome_api/infrastructure/database.py", result.database_log.removed_paths)
            self.assertNotIn("my_awesome_api/initialize.py", result.database_log.removed_paths)
            self.assertIn("my_awesome_api/initialize.py", result.database_log.updated_files)
            self.assertIn("migrations", result.database_log.removed_paths)
            self.assertIn("alembic.ini", result.database_log.removed_paths)

            sys.path.insert(0, str(generated_project))
            try:
                module = importlib.import_module("my_awesome_api.app")
                self.assertEqual(module.create_app(), {"name": "My Awesome API"})
            finally:
                sys.path.remove(str(generated_project))
                sys.modules.pop("my_awesome_api.app", None)
                sys.modules.pop("my_awesome_api.initialize", None)
                sys.modules.pop("my_awesome_api.config", None)
                sys.modules.pop("my_awesome_api", None)

    def assert_template_identity_removed(self, generated_project: Path) -> None:
        forbidden = ("Base API", "base_api", "base-api", "BASE_API")
        skipped_directories = {"__pycache__", ".pytest_cache", ".venv", "build", "dist"}
        for path in generated_project.rglob("*"):
            if any(part in skipped_directories for part in path.relative_to(generated_project).parts):
                continue
            for value in forbidden:
                self.assertNotIn(value, path.name, f"{value!r} remains in path {path}")
            if not path.is_file() or _is_binary(path):
                continue

            content = path.read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, content, f"{value!r} remains in {path}")


def create_local_git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    (path / "app.py").write_text("print('base api')\n", encoding="utf-8")
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "Initial commit",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return path


def create_fake_base_api_repo(path: Path) -> Path:
    package_dir = path / "base_api"
    package_dir.mkdir(parents=True)
    infrastructure_dir = package_dir / "infrastructure"
    infrastructure_dir.mkdir()
    (package_dir / "__init__.py").write_text('"""Base API package."""\n', encoding="utf-8")
    (infrastructure_dir / "__init__.py").write_text("", encoding="utf-8")
    (infrastructure_dir / "apm.py").write_text("def create_monitor(app):\n    return app\n", encoding="utf-8")
    (infrastructure_dir / "security.py").write_text("", encoding="utf-8")
    (infrastructure_dir / "database.py").write_text("# BASE_API_OPTIONAL: postgresql\n", encoding="utf-8")
    (package_dir / "config.py").write_text(
        'APP_NAME = "Base API"\nCONFIG_NAME = "base-api-config"\nENV_PREFIX = "BASE_API"\n',
        encoding="utf-8",
    )
    (package_dir / "db.py").write_text(
        "class FakeDB:\n"
        "    def init_app(self, app):\n"
        "        app['db_initialized'] = True\n\n"
        "db = FakeDB()\n",
        encoding="utf-8",
    )
    (package_dir / "initialize.py").write_text(
        "from base_api.config import APP_NAME\n"
        "from base_api.infrastructure import apm, database, security\n\n"
        "# TESTE_API_OPTIONAL: postgresql\n"
        "from base_api.db import db\n"
        "\n"
        "def create_app():\n"
        "    app = {'name': APP_NAME}\n"
        "    # TESTE_API_OPTIONAL: postgresql\n"
        "    db.init_app(app)\n"
        "    return app\n",
        encoding="utf-8",
    )
    (package_dir / "app.py").write_text(
        "from base_api.config import APP_NAME\n"
        "from base_api.initialize import create_app\n\n"
        "DEFAULT_APP_NAME = \"Base API\"\n\n"
        "def get_app_name():\n"
        "    return APP_NAME\n",
        encoding="utf-8",
    )
    (path / "README.md").write_text(
        "# Base API\n\nDocker service: base-api-web\nPackage: base_api\n",
        encoding="utf-8",
    )
    (path / "pyproject.toml").write_text(
        "[project]\n"
        "name = \"base-api\"\n"
        "dependencies = [\n"
        "    \"Flask>=3\",\n"
        "    \"SQLAlchemy>=2\",\n"
        "    \"Alembic>=1\",\n"
        "]\n",
        encoding="utf-8",
    )
    (path / "requirements.txt").write_text(
        "Flask>=3\nSQLAlchemy>=2\npsycopg[binary]>=3\nalembic>=1\n",
        encoding="utf-8",
    )
    (path / "docker-compose.yml").write_text(
        "services:\n"
        "  web:\n"
        "    container_name: base-api-web\n",
        encoding="utf-8",
    )
    (path / ".env.example").write_text(
        "APP_NAME=Base API\n"
        "APP_MODULE=base_api.app\n"
        "BASE_API_SERVICE_NAME=base-api-web\n"
        "DATABASE_URL=postgresql://postgres:postgres@localhost:5432/base_api\n"
        "POSTGRES_HOST=localhost\n"
        "CONTAINER=base-api-web\n",
        encoding="utf-8",
    )
    migrations_dir = path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "env.py").write_text("from base_api.db import db\n", encoding="utf-8")
    (path / "alembic.ini").write_text("[alembic]\nscript_location = migrations\n", encoding="utf-8")
    (path / "TEMPLATE_FEATURES.md").write_text(
        "# Template Features\n\n"
        "## Database\n\n"
        "Database files:\n"
        "- `base_api/db.py`\n"
        "- `base_api/infrastructure/database.py`\n"
        "- `base_api/initialize.py`\n"
        "- `migrations`\n"
        "- `alembic.ini`\n\n"
        "Startup files:\n"
        "- `base_api/initialize.py`\n",
        encoding="utf-8",
    )
    (path / "base-api.env").write_text("PROJECT=base-api\n", encoding="utf-8")
    (path / "image.bin").write_bytes(b"\0Base API\0base_api\0base-api")
    cache_dir = path / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "base_api.pyc").write_bytes(b"base_api")
    return _commit_git_repo(path)


def _commit_git_repo(path: Path) -> Path:
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "Initial commit",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return path


def _is_binary(path: Path) -> bool:
    content = path.read_bytes()
    if b"\0" in content:
        return True

    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return True

    return False


if __name__ == "__main__":
    unittest.main()
