"""Spec 003: the repo UI plist launches the Next.js production server, not Gradio."""

import json
import plistlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UI_PLIST = REPO / "com.secondbrain.ui.plist"


def _ui_plist() -> dict:
    with UI_PLIST.open("rb") as f:
        return plistlib.load(f)


def test_repo_plist_launches_npm_start_in_frontend():
    """Scenario: repo plist launches npm start in frontend/."""
    plist = _ui_plist()

    assert plist["Label"] == "com.secondbrain.ui"
    assert plist["ProgramArguments"] == ["/opt/homebrew/bin/npm", "run", "start"]
    assert Path(plist["WorkingDirectory"]) == REPO / "frontend"
    assert (plist["RunAtLoad"], plist["KeepAlive"], plist["ThrottleInterval"]) == (True, True, 10)
    for key in ("StandardOutPath", "StandardErrorPath"):
        assert Path(plist[key]).parent == REPO / "data" / "logs"


def test_repo_plist_no_longer_launches_gradio():
    """Scenario: repo plist no longer launches Gradio."""
    args = _ui_plist()["ProgramArguments"]

    assert "secondbrain.ui" not in args
    assert not any(a.endswith("/uv") for a in args)


def test_frontend_start_script_binds_loopback_on_port_7860():
    """Scenario: the frontend start script binds loopback on port 7860."""
    package = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["start"] == "next start -p 7860 -H 127.0.0.1"


def test_make_ui_runs_the_nextjs_frontend_not_gradio():
    """Scenario: make ui runs the Next.js frontend, not Gradio."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^ui:.*\n((?:\t.*\n)+)", makefile, re.M)
    assert match, "no ui target in the Makefile"
    recipe = match.group(1)

    assert "secondbrain.ui" not in recipe
    assert re.search(r"cd frontend && npm run start", recipe)
