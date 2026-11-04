import json
import os
from pathlib import Path

import FastenersCmd
import FreeCAD

document = FreeCAD.newDocument("PurifierProof")
bolt = document.addObject("Part::FeaturePython", "Bolt")
FastenersCmd.FSScrewObject(bolt, "ISO4762", None)
bolt.Diameter = "M6"
document.recompute()
bolt.Length = "Custom"
bolt.LengthCustom = 20.0
document.recompute()
assert not bolt.Shape.isNull() and bolt.Shape.isValid()
out = Path(os.environ.get("FREECAD_PURIFIER_OUTPUT", "."))
out.mkdir(parents=True, exist_ok=True)
bolt.Shape.exportBrep(str(out / "bolt.brep"))
(out / "geometry.json").write_text(
    json.dumps(
        {"volume": bolt.Shape.Volume, "solids": len(bolt.Shape.Solids)}, sort_keys=True
    )
    + "\n"
)
