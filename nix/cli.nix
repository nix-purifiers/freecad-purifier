{
  lib,
  runCommand,
  writeText,
  makeWrapper,
  python3,
  original,
  nix-prefetch-git,
  git,
  sdk,
  nix,
  gh,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
let
  integration = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../freecad_purifier
      ../native
      ./.
    ];
  };
  realize = writeText "freecad-purifier-realize.nix" ''
    { lockPath, projectPath, target ? "environment" }:
    let
      pkgs = import (builtins.storePath "${nixpkgsSrc}") {};
      scope = import ${integration}/nix/scope.nix {
        inherit pkgs;
        nixpkgsSrc = builtins.storePath "${nixpkgsSrc}";
        purifierSrc = builtins.storePath "${purifierSrc}";
      };
      lockFile = builtins.toPath lockPath;
      src = builtins.path {
        path = builtins.toPath projectPath;
        name = "freecad-project";
        filter = path: type: !(builtins.elem (baseNameOf path) [ ".git" ".freecad-purifier" "__pycache__" "result" ]);
      };
      build = scope.buildFreecadProject { inherit src lockFile; };
    in if target == "environment" then scope.environment { lock = scope.readLock { inherit src lockFile; }; }
       else if target == "project" then build.packages.project
       else if target == "release" then build.release
       else throw "Unknown FreeCAD purifier target"
  '';
in
runCommand "freecad-purifier" { nativeBuildInputs = [ makeWrapper ]; } ''
  mkdir -p "$out/bin"
  for name in freecad-purifier FreeCAD FreeCADCmd freecad freecadcmd; do
    makeWrapper ${python3}/bin/python "$out/bin/$name" \
      --add-flags '-m freecad_purifier.main' \
      --set PYTHONPATH ${integration} \
      --set FREECAD_PURIFIER_COMMAND "$name" \
      --set FREECAD_PURIFIER_NATIVE ${integration}/native \
      --set FREECAD_PURIFIER_GUI ${original}/bin/FreeCAD \
      --set FREECAD_PURIFIER_CMD ${original}/bin/FreeCADCmd \
      --set FREECAD_PURIFIER_ORIGINAL ${original} \
      --set FREECAD_PURIFIER_PREFETCH_GIT ${nix-prefetch-git}/bin/nix-prefetch-git \
      --set FREECAD_PURIFIER_SDK ${sdk} \
      --set FREECAD_PURIFIER_REALIZE ${realize} \
      --set-default FREECAD_PURIFIER_GH ${gh}/bin/gh \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default NIX_SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --prefix PATH : ${
        lib.makeBinPath [
          nix
          gh
          git
        ]
      }
  done
''
