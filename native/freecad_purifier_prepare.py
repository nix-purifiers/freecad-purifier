"""Prepare private native state without accepting executable ambient add-on code."""

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def prepare(state, profile):
    state = Path(state).resolve()
    profile = Path(profile).resolve()
    data = state / "data/FreeCAD/v1-1"
    mods = data / "Mod"
    mods.mkdir(parents=True, exist_ok=True)
    lock = json.loads((profile / "lock.json").read_text())
    expected = {
        entry["path"]: str((profile / "modules" / entry["path"]).resolve())
        for entry in lock["entries"]
    }
    expected["AddonManager"] = str((profile / "manager").resolve())
    record = state / "aliases.json"
    previous = json.loads(record.read_text()) if record.exists() else {}
    for item in mods.iterdir():
        if item.name == "manifest.json" and item.is_file() and not item.is_symlink():
            continue
        if not item.is_symlink() or os.readlink(item) not in {
            expected.get(item.name),
            previous.get(item.name),
        }:
            raise ValueError(f"unlocked or changed FreeCAD module state: {item}")
        if item.name not in expected:
            item.unlink()
    for name, target in expected.items():
        alias = mods / name
        if alias.is_symlink() and os.readlink(alias) != target:
            alias.unlink()
        if not alias.exists():
            alias.symlink_to(target)
    for directory in [data / "AdditionalPythonPackages", data / "Macro/Mod"]:
        if directory.exists() and any(directory.iterdir()):
            raise ValueError(f"unlocked FreeCAD dependency state: {directory}")
    record.write_text(json.dumps(expected, indent=2) + "\n")
    config = state / "config/FreeCAD/v1-1/user.cfg"
    config.parent.mkdir(parents=True, exist_ok=True)
    tree = (
        ET.parse(config)
        if config.exists()
        else ET.ElementTree(ET.Element("FCParameters"))
    )
    group = tree.getroot()
    for name in ["Root", "BaseApp", "Preferences", "Macro"]:
        child = group.find(f"FCParamGroup[@Name='{name}']")
        if child is None:
            child = ET.SubElement(group, "FCParamGroup", Name=name)
        group = child
    macro = group.find("FCText[@Name='MacroPath']")
    if macro is None:
        macro = ET.SubElement(group, "FCText", Name="MacroPath")
    macro.text = str(data / "Macro")
    (data / "Macro").mkdir(exist_ok=True)
    tree.write(config, encoding="UTF-8", xml_declaration=True)
    for name in ["home", "cache"]:
        (state / name).mkdir(exist_ok=True)
    return {
        "XDG_DATA_HOME": str(state / "data"),
        "XDG_CONFIG_HOME": str(state / "config"),
        "XDG_CACHE_HOME": str(state / "cache"),
        "FREECAD_PURIFIER_ENVIRONMENT": str(profile),
    }


if __name__ == "__main__":
    print(json.dumps(prepare(sys.argv[1], sys.argv[2])))
