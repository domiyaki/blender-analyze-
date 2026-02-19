bl_info = {
    "name": "Node JSON Export (Root + Groups, Minimal)",
    "author": "ChatGPT",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "Node Editor > Sidebar (N) > Node JSON",
    "description": "Export root nodes/links + groups as independent blocks. No view. No in/out. Skips NodeFrame.",
    "category": "Node",
}

import bpy
import json
from pathlib import Path
from bpy.types import AddonPreferences
from bpy.props import StringProperty, BoolProperty

OUT_FILE = "node_export.json"


# =========================================================
# main (只看这里)
# =========================================================
def main_export(context) -> Path:
    space = step_get_node_editor_space(context)
    root_tree = step_get_visible_root_tree(space)

    root_block = step_dump_tree_as_block(root_tree)
    groups_block = step_dump_groups_as_blocks(root_tree)

    payload = step_build_payload(root_block, groups_block)
    out_path = step_write_json(payload, OUT_FILE)
    return out_path


def main_export_full(context) -> Path:
    space = step_get_node_editor_space(context)
    root_tree = step_get_visible_root_tree(space)

    root_block = step_dump_tree_as_block_full(root_tree)
    groups_block = step_dump_groups_as_blocks_full(root_tree)

    payload = step_build_payload(root_block, groups_block)
    out_path = step_write_json(payload, OUT_FILE)
    return out_path


# =========================================================
# host
# =========================================================
def step_get_node_editor_space(context):
    area = getattr(context, "area", None)
    space = getattr(context, "space_data", None)
    if not area or not space or area.type != "NODE_EDITOR":
        raise RuntimeError("Open a Node Editor area to export.")
    return space


def step_get_visible_root_tree(space):
    path = getattr(space, "path", None)
    if path and len(path) > 0:
        nt = getattr(path[-1], "node_tree", None)
        if nt:
            return nt
    nt = getattr(space, "edit_tree", None) or getattr(space, "node_tree", None)
    if not nt:
        raise RuntimeError("No visible node tree.")
    return nt


# =========================================================
# dump root/group tree blocks
# =========================================================
def step_dump_tree_as_block(nt):
    return {
        "nodes": step_dump_nodes(nt),
        "links": step_dump_links(nt),
    }


def step_dump_nodes(nt):
    nodes_out = []
    for n in nt.nodes:
        # Skip UI-only frames
        if n.bl_idname == "NodeFrame":
            continue

        nd = {
            "name": n.name,
            "type": n.bl_idname,
            **step_group_ref_if_any(n),
        }
        nodes_out.append(nd)
    return nodes_out


def step_dump_links(nt):
    links_out = []
    for l in nt.links:
        links_out.append({
            "from": [l.from_node.name, step_socket_id(l.from_socket)],
            "to":   [l.to_node.name,   step_socket_id(l.to_socket)],
        })
    return links_out


def step_dump_tree_as_block_full(nt):
    return {
        "nodes": step_dump_nodes_full(nt),
        "links": step_dump_links_full(nt),
    }


def step_dump_nodes_full(nt):
    nodes_out = []
    for n in nt.nodes:
        if n.bl_idname == "NodeFrame":
            continue

        nd = {
            "name": n.name,
            "type": n.bl_idname,
            "extra": step_node_extra_compute_only(n),
        }

        grp = step_group_ref_if_any(n)
        if "group" in grp and grp["group"] is not None:
            nd["group"] = grp["group"]

        nodes_out.append(nd)
    return nodes_out


def step_dump_links_full(nt):
    bucket = {}
    for l in nt.links:
        fn = l.from_node.name
        tn = l.to_node.name
        bucket.setdefault((fn, tn), []).append({
            "from_socket": step_socket_id(l.from_socket),
            "to_socket": step_socket_id(l.to_socket),
        })

    out = []
    for (fn, tn), conns in bucket.items():
        out.append({
            "from": fn,
            "to": tn,
            "connections": conns,
        })
    return out


