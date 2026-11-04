"""Activate the real locked workbench in FreeCAD's normal GUI under Xvfb."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/FreeCAD"
xvfb = Path(sys.argv[2]).resolve() / "bin/xvfb-run"
resources = Path(sys.argv[3]).resolve()
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
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    bus = ET.Element("busconfig")
    ET.SubElement(bus, "type").text = "session"
    ET.SubElement(bus, "listen").text = "unix:tmpdir=" + str(runtime)
    ET.SubElement(bus, "auth").text = "EXTERNAL"
    policy = ET.SubElement(bus, "policy", context="default")
    for attribute in ["own", "send_destination", "receive_sender"]:
        ET.SubElement(policy, "allow", {attribute: "*"})
    bus_config = root / "bus.conf"
    ET.ElementTree(bus).write(bus_config, encoding="UTF-8", xml_declaration=True)
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
        "QT_QPA_PLATFORM": "xcb",
        "FONTCONFIG_FILE": str(resources / "fonts.conf"),
        "NO_AT_BRIDGE": "1",
        "HOME": str(root / "home"),
        "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=" + str(root / "no-system-bus"),
        "XDG_RUNTIME_DIR": str(runtime),
    }
    (root / "home").mkdir()
    for name in [
        "WAYLAND_DISPLAY",
        "WAYLAND_SOCKET",
        "DBUS_SESSION_BUS_ADDRESS",
        "SESSION_MANAGER",
        "AT_SPI_BUS_ADDRESS",
        "QT_QPA_PLATFORMTHEME",
        "DBUS_STARTER_ADDRESS",
        "DBUS_STARTER_BUS_TYPE",
        "XDG_ACTIVATION_TOKEN",
        "DESKTOP_STARTUP_ID",
    ]:
        env.pop(name, None)
    subprocess.run(
        [
            str(xvfb),
            "-a",
            str(resources / "bin/dbus-run-session"),
            "--dbus-daemon=" + str(resources / "bin/dbus-daemon"),
            "--config-file=" + str(bus_config),
            "--",
            str(cli),
            str(macro),
        ],
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
