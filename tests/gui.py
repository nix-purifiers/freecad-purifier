"""Activate the real locked workbench in FreeCAD's normal GUI under Xvfb."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/FreeCAD"
xvfb = Path(sys.argv[2]).resolve() / "bin/xvfb-run"
source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="freecad-gui-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".freecad-purifier"),
    )
    marker = root / "gui.json"
    macro = root / "native_gui_probe.FCMacro"
    macro.write_text(
        "import FreeCAD,FreeCADGui,os,json,traceback\nfrom pathlib import Path\n"
        "from PySideWrapper import QtCore,QtWidgets\ntry:\n"
        "    assert 'FastenersWorkbench' in FreeCADGui.listWorkbenches()\n"
        "    FreeCADGui.activateWorkbench('FastenersWorkbench')\n"
        "    import addonmanager_installer\n"
        "    try: addonmanager_installer.AddonInstaller.run(None)\n"
        "    except RuntimeError as error: assert 'locked' in str(error)\n"
        "    else: raise AssertionError('GUI manager mutations were not frozen')\n"
        f"    Path({str(marker)!r}).write_text(json.dumps({{'workbench':FreeCADGui.activeWorkbench().name(),'gui':FreeCAD.GuiUp}}))\n"
        "except BaseException:\n    os.write(2,traceback.format_exc().encode());os._exit(17)\n"
        "QtCore.QTimer.singleShot(0,QtWidgets.QApplication.instance().quit)\n"
    )
    env = os.environ.copy() | {
        "FREECAD_PURIFIER_PROJECT": str(project),
        "QTWEBENGINE_DISABLE_SANDBOX": "1",
        "LIBGL_ALWAYS_SOFTWARE": "1",
    }
    subprocess.run(
        [str(xvfb), "-a", str(cli), str(macro)],
        env=env,
        cwd=project,
        check=True,
        timeout=60,
    )
    assert json.loads(marker.read_text()) == {
        "workbench": "FastenersWorkbench",
        "gui": 1,
    }
print("native FreeCAD GUI workbench activation passed")
