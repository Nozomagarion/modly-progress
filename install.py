"""Reversible Modly desktop UI add-on. Python standard library only."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile

ROOT = Path(__file__).resolve().parent
MARKER = "// MODLY_PROGRESS_V1"


def read_asar(path: Path):
    with path.open("rb") as f:
        prefix = f.read(16)
        if len(prefix) != 16:
            raise ValueError("Truncated ASAR")
        size, header_size, payload_size, json_size = struct.unpack("<4I", prefix)
        if size != 4 or json_size > 64 * 1024 * 1024 or header_size < 8 + json_size:
            raise ValueError("Unsupported ASAR header")
        header = json.loads(f.read(json_size))
        f.seek(8 + header_size)
        data = f.read()
    return header, data


def entries(header, prefix=""):
    for name, entry in header.get("files", {}).items():
        full = prefix + name
        if "files" in entry:
            yield from entries(entry, full + "/")
        else:
            yield full, entry


def contents(entry, data):
    start = int(entry["offset"])
    result = data[start:start + entry["size"]]
    if len(result) != entry["size"]:
        raise ValueError("Truncated ASAR payload")
    return result


def build_asar(header, data, replacements):
    output = bytearray()
    found = set()
    for name, entry in entries(header):
        if entry.get("unpacked") or "link" in entry:
            continue
        blob = replacements.get(name)
        if blob is None:
            blob = contents(entry, data)
        else:
            found.add(name)
            if "integrity" in entry:
                block = entry["integrity"].get("blockSize", 4194304)
                entry["integrity"] = {
                    "algorithm": "SHA256", "hash": hashlib.sha256(blob).hexdigest(),
                    "blockSize": block,
                    "blocks": [hashlib.sha256(blob[i:i+block]).hexdigest() for i in range(0, len(blob), block)],
                }
        entry["offset"] = str(len(output))
        entry["size"] = len(blob)
        output.extend(blob)
    if found != set(replacements):
        raise ValueError("Replacement path missing from ASAR")
    raw = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    padding = (-len(raw)) % 4
    payload = struct.pack("<I", len(raw)) + raw + b"\0" * padding
    header_pickle = struct.pack("<I", len(payload)) + payload
    return struct.pack("<II", 4, len(header_pickle)) + header_pickle + output


def patch_renderer(source, component):
    if MARKER in source:
        return source
    anchor = "function BaseNode({"
    insertion = "        subheader && /* @__PURE__ */"
    if source.count(anchor) != 1 or source.count(insertion) != 1:
        raise ValueError("Unsupported Modly renderer. No file was changed.")
    if "useWorkflowRunStore" not in source or "jsxRuntimeExports" not in source:
        raise ValueError("Required Modly UI bindings unavailable")
    source = source.replace(anchor, MARKER + "\n" + component + "\n" + anchor, 1)
    return source.replace(insertion,
        '        /* @__PURE__ */ jsxRuntimeExports.jsx(ModlyProgressPanel, { nodeId: id }),\n' + insertion, 1)


def patch_hunyuan(source):
    if "MODLY_PROGRESS_STEPS_V1" in source:
        return source
    start = source.find('        self._report(progress_cb, 12, "Generating 3D shape…")')
    end = source.find("        self._check_cancelled(cancel_event)", start)
    if start < 0 or end < 0:
        raise ValueError("Unsupported Hunyuan Mini adapter; no changes made")
    original = source[start:end]
    if "target=smooth_progress" not in original or "mesh = outputs[0]" not in original:
        raise ValueError("Unsupported Hunyuan Mini inference block")
    replacement = '''        # MODLY_PROGRESS_STEPS_V1: report completed diffusion steps, never a timer.
        self._report(progress_cb, 12, "Diffusion 0/" + str(num_steps))

        def report_step(index, timestep, outputs):
            self._check_cancelled(cancel_event)
            completed = min(num_steps, int(index) + 1)
            self._report(progress_cb, 12 + int(68 * completed / num_steps),
                         f"Diffusion {completed}/{num_steps}")
            if completed == num_steps:
                self._report(progress_cb, 82, "Décodage du volume — durée inconnue")

        with torch.no_grad():
            generator = torch.Generator().manual_seed(seed)
            outputs = self._model(
                image=image,
                num_inference_steps=num_steps,
                octree_resolution=octree_res,
                guidance_scale=guidance_scale,
                num_chunks=4000,
                generator=generator,
                output_type="trimesh",
                callback=report_step,
                callback_steps=1,
            )
        mesh = outputs[0]

'''
    patched = source[:start] + replacement + source[end:]
    ast.parse(patched)
    return patched


def patch_generate_page(source, component):
    if MARKER in source:
        return source
    anchor = "function GeneratePage() {"
    insertion = '      firstPreflightIssue && !isRunning && /* @__PURE__ */'
    if source.count(anchor) != 1 or source.count(insertion) != 1:
        raise ValueError("Unsupported Generate page layout")
    source = source.replace(anchor, MARKER + "\n" + component + "\n" + anchor, 1)
    return source.replace(insertion,
        '      /* @__PURE__ */ jsxRuntimeExports.jsx(ModlyProgressPanel, {}),\n' + insertion, 1)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path, data):
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def defaults():
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    roaming = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    settings_path = roaming / "Modly/settings.json"
    settings = json.loads(settings_path.read_text("utf-8")) if settings_path.exists() else {}
    extension_root = Path(settings.get("extensionsDir", Path.home() / "Documents/Modly/extensions"))
    return local / "Programs/Modly/resources/app.asar", extension_root / "hunyuan3d-mini/generator.py", local / "ModlyProgress/backups"


def install(archive, generator, backup_root, *, dry_run=False, with_hunyuan=False):
    header, data = read_asar(archive)
    candidates = [(name, entry) for name, entry in entries(header)
                  if name.startswith("out/renderer/assets/WorkflowsPage-") and name.endswith(".js")]
    if len(candidates) != 1:
        raise ValueError("Expected exactly one WorkflowsPage bundle; refusing unsupported build")
    name, entry = candidates[0]
    source = contents(entry, data).decode("utf-8")
    patched = patch_renderer(source, (ROOT / "assets/progress.js").read_text("utf-8"))
    generate_candidates = [(n, e) for n, e in entries(header)
                           if n.startswith("out/renderer/assets/GeneratePage-") and n.endswith(".js")]
    if len(generate_candidates) != 1:
        raise ValueError("Expected exactly one GeneratePage bundle")
    generate_name, generate_entry = generate_candidates[0]
    generate_source = contents(generate_entry, data).decode("utf-8")
    generate_patched = patch_generate_page(generate_source, (ROOT / "assets/progress.js").read_text("utf-8"))
    changes = []
    replacements = {}
    if patched != source:
        replacements[name] = patched.encode("utf-8")
    if generate_patched != generate_source:
        replacements[generate_name] = generate_patched.encode("utf-8")
    if replacements:
        changes.append((archive, build_asar(header, data, replacements)))
    if with_hunyuan:
        original = generator.read_text("utf-8")
        improved = patch_hunyuan(original)
        if improved != original:
            # Check actual upstream callback support before touching the adapter.
            pipeline = generator.parents[2] / "models/hunyuan3d-mini/generate/_hy3dgen/hy3dgen/shapegen/pipelines.py"
            if not pipeline.exists() or 'callback_steps' not in pipeline.read_text("utf-8"):
                raise ValueError("Cannot verify installed Hunyuan pipeline callback support")
            changes.append((generator, improved.encode("utf-8")))
    for path, blob in changes:
        print(f"{'Would update' if dry_run else 'Update'}: {path} ({len(blob)} bytes)")
    if dry_run or not changes:
        print("Validation OK" if changes else "Already installed")
        return None
    # All compatibility checks complete before the first mutation.
    backup_root.mkdir(parents=True, exist_ok=True)
    import datetime
    backup = backup_root / datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir()
    records = []
    for i, (path, blob) in enumerate(changes):
        dest = backup / f"{i}-{path.name}.backup"
        shutil.copy2(path, dest)
        records.append({"path": str(path.resolve()), "backup": dest.name,
                        "original_sha256": digest(dest), "patched_sha256": hashlib.sha256(blob).hexdigest()})
    (backup / "manifest.json").write_text(json.dumps(records, indent=2), "utf-8")
    written = []
    try:
        for record, (path, blob) in zip(records, changes):
            atomic_write(path, blob)
            written.append(record)
    except Exception:
        for record in reversed(written):
            atomic_write(Path(record["path"]), (backup / record["backup"]).read_bytes())
        raise
    print(f"Backup: {backup}\nRestart Modly after any current run has finished.")
    return backup


def restore(backup):
    records = json.loads((backup / "manifest.json").read_text("utf-8"))
    for r in records:
        if digest(backup / r["backup"]) != r["original_sha256"]:
            raise ValueError("Backup checksum mismatch")
        if digest(Path(r["path"])) != r["patched_sha256"]:
            raise ValueError("Installed files changed (possibly a Modly update); refusing to overwrite")
    for r in records:
        atomic_write(Path(r["path"]), (backup / r["backup"]).read_bytes())
    print("Original files restored. Restart Modly.")


def main():
    archive, generator, backups = defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asar", type=Path, default=archive)
    parser.add_argument("--generator", type=Path, default=generator)
    parser.add_argument("--backups", type=Path, default=backups)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--hunyuan", action="store_true", help="Also enable real Hunyuan Mini diffusion-step reporting")
    parser.add_argument("--restore", type=Path, metavar="BACKUP_FOLDER")
    args = parser.parse_args()
    try:
        if args.restore:
            restore(args.restore)
        else:
            install(args.asar, args.generator, args.backups, dry_run=args.dry_run, with_hunyuan=args.hunyuan)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
