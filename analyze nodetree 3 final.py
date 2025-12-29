import bpy, json
from pathlib import Path

# ===== 用户配置 =====
MOD_NAME = ""                 # 例如 "GeometryNodes.003"，留空则自动选择
FILE_SUFFIX = "gn_export"     # 输出文件名后缀

EXPORT_ABS_POS = True         # 默认开启：导出节点绝对位置（x,y）
EXPORT_FRAMES = True          # 默认开启：单独导出 frames 第三块

INCLUDE_SOCKET_NAME = True    # socket 是否保留可读 name（建议 True，便于人工校验）
INCLUDE_NODE_LABEL = True     # node.label 是否保留（建议 True）

# ===== params 白名单：只保留高信息密度字段 =====
PARAM_WHITELIST = {
    # 你明确要的
    "operation", "domain", "data_type", "input_type", "transform_space",
    # 常见扩展（不同节点会用到不同字段名）
    "mode", "interpolation", "clamp", "axis",
    "use_clamp", "space", "coordinate_space",
}

# ===== JSON 兜底：序列化 Blender / mathutils 类型 =====
def to_json_default(obj):
    try:
        if hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes)):
            return [to_json_default(x) for x in list(obj)]
    except Exception:
        pass

    try:
        if hasattr(obj, "name"):
            return obj.name
    except Exception:
        pass

    return str(obj)

def socket_type(s):
    return (
        getattr(s, "bl_socket_idname", None) or
        getattr(s, "bl_idname", None) or
        getattr(s, "type", None) or
        type(s).__name__
    )

def abs_node_pos(n):
    """
    计算 Node Editor 的“绝对位置”：
    - Blender 中 node.location 对 parent frame 可能是相对值
    - 绝对位置 = 自己 location + 所有祖先 frame 的 location 累加
    """
    x = float(getattr(n.location, "x", 0.0))
    y = float(getattr(n.location, "y", 0.0))
    p = getattr(n, "parent", None)
    # parent 链一般只会是 Frame
    while p is not None:
        try:
            x += float(p.location.x)
            y += float(p.location.y)
        except Exception:
            break
        p = getattr(p, "parent", None)
    return [x, y]

def dump_socket(s, is_input: bool):
    """
    面向理解的最小 socket 定义：
    - identifier：links 端点对齐用
    - socket_type：类型提示（Geometry/Vector/Float/Bool/String/Object...)
    - default_value：仅当输入未连接时保留（常量语义关键）
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
    只导出白名单 params，避免 UI 噪声。
    """
    params = {}
    for key in PARAM_WHITELIST:
        try:
            # 只取简单值；复杂对象不在白名单范围内
            if hasattr(n, key):
                val = getattr(n, key)
                # RNA 中部分字段可能是 None 或不可序列化类型，交给 json default 兜底
                params[key] = val
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

    if MOD_NAME:
        mod = obj.modifiers.get(MOD_NAME)
        if not mod:
            raise RuntimeError(f"找不到名为 {MOD_NAME} 的 modifier。请检查名称是否完全一致。")
        if mod.type != 'NODES':
            raise RuntimeError(f"{MOD_NAME} 存在，但不是 NODES 类型。")
        return mod

    active_mod = getattr(obj.modifiers, "active", None)
    if active_mod and active_mod.type == 'NODES':
        return active_mod

    return nodes_mods[0]

def export_frames_block(node_tree):
    """
    方案二：frames 独立第三块，不插入 nodes/links。
    输出每个 Frame 的：
    - name/label
    - pos_abs（可选）
    - parent_frame（若 frame 嵌套 frame）
    - children_nodes：直接子节点（parent 指向该 frame 的节点 name 列表）
    - child_frames：直接子 frame 列表
    """
    frames = [n for n in node_tree.nodes if n.bl_idname == "NodeFrame"]
    if not frames:
        return []

    # 建索引：frame -> children nodes
    children_nodes_map = {f: [] for f in frames}
    children_frames_map = {f: [] for f in frames}

    for n in node_tree.nodes:
        p = getattr(n, "parent", None)
        if p is None:
            continue
        if p in children_nodes_map:
            # 直接挂在某个 frame 下
            children_nodes_map[p].append(n.name)

    for f in frames:
        pf = getattr(f, "parent", None)
        if pf is not None and pf.bl_idname == "NodeFrame":
            # frame 嵌套
            if pf in children_frames_map:
                children_frames_map[pf].append(f.name)

    out = []
    for f in frames:
        fd = {
            "name": f.name,
            "label": f.label or "",
            "parent_frame": getattr(getattr(f, "parent", None), "name", None),
            "children_nodes": children_nodes_map.get(f, []),
            "child_frames": children_frames_map.get(f, []),
        }
        if EXPORT_ABS_POS:
            fd["pos"] = abs_node_pos(f)
        out.append(fd)

    return out

def export_node_tree_to_json(node_tree, out_path: Path):
    nodes_out = []
    for n in node_tree.nodes:
        nd = {
            "name": n.name,
            "type": n.bl_idname,
            "params": dump_node_params(n),
            "inputs": [dump_socket(s, is_input=True) for s in n.inputs],
            "outputs": [dump_socket(s, is_input=False) for s in n.outputs],
        }
        if INCLUDE_NODE_LABEL:
            nd["label"] = n.label or ""
        if EXPORT_ABS_POS:
            nd["pos"] = abs_node_pos(n)
        nodes_out.append(nd)

    links_out = []
    for l in node_tree.links:
        links_out.append({
            "from_node": l.from_node.name,
            "from_socket": getattr(l.from_socket, "identifier", l.from_socket.name),
            "to_node": l.to_node.name,
            "to_socket": getattr(l.to_socket, "identifier", l.to_socket.name),
        })

    data = {
        "schema": "blender-geometry-nodes-ai@1",
        "node_tree_name": node_tree.name,
        "nodes": nodes_out,
        "links": links_out,
    }

    if EXPORT_FRAMES:
        data["frames"] = export_frames_block(node_tree)

    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=to_json_default),
        encoding="utf-8"
    )

    print("Exported JSON:", str(out_path))
    print("Nodes:", len(nodes_out), "Links:", len(links_out))
    if EXPORT_FRAMES:
        print("Frames:", len(data.get("frames", [])))

# ===== main =====
obj = bpy.context.object
mod = choose_gn_modifier(obj)

ng = mod.node_group
if ng is None:
    raise RuntimeError("该 NODES modifier 没有关联 node_group（可能为空/损坏）。")

out_dir = Path(bpy.path.abspath("//"))
fname = f"{ng.name}_{FILE_SUFFIX}.json" if FILE_SUFFIX else f"{ng.name}.json"
out_path = out_dir / fname

export_node_tree_to_json(ng, out_path)
