import importlib
import os
import runpy
import sys
import traceback
from pathlib import Path

try:
    importlib.import_module("freecad_purifier_guard")
    sys.path.insert(0, str(Path(os.environ["FREECAD_PURIFIER_SCRIPT"]).parent))
    runpy.run_path(os.environ["FREECAD_PURIFIER_SCRIPT"], run_name="__main__")
    Path(os.environ["FREECAD_PURIFIER_BUILD_DONE"]).write_text("passed\n")
except BaseException:  # noqa: BLE001 - FreeCAD otherwise masks Python failures and exits.
    os.write(2, traceback.format_exc().encode())
    os._exit(1)
