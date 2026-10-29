import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from artifact_loader import copy_verified, safe_path, validate_manifest


class LoaderTests(unittest.TestCase):
    def test_paths_reject_escape(self):
        for path in ("../weights", "/weights", "x/../y", "x\\y", "C:x", "x//y", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(path)

    def test_nested_path(self):
        self.assertEqual(safe_path("weights/a.safetensors"), Path("weights/a.safetensors"))

    def test_verified_copy(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "model"
            copy_verified(io.BytesIO(b"abc"), path, hashlib.sha256(b"abc").hexdigest(), 3)
            self.assertEqual(path.read_bytes(), b"abc")

    def test_corrupt_object_is_not_published(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "model"
            with self.assertRaises(ValueError):
                copy_verified(io.BytesIO(b"wrong"), path, "a"*64, 5)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_name("model.partial").exists())

    def test_oversized_object_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "model"
            with self.assertRaises(ValueError):
                copy_verified(io.BytesIO(b"abc"), path, hashlib.sha256(b"abc").hexdigest(), 2)
            self.assertFalse(path.exists())

    def test_unversioned_object_is_rejected(self):
        manifest = {"schema": 1, "release_id": "r1", "runtime_image": "runtime@sha256:"+"a"*64,
                    "files": [{"path": "config.json", "sha256": "b"*64, "bytes": 3, "version_id": "null"}]}
        with self.assertRaises(ValueError):
            validate_manifest(manifest)

    def test_existing_partial_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "model"
            partial = Path(directory) / "model.partial"
            partial.write_bytes(b"prior attempt")
            with self.assertRaises(FileExistsError):
                copy_verified(io.BytesIO(b"abc"), path, hashlib.sha256(b"abc").hexdigest(), 3)
            self.assertEqual(partial.read_bytes(), b"prior attempt")

    def test_existing_destination_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "model"
            path.write_bytes(b"approved")
            with self.assertRaises(FileExistsError):
                copy_verified(io.BytesIO(b"abc"), path, hashlib.sha256(b"abc").hexdigest(), 3)
            self.assertEqual(path.read_bytes(), b"approved")


if __name__ == "__main__":
    unittest.main()
