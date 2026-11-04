"""Enforce management guards even when native safe mode skips initializers."""

import importlib

importlib.import_module("freecad_purifier_guard")
