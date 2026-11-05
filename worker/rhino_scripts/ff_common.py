"""Pure-Python scene and assignment helpers shared by Rhino scripts.

Keep this module compatible with Rhino's IronPython 2.7 as well as CPython.
The stable keys are based on the definition, layer and geometry, never Rhino's
per-import document IDs. Identical, coincident objects intentionally share a key.
"""
from __future__ import division

import hashlib
import json
import math

SCHEMA = "rhino-geometry-v1"
MAX_PREVIEW_VERTICES = 1500000
MAX_PREVIEW_INDICES = 6000000


def part_key(owner, layer, kind, crc, bbox, name):
    """Identify a definition object (or a top-level object) across imports.

    A CRC is combined with type, name and high-precision local-space bounds. If two
    source objects are indistinguishable, they are explicitly treated as a group.
    """
    bounds = [round(float(v), 7) for v in bbox["min"] + bbox["max"]]
    value = [owner or "", layer, kind, str(crc), bounds, name or ""]
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return "ffp_" + hashlib.sha256(encoded).hexdigest()[:32]


def union_bbox(a, b):
    if a is None:
        return {"min": list(b["min"]), "max": list(b["max"])}
    return {"min": [min(a["min"][i], b["min"][i]) for i in range(3)],
            "max": [max(a["max"][i], b["max"][i]) for i in range(3)]}


class SceneBuilder(object):
    """Collect discovered parts and optional model-space preview geometry."""
    def __init__(self, include_geometry=True):
        self.include_geometry = include_geometry
        self.parts = {}
        self.order = []
        self.blocks = {}
        self.layers = {}
        self.occurrences = []
        self.unsupported = []
        self.extents = None
        self.vertices = 0
        self.indices = 0
        self.partial = False
        self.warnings = []

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def add_block(self, name):
        block = self.blocks.setdefault(name, {"name": name, "instance_count": 0,
                                             "layers": set(), "part_ids": set()})
        block["instance_count"] += 1

    def add_unsupported(self, layer, ancestors, kind):
        self.unsupported.append({"layer": layer, "ancestors": list(ancestors), "kind": kind})
        if self.include_geometry:
            self.partial = True
            self.warn("Some unsupported Rhino object types are omitted from the interactive preview.")

    def add_leaf(self, key, name, layer, color, owner, ancestors, bbox,
                 renderable, source_id, scaled=False, positions=None,
                 triangles=None, lines=None):
        part = self.parts.get(key)
        if part is None:
            part = {"id": key, "name": name, "layer": layer, "block": owner,
                    "requires_block_edit": bool(owner), "bbox": None,
                    "block_ancestors": set(), "block_paths": set(), "occurrence_count": 0,
                    "renderable": bool(renderable), "source_ids": set(),
                    "positions": [], "triangles": [], "lines": []}
            self.parts[key] = part
            self.order.append(key)
        elif part["renderable"] != bool(renderable):
            raise ValueError("ambiguous geometry identity: " + key)
        part["bbox"] = union_bbox(part["bbox"], bbox)
        part["block_ancestors"].update(ancestors)
        part["block_paths"].add(tuple(ancestors))
        part["occurrence_count"] += 1
        part["source_ids"].add(str(source_id))
        self.extents = union_bbox(self.extents, bbox)
        self.layers.setdefault(layer, {"name": layer, "color": color, "part_ids": set()})["part_ids"].add(key)
        for block_name in ancestors:
            if block_name not in self.blocks:
                raise ValueError("block was not registered: " + block_name)
            self.blocks[block_name]["layers"].add(layer)
            self.blocks[block_name]["part_ids"].add(key)
        self.occurrences.append({"key": key, "layer": layer, "owner": owner,
                                 "ancestors": list(ancestors), "renderable": bool(renderable),
                                 "scaled": bool(scaled), "bbox": bbox})
        if not self.include_geometry:
            return
        positions, triangles, lines = positions or [], triangles or [], lines or []
        if not positions or not (triangles or lines):
            self.partial = True
            self.warn("Some geometry could not be meshed for the interactive preview.")
            return
        if (self.vertices + len(positions) // 3 > MAX_PREVIEW_VERTICES or
                self.indices + len(triangles) + len(lines) > MAX_PREVIEW_INDICES):
            self.partial = True
            self.warn("The interactive preview hit its geometry limit; some objects are omitted.")
            return
        base = len(part["positions"]) // 3
        part["positions"].extend(positions)
        part["triangles"].extend([base + i for i in triangles])
        part["lines"].extend([base + i for i in lines])
        self.vertices += len(positions) // 3
        self.indices += len(triangles) + len(lines)

    def structure(self, source_file):
        if not self.order:
            raise ValueError("No supported geometry was found in the model.")
        parts = []
        for key in self.order:
            p = self.parts[key]
            parts.append({"id": p["id"], "name": p["name"], "layer": p["layer"],
                          "block": p["block"], "requires_block_edit": p["requires_block_edit"],
                          "bbox": p["bbox"], "block_ancestors": sorted(p["block_ancestors"]),
                          "block_paths": [list(path) for path in sorted(p["block_paths"])],
                          "occurrence_count": p["occurrence_count"],
                          "matching_objects": len(p["source_ids"]),
                          "renderable": p["renderable"]})
        layers = [{"name": d["name"], "color": d["color"], "part_count": len(d["part_ids"])}
                  for _, d in sorted(self.layers.items())]
        blocks = [{"name": d["name"], "instance_count": d["instance_count"],
                   "layers": sorted(d["layers"]), "part_ids": sorted(d["part_ids"])}
                  for _, d in sorted(self.blocks.items())]
        return {"units": "inches", "source_file": source_file,
                "analyzer": "rhino8-worker 2.0", "target_schema": SCHEMA,
                "extents": self.extents, "layers": layers, "blocks": blocks, "parts": parts,
                "geometry_status": "partial" if self.partial else "complete",
                "geometry_warnings": list(self.warnings)}

    def geometry(self):
        return {"version": 1, "units": "inches", "parts": [
            {"id": key, "positions": self.parts[key]["positions"],
             "triangles": self.parts[key]["triangles"], "lines": self.parts[key]["lines"]}
            for key in self.order if self.parts[key]["positions"]]}