def step_dump_groups_as_blocks(root_tree):
    """
    Groups are extracted as independent blocks under the root payload.
    - Only groups referenced by nodes in the root_tree are exported.
    - De-duplicates multiple instances pointing to the same group definition.
    - Does NOT inline group internals into root.
    - Skips NodeFrame inside groups as well (via shared step_dump_nodes).
    """
    groups = {}
    seen = set()

    for n in root_tree.nodes:
        if not step_is_group_node(n):
            continue
        child = getattr(n, "node_tree", None)
        if not child:
            continue

        ptr = step_tree_ptr(child)
        if ptr in seen:
            continue
        seen.add(ptr)

        groups[child.name] = {
            "nodes": step_dump_nodes(child),
            "links": step_dump_links(child),
        }

    return groups


def step_dump_groups_as_blocks_full(root_tree):
    groups = {}
    seen = set()

    for n in root_tree.nodes:
        if not step_is_group_node(n):
            continue
        child = getattr(n, "node_tree", None)
        if not child:
            continue

        ptr = step_tree_ptr(child)
        if ptr in seen:
            continue
        seen.add(ptr)

        groups[child.name] = {
            "nodes": step_dump_nodes_full(child),
            "links": step_dump_links_full(child),
        }

    return groups


def step_group_ref_if_any(node):
    if not step_is_group_node(node):
        return {}
    child = getattr(node, "node_tree", None)
    return {"group": child.name if child else None}


# =========================================================
# payload + IO
# =========================================================
def step_build_payload(root_block, groups_block):
    return {
        "root": root_block,
        "groups": groups_block,
    }


def step_write_json(payload, filename) -> Path:
    out_dir = Path(bpy.path.abspath("//"))

    prefs = step_get_addon_prefs()
    if prefs and getattr(prefs, "use_custom_dir", False):
        p = (prefs.export_dir or "").strip()
        if p:
            out_dir = Path(bpy.path.abspath(p))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    out_path.write_text(json_text, encoding="utf-8")

    if prefs and getattr(prefs, "copy_to_clipboard", True):
        bpy.context.window_manager.clipboard = json_text

    return out_path


def step_get_addon_prefs():
    try:
        return bpy.context.preferences.addons[__name__].preferences
    except Exception:
        return None


# =========================================================
# helpers
# =========================================================
def step_socket_id(sock):
    return getattr(sock, "identifier", None) or sock.name


def step_is_group_node(node):
    bid = getattr(node, "bl_idname", "") or ""
    return bid.endswith("NodeGroup") or bid == "NodeGroup" or hasattr(node, "node_tree")


def step_tree_ptr(nt):
    try:
        return nt.as_pointer()
    except Exception:
        return id(nt)


_EXTRA_PROP_CACHE = {}
_EXTRA_SKIP_IDS = {
    "rna_type",
    "name",
    "label",
    "location",
    "width",
    "height",
    "hide",
    "mute",
    "select",
    "color",
    "use_custom_color",
    "parent",
}
_EXTRA_ALLOW_TYPES = {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}


def step_node_extra_compute_only(node) -> dict:
    """
    Extract compute-relevant RNA props:
    - allow BOOLEAN/INT/FLOAT/STRING/ENUM (and simple arrays)
    - skip bl_* metadata, type/bl_static_type, and UI/editor-state fields
    - per-prop try/except to stay resilient
    """
    try:
        rna = getattr(node, "bl_rna", None)
        if not rna:
            return {}

        key = getattr(node, "bl_idname", None) or node.__class__.__name__
        prop_ids = _EXTRA_PROP_CACHE.get(key)

        if prop_ids is None:
            prop_ids = []
            for prop in rna.properties:
                pid = getattr(prop, "identifier", None)
                if not pid:
                    continue

                if pid.startswith("bl_"):
                    continue
                if pid in {"type", "bl_static_type"}:
                    continue
                if pid in {
                    "rna_type",
                    "name",
                    "label",
                    "select",
                    "parent",
                    "color",
                    "use_custom_color",
                    "warning_propagation",
                    "color_tag",
                    "dimensions",
                    "location",
                    "location_absolute",
                }:
                    continue
                if pid.startswith("show_") or pid.startswith("ui_"):
                    continue
                if pid in _EXTRA_SKIP_IDS:
                    continue

                ptype = getattr(prop, "type", None)
                if ptype not in _EXTRA_ALLOW_TYPES:
                    continue
                if getattr(prop, "is_hidden", False):
                    continue

                prop_ids.append(pid)

            _EXTRA_PROP_CACHE[key] = prop_ids

        extra = {}
        for pid in prop_ids:
            try:
                val = getattr(node, pid)
            except Exception:
                continue

            v = _jsonable_shallow(val)
            if v is not None:
                extra[pid] = v

        return extra
    except Exception:
        return {}


