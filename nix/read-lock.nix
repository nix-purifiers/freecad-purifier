{ lib }:
{
  src,
  lockFile ? src + "/freecad-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  component =
    s:
    builtins.isString s
    && builtins.match "[A-Za-z0-9_+-][A-Za-z0-9_.+-]*" s != null
    && lib.toLower s != "addonmanager";
  selection =
    if builtins.pathExists (src + "/freecad-purifier.json") then
      builtins.fromJSON (builtins.readFile (src + "/freecad-purifier.json"))
    else
      null;
  valid =
    (data.version or null) == 1
    && (data.purifier or null) == "freecad"
    && builtins.isString (data.sdk or null)
    && builtins.isAttrs (data.selection or null)
    && data.selection == selection
    && builtins.isList (data.selection.addons or null)
    && builtins.all component data.selection.addons
    && builtins.isAttrs (data.native or null)
    && builtins.isAttrs (data.native.catalog or null)
    && builtins.isList entries
    && builtins.all (
      e:
      builtins.isAttrs e
      && component (e.path or null)
      && builtins.isAttrs (e.git or null)
      && builtins.isString (e.git.url or null)
      && lib.hasPrefix "https://" e.git.url
      && builtins.isString (e.git.rev or null)
      && builtins.match "[0-9a-f]{40}" e.git.rev != null
      && (e.git.submodules or null) == true
      && builtins.isString (e.hash or null)
      && builtins.match "sha256-[A-Za-z0-9+/]{43}=" e.hash != null
      && builtins.isAttrs (e.freecad or null)
      && builtins.isString (e.freecad.package_xml or null)
      && builtins.isAttrs (e.freecad.providers or null)
      && builtins.isList (e.freecad.requires or null)
      && builtins.isList (e.freecad.external_addons or null)
    ) entries
    && builtins.length (lib.unique (map (e: e.path) entries)) == builtins.length entries
    &&
      builtins.sort builtins.lessThan (map (e: e.path) entries) == builtins.attrNames data.native.catalog
    && builtins.all (id: builtins.hasAttr id data.native.catalog) data.selection.addons;
in
{
  purifier = "freecad";
  inherit data entries;
  problems = lib.optional (
    !valid
  ) "FreeCAD lock is missing, malformed, or stale; run freecad-purifier lock --update";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
