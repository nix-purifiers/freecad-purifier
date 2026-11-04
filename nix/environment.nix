{
  lib,
  runCommand,
  writeText,
  fetchurl,
  fetchgit,
  python3,
  original,
  manager,
  purifier,
  sdk,
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  tree = purifier.tree (
    {
      name = "freecad-locked-git-sources";
      entries = checked.entries;
      inherit
        runCommand
        writeText
        fetchurl
        fetchgit
        python3
        ;
    }
    // fetchers
  );
  context = writeText "freecad-lock.json" (builtins.toJSON checked.data);
  installed = runCommand "freecad-native-workbenches" { } ''
    export HOME="$TMPDIR/home" XDG_CONFIG_HOME="$TMPDIR/config" XDG_DATA_HOME="$TMPDIR/data" XDG_CACHE_HOME="$TMPDIR/cache" QT_QPA_PLATFORM=offscreen
    export FREECAD_PURIFIER_ORIGINAL=${original} FREECAD_PURIFIER_LOCK_DATA=${context} FREECAD_PURIFIER_TREE=${tree}
    mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$out"
    ${original}/bin/FreeCADCmd ${../native}/freecad_purifier_install.py </dev/null
    test -d "$out/modules"
  '';
in
assert lib.assertMsg (checked.data.sdk == sdk) "FreeCAD SDK changed; update the purifier lock";
runCommand "freecad-locked-environment" { passthru = { inherit tree installed; }; } ''
  mkdir -p "$out"
  ln -s ${installed}/modules "$out/modules"
  ln -s ${manager} "$out/manager"
  ln -s ${context} "$out/lock.json"
''
