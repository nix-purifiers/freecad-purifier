{ runCommand, original }:
runCommand "freecad-purifier-addon-manager" { } ''
  cp -rs ${original}/Mod/AddonManager "$out"
  chmod u+w "$out"
  rm "$out/Init.py"
  cp ${../native/freecad_purifier_init.py} "$out/Init.py"
  cp ${../native/freecad_purifier_guard.py} "$out/freecad_purifier_guard.py"
''
