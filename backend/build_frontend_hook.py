from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from setuptools.command.build_py import build_py as _build_py

_BACKEND_DIR = Path(__file__).resolve().parent
_FRONTEND_DIR = _BACKEND_DIR.parent / "frontend"
_STATIC_DIR = _BACKEND_DIR / "catalog" / "static"
_TRUTHY = {"1", "true", "yes", "on"}


def _is_dist_build() -> bool:
    argv = " ".join(sys.argv).lower()
    return any(token in argv for token in ("bdist_wheel", "sdist", "build_wheel", "build_sdist"))


def _should_build_frontend() -> bool:
    forced = os.getenv("CATALOG_BUILD_FRONTEND", "").strip().lower()
    if forced in {"0", "false", "no", "off"}:
        return False
    if forced in _TRUTHY:
        return True
    return _is_dist_build()


def stamp_build_sha() -> str:
    spec = importlib.util.spec_from_file_location(
        "catalog_build_stamp", _BACKEND_DIR / "catalog" / "build_stamp.py"
    )
    if spec is None or spec.loader is None:
        return ""
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.write_build_sha())


def build_frontend_assets() -> None:
    if not (_FRONTEND_DIR / "package.json").is_file():
        return
    env = {**os.environ, "VITE_API_URL": ""}
    subprocess.check_call(["pnpm", "install"], cwd=_FRONTEND_DIR, env=env)
    subprocess.check_call(["pnpm", "run", "build"], cwd=_FRONTEND_DIR, env=env)
    dist = _FRONTEND_DIR / "dist"
    if not dist.is_dir():
        raise RuntimeError(f"frontend build produced no dist at {dist}")
    if _STATIC_DIR.exists():
        shutil.rmtree(_STATIC_DIR)
    shutil.copytree(dist, _STATIC_DIR)


class build_py(_build_py):
    def run(self) -> None:
        if _is_dist_build():
            stamp_build_sha()
        if _should_build_frontend():
            build_frontend_assets()
        super().run()
