import importlib
import os

if os.environ.get("FREECAD_PURIFIER_ENVIRONMENT"):
    importlib.import_module("freecad_purifier_guard")
