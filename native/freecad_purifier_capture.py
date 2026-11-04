"""Run original native catalog selection, dependency traversal and Git installation."""

import json
import os
import subprocess
import traceback
from pathlib import Path

try:
    from PySideWrapper import QtWidgets

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    import addonmanager_freecad_interface as fci
    from AddonCatalog import AddonCatalog
    from addonmanager_installer import AddonInstaller, InstallationMethod
    from freecad_purifier_common import (
        CatalogView,
        component,
        dependencies,
        providers,
        public_url,
    )

    root = Path(os.environ["FREECAD_PURIFIER_CAPTURE"])
    request = json.loads(Path(os.environ["FREECAD_PURIFIER_REQUEST"]).read_text())
    raw = json.loads((root / "catalog.json").read_text())
    catalog = AddonCatalog(raw)
    available = CatalogView(catalog)
    required = {component(name) for name in request["addons"]}
    installed = {}
    sdk = Path(os.environ["FREECAD_PURIFIER_ORIGINAL"])
    allowed = (
        (sdk / "Mod/AddonManager/ALLOWED_PYTHON_PACKAGES.txt").read_text().splitlines()
    )
    while required - installed.keys():
        name = min(required - installed.keys())
        addon = available[name]
        public_url(addon.url)
        if (
            not addon.contains_workbench()
            or addon.contains_macro()
            or addon.contains_preference_pack()
            or addon.contains_bundle()
        ):
            raise ValueError("the initial FreeCAD provider supports workbench addons")
        fci.Preferences().set("force_git_in_repos", name)
        installer = AddonInstaller(addon, allow_list=allowed)
        if not installer.run(InstallationMethod.GIT):
            raise RuntimeError(f"native Git installation failed: {name}")
        location = Path(installer.installation_path) / name

        def git(*args, location=location):
            return subprocess.check_output(
                ["git", "-C", str(location), *args], text=True
            ).strip()

        origin = public_url(git("config", "--get", "remote.origin.url"))
        graph = dependencies(addon, available)
        required.update(component(dep.name) for dep in graph.required_external_addons)
        installed[name] = {
            "id": name,
            "url": origin,
            "rev": git("rev-parse", "HEAD"),
            "path": str(location),
            "package_xml": (location / "package.xml").read_text(),
            "requires": sorted(addon.requires),
            "external_addons": sorted(
                dep.name for dep in graph.required_external_addons
            ),
        }
    for name, result in installed.items():
        graph = dependencies(available[name], available)
        result["providers"] = providers(graph)
        result["external_addons"] = sorted(
            dep.name for dep in graph.required_external_addons
        )
        conflicts = {addon.name for addon in graph.blockers} & installed.keys()
        if conflicts:
            raise ValueError(f"conflicting FreeCAD addons: {name}: {sorted(conflicts)}")
    context = {name: raw[name] for name in sorted(installed)}
    (root / "selection.json").write_text(
        json.dumps({"addons": installed, "catalog": context}, indent=2) + "\n"
    )
except BaseException:  # noqa: BLE001 - FreeCAD otherwise masks Python failures and exits.
    os.write(2, traceback.format_exc().encode())
    os._exit(1)
