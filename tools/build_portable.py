"""Build the Windows x64 portable distribution."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
PYTHON_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
PYTHON_SHA256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
EXCLUDED = shutil.ignore_patterns("__pycache__", "*.pyc", "*.nbc", "*.nbi", "*.whl")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, help="Reuse an already provisioned Python 3.12 runtime")
    args = parser.parse_args()
    stage = ROOT / "build" / f"Mocknido-v{VERSION}"
    if stage.exists():
        raise SystemExit("Build directory exists. Move or remove it before rebuilding.")
    stage.mkdir(parents=True)
    runtime = stage / "runtime"
    if args.runtime:
        shutil.copytree(args.runtime, runtime, ignore=EXCLUDED)
    else:
        if sys.version_info[:2] != (3, 12) or sys.platform != "win32":
            raise SystemExit("Build with Python 3.12 on Windows x64.")
        runtime.mkdir()
        download = stage.parent / "python-3.12.10-embed-amd64.zip"
        urllib.request.urlretrieve(PYTHON_URL, download)
        if hashlib.sha256(download.read_bytes()).hexdigest() != PYTHON_SHA256:
            raise SystemExit("Python archive checksum mismatch.")
        with zipfile.ZipFile(download) as archive:
            archive.extractall(runtime)
        subprocess.run([sys.executable, "-m", "pip", "install", "--only-binary=:all:",
                        "--no-compile", "--target", str(runtime / "Lib" / "site-packages"),
                        "-r", str(ROOT / "requirements.txt")], check=True)
    (runtime / "python312._pth").write_text(
        "python312.zip\n.\nLib/site-packages\n../scripts\nimport site\n", encoding="utf-8")
    for name in ("scripts", "pillow_obj", "docs"):
        shutil.copytree(ROOT / name, stage / name, ignore=EXCLUDED)
    (stage / "deliverables").mkdir()
    for name in ("sample.png", "launch.py", "启动模巢.bat", "README.md", "LICENSE",
                 "THIRD_PARTY_NOTICES.md", "CHANGELOG.md", "requirements.txt"):
        shutil.copy2(ROOT / name, stage / name)
    probe = subprocess.check_output([str(runtime / "python.exe"), "-X", "utf8", "-c",
        "import sys,importlib.metadata as m,json; print(json.dumps({'python':sys.version.split()[0],"
        "'dependencies':{x:m.version(x) for x in ['Pillow','numpy','numba','scipy','llvmlite','websocket-client']}}))"], text=True)
    metadata = json.loads(probe)
    assert metadata["python"] == "3.12.10", "Unexpected Python version"
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        name, version = line.split("==")
        assert metadata["dependencies"][name] == version, "Dependency version mismatch: " + name
    metadata.update(version=VERSION, platform="Windows x64", python_source=PYTHON_URL)
    (stage / "build-info.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    subprocess.run([str(runtime / "python.exe"), "-X", "utf8", str(stage / "scripts" / "check_portable.py")], cwd=stage, check=True)
    release = ROOT / "RELEASE"
    release.mkdir(exist_ok=True)
    output = release / f"Mocknido-v{VERSION}-Windows-x64.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
        for path in sorted(stage.rglob("*")):
            rel = path.relative_to(stage)
            if path.is_file() and not any(x in ("__pycache__", "cache") for x in rel.parts) and path.suffix not in (".pyc", ".nbc", ".nbi"):
                archive.write(path, Path(stage.name) / rel)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (release / "SHA256SUMS.txt").write_text(digest + "  " + output.name + "\n", encoding="ascii")
    print("Built:", output.name, flush=True)


if __name__ == "__main__":
    main()
