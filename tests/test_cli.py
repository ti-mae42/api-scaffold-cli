import sys
import unittest
import shutil
import subprocess
import tempfile
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api_scaffold_cli.cli import DEFAULT_BASE_REPO_URL, main, parse_args


class TestCliArgumentParsing(unittest.TestCase):
    def test_new_requires_project_name(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parse_args(["new"])

    def test_new_parses_required_project_name(self) -> None:
        args = parse_args(["new", "new-project-api"])

        self.assertEqual(args.command, "new")
        self.assertEqual(args.project_name, "new-project-api")

    def test_new_uses_default_options(self) -> None:
        cwd = Path.cwd()
        args = parse_args(["new", "new-project-api"])

        self.assertEqual(args.database, "none")
        self.assertFalse(args.with_celery)
        self.assertFalse(args.with_aws)
        self.assertIsNone(args.with_cloud)
        self.assertEqual(args.base_repo_url, DEFAULT_BASE_REPO_URL)
        self.assertEqual(args.output_dir, cwd)

    def test_new_accepts_all_options(self) -> None:
        output_dir = Path("generated")

        args = parse_args(
            [
                "new",
                "new-project-api",
                "--database=postgresql",
                "--with-celery",
                "--with-cloud=aws",
                "--base-repo-url=https://github.com/acme/base-api.git",
                f"--output-dir={output_dir}",
            ]
        )

        self.assertEqual(args.database, "postgresql")
        self.assertTrue(args.with_celery)
        self.assertFalse(args.with_aws)
        self.assertEqual(args.with_cloud, "aws")
        self.assertEqual(args.base_repo_url, "https://github.com/acme/base-api.git")
        self.assertEqual(args.output_dir, output_dir)

    def test_new_accepts_supported_databases(self) -> None:
        for database in ("none", "postgresql"):
            with self.subTest(database=database):
                args = parse_args(["new", "new-project-api", f"--database={database}"])

                self.assertEqual(args.database, database)

    def test_new_rejects_unsupported_database(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parse_args(["new", "new-project-api", "--database=mysql"])

    @unittest.skipUnless(shutil.which("git"), "git is required for clone integration test")
    def test_new_command_clones_from_local_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_repo = create_local_git_repo(tmp_path / "base-api")
            output_dir = tmp_path / "output"
            stdout = StringIO()
            stderr = StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "new",
                        "new-project-api",
                        f"--base-repo-url={source_repo}",
                        f"--output-dir={output_dir}",
                    ]
                )

            generated_project = output_dir / "new-project-api"
            self.assertEqual(exit_code, 0, stderr.getvalue())
            self.assertIn("Transformation log:", stdout.getvalue())
            self.assertIn("Database log:", stdout.getvalue())
            self.assertIn("Celery log:", stdout.getvalue())
            self.assertIn("Cloud log:", stdout.getvalue())
            self.assertIn(f"Created project 'new-project-api' at {generated_project}", stdout.getvalue())
            self.assertTrue((generated_project / "app.py").is_file())
            self.assertFalse((generated_project / ".git").exists())

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


if __name__ == "__main__":
    unittest.main()
