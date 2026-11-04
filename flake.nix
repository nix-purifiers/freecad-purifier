{
  description = "FreeCAD with locked, Nix-resolved add-ons";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        freecad-purifier = import ./nix/scope.nix {
          pkgs = final;
          nixpkgsSrc = nixpkgs;
          purifierSrc = purifier;
        };
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (
        system:
        let
          p = (pkgsFor system).freecad-purifier;
        in
        {
          default = p.cli;
          freecad = p.original;
          xvfb = (pkgsFor system).xvfb-run;
        }
      );
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/freecad-purifier";
        };
      });
      lib.freecad-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
      checks = forAll (
        system:
        let
          p = (pkgsFor system).freecad-purifier;
          build = p.buildFreecadProject { src = ./examples/minimal; };
        in
        {
          cli = p.cli;
          inherit (build.packages) environment project;
          release = build.release;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}
