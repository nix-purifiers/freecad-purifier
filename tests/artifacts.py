"""Consume exported native geometry, external locks and exact release assets."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/freecad-purifier"
original = Path(sys.argv[2]).resolve() / "bin/FreeCADCmd"
source = Path(__file__).resolve().parents[1]


def call(arguments, *, env, cwd):
    result = subprocess.run(
        arguments, check=True, env=env, cwd=cwd, text=True, capture_output=True
    )
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="freecad-artifacts-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".freecad-purifier"),
    )
    env = os.environ.copy() | {
        "HOME": str(root / "home"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    for name in ["home", "data", "config", "cache"]:
        (root / name).mkdir()
    args = [str(cli), "--project", str(project)]
    build = Path(call([*args, "build"], env=env, cwd=root))
    geometry = json.loads((build / "geometry.json").read_text())
    consumer = root / "native_geometry_consumer.py"
    marker = root / "consumed.json"
    consumer.write_text(
        "import FreeCAD,Part,os,json,traceback\nfrom pathlib import Path\ntry:\n"
        "    shape=Part.Shape()\n"
        f"    shape.read({str(build / 'bolt.brep')!r})\n"
        "    assert shape.isValid() and len(shape.Solids)==1\n"
        f"    Path({str(marker)!r}).write_text(json.dumps({{'volume':shape.Volume}}))\n"
        "except BaseException:\n    os.write(2,traceback.format_exc().encode());os._exit(17)\n"
    )
    call([str(original), str(consumer)], env=env, cwd=root)
    assert abs(json.loads(marker.read_text())["volume"] - geometry["volume"]) < 1e-7
    release = Path(call([*args, "bundle"], env=env, cwd=root))
    archive = release / "freecad-project.tar.gz"
    with tarfile.open(archive) as tar:
        assert json.loads(tar.extractfile("./geometry.json").read()) == geometry
        assert (
            tar.extractfile("./bolt.brep").read() == (build / "bolt.brep").read_bytes()
        )
    external = root / "external-lock.json"
    shutil.copyfile(project / "freecad-purifier.lock.json", external)
    replay = Path(call([*args, "--lock", str(external), "bundle"], env=env, cwd=root))
    assert (replay / archive.name).read_bytes() == archive.read_bytes()
    fake = root / "gh"
    fake.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
        "Path(os.environ['UPLOAD_RECORD']).write_text(json.dumps(sys.argv[1:]))\n"
        "Path(os.environ['UPLOAD_BYTES']).write_bytes(Path(sys.argv[4]).read_bytes())\n"
    )
    fake.chmod(0o755)
    publish_env = env | {
        "FREECAD_PURIFIER_GH": str(fake),
        "UPLOAD_RECORD": str(root / "upload.json"),
        "UPLOAD_BYTES": str(root / "upload.tar.gz"),
    }
    call([*args, "publish", "--tag", "proof"], env=publish_env, cwd=root)
    record = json.loads((root / "upload.json").read_text())
    assert record[:3] == ["release", "upload", "proof"] and record[3] == str(archive)
    assert (root / "upload.tar.gz").read_bytes() == archive.read_bytes()
print("native FreeCAD artifact consumers passed")
