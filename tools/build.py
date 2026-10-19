"""Build distributable zips for BadVertexColorTool (stdlib only).

Usage:
    python tools/build.py
    blender --background --factory-startup --python tools/build.py

Creates in dist/:
    bad_vertex_color_tool-<version>.zip         Extension (files in the archive root)
    BadVertexColorTool-<version>-legacy.zip     Legacy add-on (inside BadVertexColorTool/)

Only whitelisted files are packed; see ROOT_FILES / PACKAGES.
"""

import ast
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
LEGACY_DIR = "BadVertexColorTool"

# Whitelist: top-level files (every other top-level *.py is added too) and packages (only *.py inside).
ROOT_FILES = ("blender_manifest.toml", "LICENSE", "README.md", "README.uk.md")
PACKAGES = ("core", "ops", "brush", "preview", "ui")


def read_manifest_version() -> str:
    text = (ROOT / "blender_manifest.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("ERROR: version not found in blender_manifest.toml")
    return m.group(1)


def read_bl_info_version() -> str:
    tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "bl_info" for t in node.targets):
            info = ast.literal_eval(node.value)
            return ".".join(str(x) for x in info["version"])
    raise SystemExit("ERROR: bl_info not found in __init__.py")


def collect_files() -> list[Path]:
    """Whitelisted files relative to ROOT, sorted."""
    files: list[Path] = []
    for p in sorted(ROOT.glob("*.py")):
        files.append(p.relative_to(ROOT))
    for name in ROOT_FILES:
        if (ROOT / name).is_file():
            files.append(Path(name))
    for pkg in PACKAGES:
        for p in sorted((ROOT / pkg).rglob("*.py")):
            if "__pycache__" not in p.parts:
                files.append(p.relative_to(ROOT))
    seen, out = set(), []
    for f in files:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def write_zip(path: Path, files: list[Path], prefix: str) -> None:
    if path.exists():
        path.unlink()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            arc = f"{prefix}{f.as_posix()}"
            zf.write(ROOT / f, arc)
    print(f"\n{path.relative_to(ROOT)}  ({path.stat().st_size} bytes)")
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            print(f"  {info.filename}  {info.file_size}")


def main() -> int:
    manifest_v, info_v = read_manifest_version(), read_bl_info_version()
    if manifest_v != info_v:
        print(f"ERROR: version mismatch: blender_manifest.toml={manifest_v}, bl_info={info_v}")
        return 1
    if not (ROOT / "LICENSE").is_file():
        print("WARNING: LICENSE not found, building without it")
    files = collect_files()
    DIST.mkdir(exist_ok=True)
    write_zip(DIST / f"bad_vertex_color_tool-{manifest_v}.zip", files, "")
    write_zip(DIST / f"{LEGACY_DIR}-{manifest_v}-legacy.zip", files, f"{LEGACY_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