def _jsonable_shallow(val):
    if val is None or isinstance(val, (bool, int, float, str)):
        return val

    try:
        if hasattr(val, "__len__") and not isinstance(val, (str, bytes)):
            arr = list(val)
            out = []
            for x in arr:
                if x is None or isinstance(x, (bool, int, float, str)):
                    out.append(x)
                else:
                    return None
            return out
    except Exception:
        return None

    return None


def step_node_props(node):
    """
    Add general-purpose node info that exists across editors
    (Geometry/Shader/Compositor/Texture). Uses getattr to stay safe.
    """
    loc = getattr(node, "location", None)
    try:
        loc_out = [float(loc[0]), float(loc[1])] if loc is not None else None
    except Exception:
        loc_out = None

    dims = None
    w = getattr(node, "width", None)
    h = getattr(node, "height", None)
    if isinstance(w, (int, float)) and isinstance(h, (int, float)):
        dims = [float(w), float(h)]

    color = None
    if getattr(node, "use_custom_color", False):
        col = getattr(node, "color", None)
        try:
            color = [float(col[0]), float(col[1]), float(col[2])] if col is not None else None
        except Exception:
            color = None

    data = {
        "label": getattr(node, "label", None) or None,
        "location": loc_out,
        "dimensions": dims,
        "hide": bool(getattr(node, "hide", False)),
        "mute": bool(getattr(node, "mute", False)) if hasattr(node, "mute") else False,
        "color": color,
    }
    # Remove None entries to keep output compact.
    return {k: v for k, v in data.items() if v is not None}


# =========================================================
# UI
# =========================================================
class NTJSON_AddonPreferences(AddonPreferences):
    bl_idname = __name__

    use_custom_dir: BoolProperty(
        name="Use custom export directory",
        description="If enabled, export JSON to the directory below instead of the .blend directory",
        default=False,
    )

    export_dir: StringProperty(
        name="Export directory",
        description="Directory where JSON files will be written",
        subtype="DIR_PATH",
        default="",
    )

    copy_to_clipboard: BoolProperty(
        name="Copy exported JSON to clipboard",
        description="Automatically copy generated JSON text to clipboard after export",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_custom_dir")
        col = layout.column()
        col.enabled = self.use_custom_dir
        col.prop(self, "export_dir")
        layout.separator()
        layout.prop(self, "copy_to_clipboard")


class NODE_OT_export_root_groups_json_min(bpy.types.Operator):
    bl_idname = "node.export_root_groups_json_min"
    bl_label = "Export Node JSON (Minimal)"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            out_path = main_export(context)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        prefs = step_get_addon_prefs()
        if prefs and getattr(prefs, "copy_to_clipboard", True):
            self.report({"INFO"}, f"Copied to clipboard(exported: {out_path})")
        else:
            self.report({"INFO"}, f"Exported: {out_path}")
        return {"FINISHED"}


class NODE_OT_export_root_groups_json_full(bpy.types.Operator):
    bl_idname = "node.export_root_groups_json_full"
    bl_label = "Export Node JSON (Full)"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            out_path = main_export_full(context)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        prefs = step_get_addon_prefs()
        if prefs and getattr(prefs, "copy_to_clipboard", True):
            self.report({"INFO"}, f"Copied to clipboard(exported: {out_path})")
        else:
            self.report({"INFO"}, f"Exported: {out_path}")
        return {"FINISHED"}


class NODE_PT_export_root_groups_json_min(bpy.types.Panel):
    bl_label = "NT JSON"
    bl_idname = "NODE_PT_export_root_groups_json_min"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "NT JSON"

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("node.export_root_groups_json_min", icon="EXPORT", text="Export to JSON(Min)")
        col.operator("node.export_root_groups_json_full", icon="EXPORT", text="Export to JSON(Full)")


classes = (
    NTJSON_AddonPreferences,
    NODE_OT_export_root_groups_json_min,
    NODE_OT_export_root_groups_json_full,
    NODE_PT_export_root_groups_json_min,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
