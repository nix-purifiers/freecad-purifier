"""Freeze Addon Manager mutations before user workbench initializers run."""

import importlib.abc
import importlib.machinery
import sys

CLASSES = {
    "addonmanager_installer": ("AddonInstaller", "MacroInstaller"),
    "addonmanager_uninstaller": ("AddonUninstaller", "MacroUninstaller"),
    "addonmanager_dependency_installer": ("DependencyInstaller",),
}


def frozen(*args, **kwargs):
    raise RuntimeError("FreeCAD add-ons are locked; run freecad-purifier lock --update")


def protect(module):
    if getattr(module, "__freecad_purifier_guarded__", False):
        return
    name = module.__name__.rsplit(".", 1)[-1]
    for class_name in CLASSES.get(name, ()):
        getattr(module, class_name).run = frozen
    if name == "addonmanager_python_deps":
        original = module.call_pip

        def call_pip(arguments):
            if any(
                arg in {"install", "uninstall", "download", "wheel"}
                for arg in arguments
            ):
                return frozen()
            return original(arguments)

        module.call_pip = call_pip
    module.__freecad_purifier_guarded__ = True


class Loader:
    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        return self.original.create_module(spec)

    def __getattr__(self, name):
        return getattr(self.original, name)

    def exec_module(self, module):
        self.original.exec_module(module)
        protect(module)


def managed_name(fullname):
    if "." in fullname and not fullname.startswith(
        ("AddonManager.", "FreeCAD.AddonManager.")
    ):
        return False
    name = fullname.rsplit(".", 1)[-1]
    return name in CLASSES or name == "addonmanager_python_deps"


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if managed_name(fullname):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is not None:
                spec.loader = Loader(spec.loader)
            return spec
        return None


sys.meta_path.insert(0, Finder())
for name, module in list(sys.modules.items()):
    if module is not None and managed_name(name):
        protect(module)
