"""
nanobot - A lightweight AI agent framework
"""

import tomllib
import sys
from importlib import import_module
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path


def _install_editable_webui_alias() -> None:
    """Expose top-level webui helpers as nanobot.webui in source checkouts."""
    if "nanobot.webui" in sys.modules:
        return

    package_dir = Path(__file__).resolve().parent
    source_webui = package_dir.parent / "webui" / "__init__.py"
    if not source_webui.exists():
        return

    try:
        webui_module = import_module("webui")
    except ModuleNotFoundError:
        return

    sys.modules.setdefault("nanobot.webui", webui_module)
    globals()["webui"] = webui_module


def _read_pyproject_version() -> str | None:
    """Read the source-tree version when package metadata is unavailable."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not pyproject.exists():
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("project", {}).get("version")


def _resolve_version() -> str:
    try:
        return _pkg_version("nanobot-ai")
    except PackageNotFoundError:
        # Source checkouts often import nanobot without installed dist-info.
        return _read_pyproject_version() or "0.2.0"


__version__ = _resolve_version()
__logo__ = "🐈"

_install_editable_webui_alias()

_LAZY_EXPORTS = {
    "Nanobot": ".nanobot",
    "RunResult": ".nanobot",
}


def __getattr__(name: str):
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    mod = import_module(module_path, __name__)
    val = getattr(mod, name)
    globals()[name] = val
    return val


__all__ = ["Nanobot", "RunResult"]
