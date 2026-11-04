"""Launch a writable project with frozen native modules; require successful completion."""

import os
import subprocess
from pathlib import Path

from freecad_purifier_prepare import prepare

state = Path(os.environ["TMPDIR"]) / "freecad-state"
env = os.environ.copy()
env.update(prepare(state, os.environ["FREECAD_PURIFIER_ENVIRONMENT"]))
env["HOME"] = str(state / "home")
env["QT_QPA_PLATFORM"] = "offscreen"
env["FREECAD_PURIFIER_BUILD_DONE"] = str(state / "build-done")
subprocess.run(
    [
        os.environ["FREECAD_PURIFIER_COMMAND_BINARY"],
        str(Path(__file__).with_name("freecad_purifier_build.py")),
    ],
    env=env,
    stdin=subprocess.DEVNULL,
    check=True,
)
if not Path(env["FREECAD_PURIFIER_BUILD_DONE"]).is_file():
    raise RuntimeError("FreeCAD did not complete the project script")
