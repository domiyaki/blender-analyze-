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
    out_path = step_write_json_to_blend_dir(payload, OUT_FILE)
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


def step_write_json_to_blend_dir(payload, filename) -> Path:
    out_dir = Path(bpy.path.abspath("//"))
    out_path = out_dir / filename
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


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


# =========================================================
# UI
# =========================================================
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

        self.report({"INFO"}, f"Exported: {out_path}")
        return {"FINISHED"}


class NODE_PT_export_root_groups_json_min(bpy.types.Panel):
    bl_label = "Node JSON"
    bl_idname = "NODE_PT_export_root_groups_json_min"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Node JSON"

    def draw(self, context):
        self.layout.operator("node.export_root_groups_json_min", icon="EXPORT")


classes = (
    NODE_OT_export_root_groups_json_min,
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
