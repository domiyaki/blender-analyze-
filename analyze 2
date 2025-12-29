
import bpy, json
from pathlib import Path

# ===== 用户配置 =====
# 1) 最稳：指定要导出的 Geometry Nodes modifier 名称；留空则自动选择
MOD_NAME = ""  # 例如 "GeometryNodes.003"

# 2) 输出文件后缀
FILE_SUFFIX = "gn_ai"

# 3) socket 是否保留可读 name（会增大文件；默认 False）
INCLUDE_SOCKET_NAME = False

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

def dump_socket(s, is_input: bool):
    """
    精简 socket：
    - 必留：identifier + socket_type
    - default_value：只在“输入且未连接”时保留（对理解常量/默认值很关键）
    """
    d = {
        "identifier": getattr(s, "identifier", s.name),
        "socket_type": socket_type(s),
    }
    if INCLUDE_SOCKET_NAME:
        d["name"] = s.name

    if is_input and hasattr(s, "default_value") and not getattr(s, "is_linked", False):
        try:
            d["default_value"] = s.default_value
        except Exception:
            pass

    return d

def dump_node_params(n):
    """
    节点语义参数白名单（只保留影响语义/求值的字段）。
    你可以按需要继续扩展 keep_by_type。
    """
    t = n.bl_idname

    keep_by_type = {
        # Math / 常用算子
        "ShaderNodeVectorMath": {"operation"},
        "ShaderNodeMath": {"operation", "use_clamp"},

        # GN 常用节点
        "GeometryNodeStoreNamedAttribute": {"data_type", "domain"},
        "GeometryNodeCaptureAttribute": {"data_type", "domain"},  # 若你用 Capture
        "GeometryNodeObjectInfo": {"transform_space"},
        "GeometryNodeSwitch": {"input_type"},

        # 组织/布线节点（可选）
        "NodeReroute": {"socket_idname"},     # 只在你想知道 reroute 携带类型时保留
        "NodeFrame": {"shrink", "label_size"} # Frame 是否收缩等（不影响计算；仅用于布局/阅读）
    }

    keep = keep_by_type.get(t, set())
    if not keep:
        return {}

    params = {}
    for k in keep:
        try:
            params[k] = getattr(n, k)
        except Exception:
            pass
    return params

def choose_gn_modifier(obj):
    """选择要导出的 NODES modifier：MOD_NAME > active > first"""
    if obj is None:
        raise RuntimeError("没有选中对象：请先在 3D 视图选中带 Geometry Nodes 的对象。")

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

    # 2) 尝试活动 modifier（在某些上下文可用）
    active_mod = getattr(obj.modifiers, "active", None)
    if active_mod and active_mod.type == 'NODES':
        return active_mod

    # 3) 回退：第一个 NODES modifier
    return nodes_mods[0]

def export_node_tree_to_json_ai(node_tree, out_path: Path):
    # 给每个 node 一个稳定 id（按 node_tree.nodes 的顺序）
    node_list = list(node_tree.nodes)
    node_id_map = {n: i for i, n in enumerate(node_list)}

    nodes_out = []
    for n in node_list:
        nodes_out.append({
            "id": node_id_map[n],
            "name": n.name,
            "label": n.label if n.label else "",
            "type": n.bl_idname,
            "params": dump_node_params(n),
            "inputs": [dump_socket(s, is_input=True) for s in n.inputs],
            "outputs": [dump_socket(s, is_input=False) for s in n.outputs],
        })

    links_out = []
    for l in node_tree.links:
        links_out.append({
            "from_id": node_id_map[l.from_node],
            "from_socket": getattr(l.from_socket, "identifier", l.from_socket.name),
            "to_id": node_id_map[l.to_node],
            "to_socket": getattr(l.to_socket, "identifier", l.to_socket.name),
        })

    data = {
        "schema": "blender-geometry-nodes-graph@1",
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

export_node_tree_to_json_ai(ng, out_path)
