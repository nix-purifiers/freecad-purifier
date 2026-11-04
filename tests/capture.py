"""Fresh native capture, cold replay and atomic failure against the public catalog."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/freecad-purifier"
source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="freecad-capture-") as temporary:
    project = Path(temporary)
    shutil.copyfile(
        source / "examples/minimal/freecad-purifier.json",
        project / "freecad-purifier.json",
    )
    env = os.environ.copy() | {"FREECAD_PURIFIER_PROJECT": str(project)}
    subprocess.run([str(cli), "lock", "--update"], check=True, env=env, cwd=project)
    lock = project / "freecad-purifier.lock.json"
    before = lock.read_bytes()
    subprocess.run([str(cli), "lock"], check=True, env=env, cwd=project)
    subprocess.run([str(cli), "prefetch"], check=True, env=env, cwd=project)
    assert lock.read_bytes() == before
    selection_file = project / "freecad-purifier.json"
    selection = json.loads(selection_file.read_text())
    selection["addons"].append("purifier_missing_addon_probe")
    selection_file.write_text(json.dumps(selection))
    failed = subprocess.run(
        [str(cli), "lock", "--update"], check=False, env=env, cwd=project
    )
    assert failed.returncode != 0 and lock.read_bytes() == before
    empty = project / "empty"
    empty.mkdir()
    (empty / "freecad-purifier.json").write_text('{"addons": []}\n')
    empty_env = env | {"FREECAD_PURIFIER_PROJECT": str(empty)}
    subprocess.run([str(cli), "lock", "--update"], check=True, env=empty_env, cwd=empty)
    subprocess.run(
        [str(cli), "exec", "--", "--version"], check=True, env=empty_env, cwd=empty
    )

print("native FreeCAD capture and atomic failure passed")
