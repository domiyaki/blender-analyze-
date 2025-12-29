import bpy, json
from pathlib import Path

# ===== 用户配置 =====
# 1) 最稳：直接指定要导出的 Geometry Nodes modifier 名称（留空则自动选择）
MOD_NAME = ""  # 例如 "GeometryNodes.003"

# 2) 输出文件名后缀（可留空）
FILE_SUFFIX = "gn_export"

# ===== JSON 兜底：序列化 Blender / mathutils 类型 =====
def to_json_default(obj):
    # mathutils.Vector/Color/Euler/Quaternion/Matrix，bpy_prop_array 等通常可迭代
    try:
        if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
            return [to_json_default(x) for x in list(obj)]
    except Exception:
        pass

    # Blender 的 ID 数据块尽量用 name
    try:
        if hasattr(obj, "name"):
            return obj.name
    except Exception:
        pass

    return str(obj)

def socket_type(s):
    # Blender 5.0 兼容：不同 socket 可能没有 bl_socket_idname
    return (
        getattr(s, "bl_socket_idname", None) or
        getattr(s, "bl_idname", None) or
        getattr(s, "type", None) or
        type(s).__name__
    )

def dump_socket(s):
    d = {
        "name": s.name,
        "identifier": getattr(s, "identifier", s.name),
        "socket_type": socket_type(s),
        "enabled": getattr(s, "enabled", True),
        "is_linked": getattr(s, "is_linked", False),
        "hide": getattr(s, "hide", False),
    }
    # default_value 可能是 Vector/Color 等，交给 json default 处理
    if hasattr(s, "default_value"):
        try:
            d["default_value"] = s.default_value
        except Exception:
            pass
    return d

def dump_node_props(n):
    props = {}
    # 仅导出相对稳定且可解释的属性；复杂对象交给 json default
    skip = {"name", "label", "location", "select", "width", "height", "mute", "hide"}
    for p in n.bl_rna.properties:
        if p.is_readonly or p.identifier in skip:
            continue
        try:
            val = getattr(n, p.identifier)
        except Exception:
            continue

        if p.type in {"BOOLEAN", "INT", "FLOAT", "STRING", "ENUM"}:
            props[p.identifier] = val
    return props

def choose_gn_modifier(obj):
    """选择要导出的 NODES modifier：MOD_NAME > active > first"""
    if obj is None:
        raise RuntimeError("没有选中对象：请先在 3D 视图选中带 Geometry Nodes 的对象。")

    # 取所有 NODES modifiers
    nodes_mods = [m for m in obj.modifiers if m.type == 'NODES']
    if not nodes_mods:
        raise RuntimeError(f"对象 {obj.name} 没有 Geometry Nodes (NODES) modifier。")

    # 1) 用户指定名称
    if MOD_NAME:
        mod = obj.modifiers.get(MOD_NAME)
        if not mod:
            raise RuntimeError(f"找不到名为 {MOD_NAME} 的 modifier。请检查名称是否完全一致。")
        if mod.type != 'NODES':
            raise RuntimeError(f"{MOD_NAME} 存在，但不是 NODES 类型。")
        return mod

    # 2) 尝试活动 modifier（若上下文可用）
    active_mod = getattr(obj.modifiers, "active", None)
    if active_mod and active_mod.type == 'NODES':
        return active_mod

    # 3) 回退：第一个 NODES modifier
    return nodes_mods[0]

def export_node_tree_to_json(node_tree, out_path: Path):
    # 给每个 node 一个稳定 id（按 node_tree.nodes 的顺序）
    node_list = list(node_tree.nodes)
    node_id_map = {n: i for i, n in enumerate(node_list)}

    nodes_out = []
    for n in node_list:
        nodes_out.append({
            "id": node_id_map[n],
            "name": n.name,
            "label": n.label,
            "type": n.bl_idname,
            "props": dump_node_props(n),
            "inputs": [dump_socket(s) for s in n.inputs],
            "outputs": [dump_socket(s) for s in n.outputs],
        })

    links_out = []
    for l in node_tree.links:
        links_out.append({
            "from_id": node_id_map[l.from_node],
            "from_node": l.from_node.name,
            "from_socket": getattr(l.from_socket, "identifier", l.from_socket.name),
            "to_id": node_id_map[l.to_node],
            "to_node": l.to_node.name,
            "to_socket": getattr(l.to_socket, "identifier", l.to_socket.name),
        })

    data = {
        "node_tree_name": node_tree.name,
        "nodes": nodes_out,
        "links": links_out,
    }

    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=to_json_default),
        encoding="utf-8"
    )

    print("Exported JSON:", str(out_path))
    print("Nodes:", len(nodes_out), "Links:", len(links_out))

# ===== main =====
obj = bpy.context.object
mod = choose_gn_modifier(obj)

ng = mod.node_group
if ng is None:
    raise RuntimeError("该 NODES modifier 没有关联 node_group（可能为空/损坏）。")

# 输出目录：blend 同目录；建议先保存 blend
out_dir = Path(bpy.path.abspath("//"))
fname = f"{ng.name}_{FILE_SUFFIX}.json" if FILE_SUFFIX else f"{ng.name}.json"
out_path = out_dir / fname

export_node_tree_to_json(ng, out_path)
