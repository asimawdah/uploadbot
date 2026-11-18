from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage import copy_local_file, finalize_temp_file, sanitize_filename


class SanitizeFilenameTests(unittest.TestCase):
    def test_removes_directory_traversal(self) -> None:
        self.assertEqual(sanitize_filename("../../private/secret.txt"), "secret.txt")

    def test_replaces_unsafe_characters(self) -> None:
        self.assertEqual(sanitize_filename("report:final?.pdf"), "report_final_.pdf")

    def test_keeps_unicode_names(self) -> None:
        self.assertEqual(sanitize_filename("ملف مهم.pdf"), "ملف مهم.pdf")

    def test_falls_back_for_empty_names(self) -> None:
        self.assertEqual(sanitize_filename("../"), "unnamed_file")


class StorageTests(unittest.TestCase):
    def test_saves_file_with_original_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "incoming.part"
            files_dir = root / "files"
            incoming.write_bytes(b"file contents")

            saved = finalize_temp_file(incoming, files_dir, "report.txt")

            self.assertEqual(saved.name, "report.txt")
            self.assertEqual(saved.read_bytes(), b"file contents")
            self.assertFalse(incoming.exists())

    def test_never_overwrites_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files_dir = root / "files"
            files_dir.mkdir()
            original = files_dir / "report.txt"
            original.write_bytes(b"first")

            incoming = root / "incoming.part"
            incoming.write_bytes(b"second")
            saved = finalize_temp_file(incoming, files_dir, "report.txt")

            self.assertNotEqual(saved, original)
            self.assertEqual(original.read_bytes(), b"first")
            self.assertEqual(saved.read_bytes(), b"second")

    def test_copies_local_api_file_into_project_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "telegram-source.bin"
            source.write_bytes(b"large-file-content")

            saved = copy_local_file(source, root / "files", "archive.bin")

            self.assertEqual(saved.read_bytes(), b"large-file-content")
            self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
