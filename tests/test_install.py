import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install


def fixture_asar(path):
    files = {"files": {"a.txt": {"size": 3, "offset": "0"},
        "bundle.js": {"size": 3, "offset": "3", "integrity": {"blockSize": 2}},
        "native.node": {"size": 12, "unpacked": True}}}
    path.write_bytes(install.build_asar(files, b"onetwo", {}))


class InstallerTests(unittest.TestCase):
    def test_asar_roundtrip_preserves_other_files_and_updates_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "app.asar"
            fixture_asar(p)
            h, data = install.read_asar(p)
            p.write_bytes(install.build_asar(h, data, {"bundle.js": b"longer bundle"}))
            h, data = install.read_asar(p)
            self.assertEqual(install.contents(h["files"]["a.txt"], data), b"one")
            self.assertEqual(install.contents(h["files"]["bundle.js"], data), b"longer bundle")
            self.assertTrue(h["files"]["native.node"]["unpacked"])
            integrity = h["files"]["bundle.js"]["integrity"]
            self.assertEqual(integrity["hash"], hashlib.sha256(b"longer bundle").hexdigest())
            self.assertEqual(len(integrity["blocks"]), 7)

    def test_rejects_missing_target(self):
        with self.assertRaises(ValueError):
            install.build_asar({"files": {}}, b"", {"missing": b"x"})

    def test_renderer_refuses_unknown_layout_and_is_idempotent(self):
        with self.assertRaises(ValueError):
            install.patch_renderer("some other build", "component")
        s = 'useWorkflowRunStore jsxRuntimeExports\nfunction BaseNode({\n        subheader && /* @__PURE__ */'
        patched = install.patch_renderer(s, "component")
        self.assertEqual(install.patch_renderer(patched, "component"), patched)
        self.assertEqual(patched.count("jsxRuntimeExports.jsx(ModlyProgressPanel"), 1)

    def test_restore_refuses_updated_application(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            target = folder / "application"
            target.write_bytes(b"updated independently")
            (folder / "original.backup").write_bytes(b"original")
            (folder / "manifest.json").write_text(json.dumps([{
                "path": str(target), "backup": "original.backup",
                "original_sha256": hashlib.sha256(b"original").hexdigest(),
                "patched_sha256": hashlib.sha256(b"patched").hexdigest()}]))
            with self.assertRaises(ValueError):
                install.restore(folder)
            self.assertEqual(target.read_bytes(), b"updated independently")

    def test_restore_recovers_exact_original(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            target = folder / "application"
            target.write_bytes(b"patched")
            (folder / "original.backup").write_bytes(b"original")
            (folder / "manifest.json").write_text(json.dumps([{
                "path": str(target), "backup": "original.backup",
                "original_sha256": hashlib.sha256(b"original").hexdigest(),
                "patched_sha256": hashlib.sha256(b"patched").hexdigest()}]))
            install.restore(folder)
            self.assertEqual(target.read_bytes(), b"original")

    def test_hunyuan_patch_uses_pipeline_callback_and_preserves_cancellation(self):
        s = '''class Adapter:
    def generate(self):
        self._report(progress_cb, 12, "Generating 3D shape…")
        # target=smooth_progress
        mesh = outputs[0]
        self._check_cancelled(cancel_event)
        return mesh
'''
        patched = install.patch_hunyuan(s)
        ast.parse(patched)
        self.assertNotIn("target=smooth_progress", patched)
        self.assertIn("callback_steps=1", patched)
        self.assertEqual(patched.count("self._check_cancelled(cancel_event)"), 2)
        self.assertEqual(install.patch_hunyuan(patched), patched)


if __name__ == "__main__":
    unittest.main()
