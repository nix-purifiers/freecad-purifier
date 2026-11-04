"""Project native Addon Manager metadata onto the provided Nix SDK."""

import importlib.metadata
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import FreeCAD
from Addon import Addon
from addonmanager_metadata import Version
from packaging.requirements import Requirement


class CatalogView(dict):
    """Load only the native catalog objects traversed by its dependency walker."""

    def __init__(self, catalog):
        super().__init__()
        self.catalog = catalog
        self.available = set(catalog.get_available_addon_ids())

    def __contains__(self, name):
        return name in self.available

    def __missing__(self, name):
        value = self.catalog.get_addon_from_id(name)
        self[name] = value
        return value


def component(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9_+-][A-Za-z0-9_.+-]*", value
    ):
        raise ValueError("invalid FreeCAD addon identifier")
    if value.lower() == "addonmanager":
        raise ValueError("Addon Manager is supplied by the pinned SDK")
    return value


def public_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("FreeCAD addon sources must be public HTTPS Git repositories")
    return value


def dependencies(addon, available):
    result = Addon.Dependencies()
    addon.walk_dependency_tree(available, result)
    return result


def providers(deps):
    if Version(from_list=list(sys.version_info[:3])) < deps.python_min_version:
        raise ValueError("addon requires a newer Python SDK")
    installed = {}
    for text in sorted(deps.python_requires):
        requirement = Requirement(text)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        if requirement.extras or requirement.url:
            raise ValueError(
                f"Python requirement needs an explicit Nix provider: {text}"
            )
        try:
            version = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ValueError(f"missing Nix SDK Python provider: {text}") from error
        if version not in requirement.specifier:
            raise ValueError(f"Nix SDK Python provider does not satisfy {text}")
        installed[requirement.name] = version
    for workbench in deps.internal_workbenches:
        if not (Path(FreeCAD.getHomePath()) / "Mod" / workbench).is_dir():
            raise ValueError(f"missing internal FreeCAD SDK workbench: {workbench}")
    return {
        "python": installed,
        "internal_workbenches": sorted(deps.internal_workbenches),
        "python_optional": sorted(deps.python_optional),
    }
