"""Portable entry point; uses only the bundled runtime."""
from pathlib import Path
import os
import runpy
import sys

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ["NUMBA_CACHE_DIR"] = str(ROOT / "cache" / "numba")
if __name__ == "__main__":
    try:
        import numpy, PIL, scipy, numba
        assert (ROOT / "sample.png").is_file(), "Default image missing"
        assert (ROOT / "pillow_obj" / "pillow_squ.fbx").is_file(), "Pillow model missing"
        print("模巢 Mocknido：正在启动，请保留此窗口。", flush=True)
        sys.argv = [str(ROOT / "scripts" / "render_photobook.py"), "--gui"]
        runpy.run_path(sys.argv[0], run_name="__main__")
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
