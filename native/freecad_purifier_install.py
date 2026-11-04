"""Replay original COPY installation against already fetched immutable Git sources."""

import json
import os
import shutil
import traceback
from pathlib import Path

try:
    from PySideWrapper import QtWidgets

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from AddonCatalog import AddonCatalog
    from addonmanager_installer import AddonInstaller, InstallationMethod
    from freecad_purifier_common import dependencies, providers

    lock = json.loads(Path(os.environ["FREECAD_PURIFIER_LOCK_DATA"]).read_text())
    catalog = AddonCatalog(lock["native"]["catalog"])
    addons = {
        name: catalog.get_addon_from_id(name)
        for name in catalog.get_available_addon_ids()
    }
    allowed = (
        (
            Path(os.environ["FREECAD_PURIFIER_ORIGINAL"])
            / "Mod/AddonManager/ALLOWED_PYTHON_PACKAGES.txt"
        )
        .read_text()
        .splitlines()
    )
    out = Path(os.environ["out"])
    out.mkdir(parents=True, exist_ok=True)
    locations = {}
    for entry in lock["entries"]:
        name = entry["path"]
        addon = addons[name]
        addon.url = str(Path(os.environ["FREECAD_PURIFIER_TREE"]) / name)
        installer = AddonInstaller(addon, allow_list=allowed)
        if not installer.run(InstallationMethod.COPY):
            raise RuntimeError(f"native COPY installation failed: {name}")
        location = Path(installer.installation_path) / name
        if (location / "package.xml").read_text() != entry["freecad"]["package_xml"]:
            raise ValueError(f"native package metadata changed: {name}")
        locations[name] = location
    for entry in lock["entries"]:
        name = entry["path"]
        addon = addons[name]
        graph = dependencies(addon, addons)
        actual = {
            "requires": sorted(addon.requires),
            "providers": providers(graph),
            "external_addons": sorted(
                dep.name for dep in graph.required_external_addons
            ),
        }
        expected = {key: entry["freecad"][key] for key in actual}
        if actual != expected:
            raise ValueError(f"native FreeCAD dependency graph changed: {name}")
        shutil.copytree(locations[name], out / "modules" / name)
    (out / "modules").mkdir(exist_ok=True)
except BaseException:  # noqa: BLE001 - FreeCAD otherwise masks Python failures and exits.
    os.write(2, traceback.format_exc().encode())
    os._exit(1)
