"""FreeCAD's normal application workflow with a frozen native extension profile."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("FreeCAD addon repositories must use public HTTPS URLs")
    return url


def selection(project):
    value = json.loads((project / "freecad-purifier.json").read_text())
    if set(value) != {"addons"} or not isinstance(value["addons"], list):
        raise ValueError("freecad-purifier.json needs an addons list")
    if len(set(value["addons"])) != len(value["addons"]):
        raise ValueError("duplicate FreeCAD addon")
    for name in value["addons"]:
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9_+-][A-Za-z0-9_.+-]*", name)
            or name.lower() == "addonmanager"
        ):
            raise ValueError(
                "invalid FreeCAD addon identifier; Addon Manager is supplied by the SDK"
            )
    return value


def project_path(explicit):
    if explicit:
        return Path(explicit).resolve()
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "freecad-purifier.json").exists() or (
            parent / "freecad-purifier.lock.json"
        ).exists():
            return parent
    return current


def validate(project, lock):
    data = json.loads(lock.read_text())
    if data.get("version") != 1 or data.get("purifier") != "freecad":
        raise ValueError("unsupported FreeCAD lock")
    if data.get("sdk") != os.environ["FREECAD_PURIFIER_SDK"]:
        raise ValueError("FreeCAD SDK changed; run freecad-purifier lock --update")
    if data.get("selection") != selection(project):
        raise ValueError(
            "extension selection changed; run freecad-purifier lock --update"
        )
    return data


def realize(project, lock, target="environment", out_link=None):
    args = [
        "nix",
        "build",
        "--impure",
        "--file",
        os.environ["FREECAD_PURIFIER_REALIZE"],
        "--argstr",
        "projectPath",
        str(project),
        "--argstr",
        "lockPath",
        str(lock),
        "--argstr",
        "target",
        target,
        "--json",
    ]
    args += ["--out-link", str(out_link)] if out_link else ["--no-link"]
    result = run(args, stdout=subprocess.PIPE, text=True)
    return Path(json.loads(result.stdout)[0]["outputs"]["out"])


def freecad_env(resources):
    env = os.environ.copy()
    env.pop("FREECAD_PURIFIER_ENVIRONMENT", None)
    env.pop("FREECAD_USER_HOME", None)
    for name, path in {
        "HOME": resources / "home",
        "XDG_CONFIG_HOME": resources / "config",
        "XDG_DATA_HOME": resources / "data",
        "XDG_CACHE_HOME": resources / "cache",
    }.items():
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_SSH_COMMAND"] = "false"
    return env


def capture(project, lock):
    import zipfile

    requested = selection(project)
    native = Path(os.environ["FREECAD_PURIFIER_NATIVE"])
    with tempfile.TemporaryDirectory(prefix="freecad-purifier-") as temporary:
        root = Path(temporary)
        request = root / "request.json"
        request.write_text(json.dumps(requested))
        url = "https://addons.freecad.org/addon_catalog_cache.zip"
        if requested["addons"]:
            fetched = json.loads(
                run(
                    ["nix", "store", "prefetch-file", "--json", url],
                    stdout=subprocess.PIPE,
                    text=True,
                ).stdout
            )
            with zipfile.ZipFile(fetched["storePath"]) as archive:
                (root / "catalog.json").write_bytes(
                    archive.read("addon_catalog_cache.json")
                )
        else:
            (root / "catalog.json").write_text("{}")
        env = freecad_env(root / "user")
        env.update(
            FREECAD_PURIFIER_REQUEST=str(request), FREECAD_PURIFIER_CAPTURE=str(root)
        )
        run(
            [
                os.environ["FREECAD_PURIFIER_CMD"],
                str(native / "freecad_purifier_capture.py"),
            ],
            env=env,
            stdin=subprocess.DEVNULL,
        )
        selected = json.loads((root / "selection.json").read_text())
        entries = []
        for name, item in sorted(selected["addons"].items()):
            source = public_url(item["url"])
            fetched = json.loads(
                run(
                    [
                        os.environ["FREECAD_PURIFIER_PREFETCH_GIT"],
                        "--url",
                        source,
                        "--rev",
                        item["rev"],
                        "--fetch-submodules",
                    ],
                    env=env,
                    stdout=subprocess.PIPE,
                    text=True,
                ).stdout
            )
            if fetched["rev"] != item["rev"]:
                raise ValueError(
                    "Nix source revision disagrees with native FreeCAD Git installation"
                )
            entries.append(
                {
                    "path": name,
                    "hash": fetched["hash"],
                    "mirrors": [],
                    "git": {
                        "url": source,
                        "rev": item["rev"],
                        "submodules": True,
                        "leaveDotGit": False,
                        "commitObject": None,
                    },
                    "freecad": {
                        key: item[key]
                        for key in [
                            "package_xml",
                            "requires",
                            "providers",
                            "external_addons",
                        ]
                    },
                }
            )
        data = {
            "version": 1,
            "purifier": "freecad",
            "sdk": os.environ["FREECAD_PURIFIER_SDK"],
            "selection": requested,
            "native": {"catalog": selected["catalog"]},
            "entries": entries,
        }
        candidate = root / "freecad-purifier.lock.json"
        candidate.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        realize(project, candidate)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=lock.parent, delete=False
        ) as output:
            output.write(candidate.read_text())
            pending = Path(output.name)
        try:
            os.replace(pending, lock)
        finally:
            pending.unlink(missing_ok=True)


def native_exec(project, lock, arguments, command="FreeCADCmd"):
    original = os.environ[
        "FREECAD_PURIFIER_CMD"
        if command.lower().endswith("cmd")
        else "FREECAD_PURIFIER_GUI"
    ]
    if not lock.exists():
        print(
            "warning: no FreeCAD purifier lock; using ordinary, impure add-on resolution",
            file=sys.stderr,
        )
        env = os.environ.copy()
        env.pop("FREECAD_PURIFIER_ENVIRONMENT", None)
        os.execve(original, [original, *arguments], env)
    validate(project, lock)
    state = project / ".freecad-purifier"
    state.mkdir(exist_ok=True)
    environment = realize(project, lock, out_link=state / "environment")
    native = Path(os.environ["FREECAD_PURIFIER_NATIVE"])
    settings = json.loads(
        run(
            [
                sys.executable,
                str(native / "freecad_purifier_prepare.py"),
                str(state),
                str(environment),
            ],
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
    )
    env = os.environ.copy()
    env.pop("FREECAD_USER_HOME", None)
    env.update(settings)
    prefix = (
        [str(native / "freecad_purifier_bootstrap.py")]
        if command.lower().endswith("cmd")
        else []
    )
    os.execve(
        original,
        [original, *prefix, *arguments],
        env,
    )


def main():
    if os.environ.get("FREECAD_PURIFIER_COMMAND") in {
        "FreeCAD",
        "FreeCADCmd",
        "freecad",
        "freecadcmd",
    }:
        project = project_path(os.environ.get("FREECAD_PURIFIER_PROJECT"))
        lock = Path(
            os.environ.get(
                "FREECAD_PURIFIER_LOCK", project / "freecad-purifier.lock.json"
            )
        ).resolve()
        native_exec(project, lock, sys.argv[1:], os.environ["FREECAD_PURIFIER_COMMAND"])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--lock")
    sub = parser.add_subparsers(dest="action", required=True)
    lock_parser = sub.add_parser("lock")
    lock_parser.add_argument("--update", action="store_true")
    sub.add_parser("prefetch")
    for name in ["build", "bundle"]:
        sub.add_parser(name)
    publish = sub.add_parser("publish")
    publish.add_argument("--tag", required=True)
    execute = sub.add_parser("exec")
    execute.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    project = project_path(args.project or os.environ.get("FREECAD_PURIFIER_PROJECT"))
    lock = Path(
        args.lock
        or os.environ.get(
            "FREECAD_PURIFIER_LOCK", project / "freecad-purifier.lock.json"
        )
    ).resolve()
    if args.action == "lock" and args.update:
        capture(project, lock)
        return
    if args.action == "exec":
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        native_exec(project, lock, arguments)
        return
    validate(project, lock)
    if args.action == "lock":
        realize(project, lock)
    elif args.action == "prefetch":
        print(realize(project, lock))
    elif args.action in {"build", "bundle"}:
        print(
            realize(project, lock, "project" if args.action == "build" else "release")
        )
    elif args.action == "publish":
        release = realize(project, lock, "release")
        run(
            [
                os.environ.get("FREECAD_PURIFIER_GH", "gh"),
                "release",
                "upload",
                args.tag,
                str(release / "freecad-project.tar.gz"),
                "--clobber",
            ]
        )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"freecad-purifier: {error}", file=sys.stderr)
        sys.exit(1)
