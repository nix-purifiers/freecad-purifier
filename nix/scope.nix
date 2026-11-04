{
  pkgs,
  nixpkgsSrc,
  purifierSrc,
}:
pkgs.lib.makeScope pkgs.newScope (scope: {
  original = pkgs.freecad;
  manager = scope.callPackage ./manager.nix { };
  purifier = import (purifierSrc + "/nix/lib") { inherit (pkgs) lib; };
  readLock = import ./read-lock.nix { inherit (pkgs) lib; };
  environment = scope.callPackage ./environment.nix { };
  cli = scope.callPackage ./cli.nix { inherit nixpkgsSrc purifierSrc; };
  buildFreecadProject = scope.callPackage ./build-project.nix { };
  sdk = builtins.hashString "sha256" (
    builtins.toJSON {
      nixpkgs = toString nixpkgsSrc;
      native = builtins.mapAttrs (name: _: builtins.hashFile "sha256" (../native + ("/" + name))) (
        pkgs.lib.filterAttrs (_: type: type == "regular") (builtins.readDir ../native)
      );
      providers = pkgs.lib.genAttrs [ "scope.nix" "environment.nix" "manager.nix" ] (
        name: builtins.hashFile "sha256" (./. + ("/" + name))
      );
    }
  );
})
