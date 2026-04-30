"""Тесты для filesystem MCP-сервера.

Запуск (внутри контейнера backend):
    docker compose exec backend python -m unittest tests.test_filesystem_server -v

Тесты не общаются с MCP-протоколом — проверяются чистые функции,
которые сервер дёргает в `call_tool`. Перед каждым тестом подменяем
PROJECT_ROOT и ALLOWED_WRITE_DIR на временную директорию.
"""

import sys
import tempfile
import unittest
from pathlib import Path

# mcp_servers/ — не пакет, поэтому добавляем его в sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR / "mcp_servers"))

import filesystem_server as fs  # noqa: E402


class FilesystemServerTests(unittest.TestCase):
    """Использует временную директорию вместо реального /repo."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

        # Готовим минимальную структуру «проекта»
        (self.root / "src").mkdir()
        (self.root / "docs").mkdir()
        (self.root / ".git").mkdir()  # должен быть пропущен при поиске

        (self.root / "src" / "service.py").write_text(
            "import os\n"
            "from typing import List\n"
            "\n"
            "class GigaChatProvider:\n"
            "    \"\"\"LLM провайдер.\"\"\"\n"
            "\n"
            "    def chat(self, messages):\n"
            "        return 'ok'\n"
            "\n"
            "def helper():\n"
            "    print('debug')\n",
            encoding="utf-8",
        )
        (self.root / "src" / "router.py").write_text(
            "from .service import GigaChatProvider\n"
            "\n"
            "provider = GigaChatProvider()\n"
            "print('debug')  # not great\n",
            encoding="utf-8",
        )
        (self.root / ".git" / "config").write_text(
            "GigaChatProvider in skipped dir\n", encoding="utf-8"
        )
        (self.root / "src" / "page.tsx").write_text(
            "import React from 'react'\n"
            "interface Props { name: string }\n"
            "export const Page = (props: Props) => <div>{props.name}</div>\n",
            encoding="utf-8",
        )

        # Подменяем глобальные константы в модуле
        self._orig_root = fs.PROJECT_ROOT
        self._orig_write = fs.ALLOWED_WRITE_DIR
        fs.PROJECT_ROOT = self.root
        fs.ALLOWED_WRITE_DIR = (self.root / "docs").resolve()

    def tearDown(self) -> None:
        fs.PROJECT_ROOT = self._orig_root
        fs.ALLOWED_WRITE_DIR = self._orig_write
        self._tmp.cleanup()

    # ----- list_project_files -----

    def test_list_files_filters_by_glob(self) -> None:
        result = fs._list_files("src", "*.py")
        paths = {e["path"] for e in result["entries"]}
        self.assertIn("src/service.py", paths)
        self.assertIn("src/router.py", paths)
        self.assertNotIn("src/page.tsx", paths)

    def test_list_files_skips_git_dir(self) -> None:
        result = fs._list_files(".", "*")
        paths = [e["path"] for e in result["entries"]]
        # Никакая запись не должна начинаться с .git
        self.assertFalse(any(p.startswith(".git") for p in paths))

    # ----- read_project_file -----

    def test_read_file_returns_numbered_lines(self) -> None:
        result = fs._read_file("src/service.py", max_lines=2, start_line=1)
        self.assertEqual(result["start_line"], 1)
        self.assertEqual(result["end_line"], 2)
        self.assertIn("    1: import os", result["content"])

    def test_read_file_blocks_traversal(self) -> None:
        result = fs._read_file("../../etc/passwd")
        self.assertIn("error", result)

    # ----- find_usages -----

    def test_find_usages_groups_by_file(self) -> None:
        result = fs._find_usages("GigaChatProvider", root=".", file_glob="*.py")
        self.assertGreaterEqual(result["total_matches"], 2)
        files = {item["file"] for item in result["files"]}
        self.assertIn("src/service.py", files)
        self.assertIn("src/router.py", files)
        # Скрытые .git-файлы не должны попасть
        self.assertFalse(any(".git" in f for f in files))

    def test_find_usages_word_boundary_excludes_substring(self) -> None:
        # `Provider` как подстрока внутри `GigaChatProvider` не должна находиться:
        # find_usages матчит по \b — это полная защита от ложных срабатываний.
        result = fs._find_usages("Provider", file_glob="*.py")
        self.assertEqual(result["total_matches"], 0)

        # Но если завести файл, где есть отдельное слово Provider — оно найдётся.
        (self.root / "src" / "extra.py").write_text(
            "Provider = object()  # standalone\n", encoding="utf-8"
        )
        result2 = fs._find_usages("Provider", file_glob="*.py")
        self.assertEqual(result2["total_matches"], 1)
        self.assertEqual(result2["matches"][0]["file"], "src/extra.py")

    # ----- analyze_file -----

    def test_analyze_python_extracts_classes_and_functions(self) -> None:
        result = fs._analyze_file("src/service.py")
        self.assertEqual(result["language"], "python")
        self.assertIn("GigaChatProvider", result["classes"])
        self.assertIn("helper", result["functions"])
        self.assertIn("chat", result["functions"])
        self.assertIn("typing", result["imports"])

    def test_analyze_tsx(self) -> None:
        result = fs._analyze_file("src/page.tsx")
        self.assertEqual(result["language"], "typescript/javascript")
        self.assertIn("Props", result["interfaces"])
        self.assertIn("react", result["imports"])

    # ----- check_rules -----

    def test_check_rules_finds_forbidden_print(self) -> None:
        rules = [
            {
                "name": "no-print",
                "pattern": r"\bprint\(",
                "must_match": False,
                "file_glob": "*.py",
            }
        ]
        result = fs._check_rules("src", rules)
        files = {v["file"] for v in result["violations"]}
        self.assertIn("src/service.py", files)
        self.assertIn("src/router.py", files)

    def test_check_rules_required_pattern_missing(self) -> None:
        rules = [
            {
                "name": "must-have-license",
                "pattern": r"^# SPDX-License-Identifier",
                "must_match": True,
                "file_glob": "*.py",
            }
        ]
        result = fs._check_rules("src", rules)
        # Ни в одном файле нет такой строки → должны быть нарушения
        self.assertGreaterEqual(result["violations_count"], 2)
        self.assertTrue(
            all(v["kind"] == "missing_required_pattern" for v in result["violations"])
        )

    # ----- compute_diff -----

    def test_compute_diff_for_existing_file(self) -> None:
        new = (
            "import os\n"
            "from typing import List\n"
            "\n"
            "class GigaChatProvider:\n"
            "    \"\"\"LLM провайдер.\"\"\"\n"
            "\n"
            "    def chat(self, messages):\n"
            "        return 'updated'\n"  # ← изменение
            "\n"
            "def helper():\n"
            "    print('debug')\n"
        )
        result = fs._compute_diff("src/service.py", new)
        self.assertFalse(result["is_new_file"])
        self.assertGreaterEqual(result["lines_added"], 1)
        self.assertGreaterEqual(result["lines_removed"], 1)
        self.assertIn("updated", result["diff"])

    def test_compute_diff_for_new_file_marks_as_new(self) -> None:
        result = fs._compute_diff("docs/new.md", "# Hello\n")
        self.assertTrue(result["is_new_file"])
        self.assertGreaterEqual(result["lines_added"], 1)

    def test_compute_diff_no_changes(self) -> None:
        same = (self.root / "src" / "service.py").read_text(encoding="utf-8")
        result = fs._compute_diff("src/service.py", same)
        self.assertTrue(result["no_changes"])

    # ----- write_doc -----

    def test_write_doc_into_docs(self) -> None:
        result = fs._write_doc("docs/report.md", "# Отчёт\n", overwrite=False)
        self.assertTrue(result["saved"])
        self.assertTrue((self.root / "docs" / "report.md").exists())

    def test_write_doc_outside_docs_blocked(self) -> None:
        result = fs._write_doc("src/leak.py", "rm -rf /\n", overwrite=False)
        self.assertFalse(result["saved"])
        self.assertIn("error", result)
        self.assertFalse((self.root / "src" / "leak.py").exists())

    def test_write_doc_no_overwrite_by_default(self) -> None:
        (self.root / "docs" / "exists.md").write_text("v1", encoding="utf-8")
        result = fs._write_doc("docs/exists.md", "v2", overwrite=False)
        self.assertFalse(result["saved"])
        # Файл не должен был измениться
        self.assertEqual(
            (self.root / "docs" / "exists.md").read_text(encoding="utf-8"), "v1"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
