"""Exercise real native geometry, private state, management guards and fallback."""

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin"
original = Path(sys.argv[2]).resolve() / "bin/FreeCADCmd"
source = Path(__file__).resolve().parents[1]


def call(arguments, env, cwd, success=True):
    result = subprocess.run(
        arguments,
        env=env,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if success and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    if not success and result.returncode == 0:
        raise AssertionError(
            "expected failure: " + repr(arguments) + result.stdout + result.stderr
        )
    return result


with tempfile.TemporaryDirectory(prefix="freecad-native-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".freecad-purifier"),
    )
    env = os.environ.copy() | {
        "FREECAD_PURIFIER_PROJECT": str(project),
        "QT_QPA_PLATFORM": "offscreen",
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CACHE_HOME": str(root / "cache"),
    }
    for name in ["home", "config", "data", "cache"]:
        (root / name).mkdir()
    lock = project / "freecad-purifier.lock.json"
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()
    script = project / "build.py"
    code = script.read_text()
    volumes = []
    for length in [20, 21, 20]:
        script.write_text(code.replace("20.0", f"{length}.0"))
        output = root / f"output-{len(volumes)}"
        command_env = env | {"FREECAD_PURIFIER_OUTPUT": str(output)}
        call([str(cli / "FreeCADCmd"), str(script)], command_env, project)
        geometry = json.loads((output / "geometry.json").read_text())
        assert geometry["solids"] == 1
        volumes.append(geometry["volume"])
        assert hashlib.sha256(lock.read_bytes()).hexdigest() == digest
    script.write_text(code)
    assert volumes[1] > volumes[0] and volumes[0] == volumes[2]
    state = project / ".freecad-purifier"
    profile = (state / "environment").resolve()
    roots = call(["nix-store", "--query", "--roots", str(profile)], env, project)
    assert str(state / "environment") in roots.stdout
    probe = project / "native_probe.py"

    def native_probe(program):
        marker = root / "probe-passed"
        marker.unlink(missing_ok=True)
        body = "import os,traceback\nfrom pathlib import Path\ntry:\n"
        body += "\n".join("    " + line for line in program.splitlines())
        body += f"\n    Path({str(marker)!r}).write_text('passed')\n"
        body += "except BaseException:\n    os.write(2,traceback.format_exc().encode());os._exit(19)\n"
        probe.write_text(body)
        call([str(cli / "FreeCADCmd"), str(probe)], env, project)
        assert marker.read_text() == "passed"

    native_probe(
        "import FastenersCmd\nassert Path(FastenersCmd.__file__).resolve().is_relative_to('/nix/store')"
    )
    native_probe(
        "import FreeCAD\nFreeCAD.ParamGet('User parameter:BaseApp/Preferences/General').SetString('PurifierPreferenceProbe','retained')"
    )
    native_probe(
        "import FreeCAD\nassert FreeCAD.ParamGet('User parameter:BaseApp/Preferences/General').GetString('PurifierPreferenceProbe') == 'retained'"
    )
    native_probe("""import addonmanager_installer, addonmanager_uninstaller, addonmanager_dependency_installer
for operation in [addonmanager_installer.AddonInstaller.run, addonmanager_installer.MacroInstaller.run, addonmanager_uninstaller.AddonUninstaller.run, addonmanager_dependency_installer.DependencyInstaller.run]:
    try: operation(None)
    except RuntimeError as error: assert 'locked' in str(error)
    else: raise AssertionError('native manager mutation was allowed')
""")
    native_probe("""import FastenersCmd
try: Path(FastenersCmd.__file__).write_text('poison')
except OSError as error: assert error.errno in {1,13,30}
else: raise AssertionError('dependency code is writable')
""")
    mods = state / "data/FreeCAD/v1-1/Mod"
    unexpected = mods / "ambient"
    unexpected.mkdir()
    (unexpected / "Init.py").write_text("raise RuntimeError('ambient addon ran')\n")
    call([str(cli / "FreeCADCmd"), str(probe)], env, project, success=False)
    assert (unexpected / "Init.py").exists()
    shutil.rmtree(unexpected)
    alias = mods / "fasteners"
    target = os.readlink(alias)
    alias.unlink()
    alias.symlink_to(root)
    call([str(cli / "FreeCADCmd"), str(probe)], env, project, success=False)
    alias.unlink()
    alias.symlink_to(target)
    vendor = state / "data/FreeCAD/v1-1/AdditionalPythonPackages"
    vendor.mkdir()
    (vendor / "FastenersCmd.py").write_text(
        "raise RuntimeError('ambient provider ran')\n"
    )
    call([str(cli / "FreeCADCmd"), str(probe)], env, project, success=False)
    shutil.rmtree(vendor)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"root-network-ok")

        def log_message(self, *args):
            pass

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            native_probe(
                f"import urllib.request\nassert urllib.request.urlopen('http://127.0.0.1:{server.server_port}/').read()==b'root-network-ok'"
            )
        finally:
            server.shutdown()
            thread.join()
    spec = project / "freecad-purifier.json"
    before = spec.read_bytes()
    spec.write_text('{"addons": ["Curves"]}\n')
    call([str(cli / "FreeCADCmd"), str(probe)], env, project, success=False)
    spec.write_bytes(before)
    empty = root / "empty"
    empty.mkdir()
    fallback = env | {"FREECAD_PURIFIER_PROJECT": str(empty)}
    warning = (
        "warning: no FreeCAD purifier lock; using ordinary, impure add-on resolution\n"
    )
    for arguments in [["--version"], ["--purifier-invalid-native-option"]]:
        expected = call(
            [str(original), *arguments],
            fallback,
            empty,
            success=arguments == ["--version"],
        )
        actual = subprocess.run(
            [str(cli / "FreeCADCmd"), *arguments],
            env=fallback,
            cwd=empty,
            capture_output=True,
            text=True,
            check=False,
        )
        assert actual.returncode == expected.returncode
        assert actual.stdout == expected.stdout, (actual.stdout, expected.stdout)
        assert actual.stderr == warning + expected.stderr, (
            actual.stderr,
            expected.stderr,
        )
print("native FreeCAD conformance passed")