def _assignment_value(a):
    finish = a.get("finish") or {}
    if finish.get("id") is None:
        raise ValueError("A finish assignment no longer has a valid finish.")
    try:
        scale = float(a.get("scale_multiplier", 1))
        width = float(finish.get("swatch_width_in", 0))
        height = float(finish.get("swatch_height_in", 0))
    except (ValueError, TypeError):
        raise ValueError("Finish dimensions and scale must be numbers.")
    if not all(math.isfinite(v) if hasattr(math, "isfinite") else not (math.isnan(v) or math.isinf(v))
               for v in (scale, width, height)) or min(scale, width, height) <= 0:
        raise ValueError("Finish dimensions and scale must be finite and greater than zero.")
    return (str(finish["id"]), scale)


def plan_assignments(scene, assignments):
    """Resolve part > nearest block > layer and reject shared-definition conflicts.

    scene is a SceneBuilder containing *all* occurrences, including unassigned ones.
    A definition edit affects every occurrence; a conflicting override must not be
    allowed to silently recolor a different instance.
    """
    by_kind = {"part": {}, "block": {}, "layer": {}}
    valid = {"part": set(scene.parts), "block": set(scene.blocks), "layer": set(scene.layers)}
    blocks_with_geometry = set(block for occ in scene.occurrences for block in occ["ancestors"])
    for a in assignments:
        kind, target = a.get("target_kind"), a.get("target_name")
        if kind not in by_kind or target not in valid[kind]:
            raise ValueError("Assignment target %s:%s is stale or missing; re-analyze and remap it." % (kind, target))
        if kind == "block" and target not in blocks_with_geometry:
            raise ValueError("Block '%s' has no supported geometry to receive a finish." % target)
        if target in by_kind[kind]:
            raise ValueError("Duplicate assignment for %s:%s." % (kind, target))
        _assignment_value(a)
        by_kind[kind][target] = a

    for obj in scene.unsupported:
        if (obj["layer"] in by_kind["layer"] or
                any(block in by_kind["block"] for block in obj["ancestors"])):
            raise ValueError("An assigned layer or block contains unsupported '%s' geometry. "
                             "Assign only supported individual surfaces/meshes instead." % obj["kind"])

    result = {}
    chosen_values = {}
    for occ in scene.occurrences:
        key = occ["key"]
        selected = by_kind["part"].get(key)
        if selected is None:
            for block in reversed(occ["ancestors"]):
                selected = by_kind["block"].get(block)
                if selected is not None:
                    break
        if selected is None:
            selected = by_kind["layer"].get(occ["layer"])
        value = _assignment_value(selected) if selected else None
        if key in chosen_values and chosen_values[key] != value:
            raise ValueError("Conflicting finishes on shared block geometry '%s'. "
                             "A BlockEdit affects all references; use consistent assignments "
                             "or make the block definitions unique in Rhino." % scene.parts[key]["name"])
        chosen_values[key] = value
        if selected is not None:
            if not occ["renderable"]:
                raise ValueError("'%s' is curve/linework, not a renderable surface. "
                                 "Assign finishes to surfaces or meshes instead." % scene.parts[key]["name"])
            if occ["scaled"]:
                raise ValueError("'%s' is in a scaled block instance. Real-world texture size "
                                 "cannot yet be verified for scaled instances." % scene.parts[key]["name"])
            result[key] = selected
    # Overridden lower-priority rules are harmless; they need not be selected.
    return result



def topology_signature(scene):
    """Detect lost, added, moved or re-parented geometry after BlockEdit."""
    supported = [("supported", occ["key"], occ["layer"], occ["owner"] or "",
                  tuple(occ["ancestors"]), occ["scaled"],
                  tuple(round(float(v), 7) for v in occ["bbox"]["min"] + occ["bbox"]["max"]))
                 for occ in scene.occurrences]
    unsupported = [("unsupported", obj["kind"], obj["layer"], "",
                    tuple(obj["ancestors"]), False, ()) for obj in scene.unsupported]
    return sorted(supported + unsupported)


def match_editable_copies(before_ids, candidates, expected):
    """Return newly created, unlocked BlockEdit copies after exact count checks.

    Candidates are dictionaries with id, key and locked fields. Existing document
    objects are never returned, even if they have a matching geometry fingerprint.
    """
    before = set(str(oid) for oid in before_ids)
    copies = {}
    for candidate in candidates:
        if str(candidate["id"]) in before or candidate.get("locked"):
            continue
        key = candidate.get("key")
        if key in expected:
            copies.setdefault(key, []).append(candidate["id"])
    actual = {key: len(ids) for key, ids in copies.items()}
    if actual != expected:
        raise ValueError("BlockEdit copies differ from the original definition "
                         "(expected %s, found %s)." % (expected, actual))
    return copies
