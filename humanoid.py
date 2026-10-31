"""人型の骨の読み替え(v3.0)。手・指・頭などを、モデルごとに違う骨の名前から探す。

VRM は骨の名前がモデルごとに違う(デルタもんは hand.l / c_index1.l)。人型のどの骨かは
VRM アドオンの印(armature.data["vrm_addon_extension"])にあり、骨は uuid で指している。
アドオンが無くても印は ID のプロパティとして読めるので、ここで uuid を骨の名前に直す。
VRM でなければ、よくある名前(MMD・Mixamo・VRoid・Rigify)から探す。

名前は VRM 1.0 の人型の名前(left_hand / left_index_proximal / head …)にそろえる。
"""

import re

import bpy

FINGERS = ("thumb", "index", "middle", "ring", "little")
FINGER_PARTS = ("metacarpal", "proximal", "intermediate", "distal")

# VRM で無いモデルの名前(骨の名前を小文字にして探す)。{s} は l / r、{S} は left / right
_HAND_PATTERNS = (
    r"^(手首|手)[._]?{lr}$", r"^{S}_?hand$", r"^hand[._]{s}$", r"^j_bip_{s}_hand$", r"^mixamorig:{S}hand$",
)
_LOWER_ARM_PATTERNS = (
    r"^(ひじ|肘)[._]?{lr}$", r"^{S}_?(fore|lower)_?arm$", r"^(forearm|lower_?arm)[._]{s}$",
    r"^j_bip_{s}_lowerarm$", r"^mixamorig:{S}forearm$",
)
_FINGER_WORDS = {
    "thumb": ("親指", "thumb"), "index": ("人指", "人差指", "index"), "middle": ("中指", "middle"),
    "ring": ("薬指", "ring"), "little": ("小指", "little", "pinky"),
}
_HEAD_PATTERNS = (r"^頭$", r"^head$", r"^head[._]x$", r"^j_bip_c_head$", r"^mixamorig:head$")


def armature_of(obj):
    """物を動かしているアーマチュア(モディファイアか親)。"""
    for m in getattr(obj, "modifiers", ()):
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    p = obj.parent
    while p is not None:
        if p.type == "ARMATURE":
            return p
        p = p.parent
    return None


def is_vrm(arm) -> bool:
    return arm is not None and arm.type == "ARMATURE" and "vrm_addon_extension" in arm.data


def _vrm_map(arm) -> dict:
    """VRM の印から {人型の名前: 骨の名前}。VRM 1.0 / 0.x の両方。"""
    out = {}
    try:
        ext = arm.data["vrm_addon_extension"]
    except KeyError:
        return out
    uuid2bone = {}
    for b in arm.data.bones:
        try:
            u = b["vrm_addon_extension"]["uuid"]
        except (KeyError, TypeError):
            continue
        uuid2bone[str(u)] = b.name
    try:
        hb = ext["vrm1"]["humanoid"]["human_bones"]
        for k in hb.keys():
            try:
                node = hb[k]["node"]
            except (KeyError, TypeError):
                continue
            name = None
            for key in ("bone_name", "value"):
                if key in node and str(node[key]) in arm.data.bones:
                    name = str(node[key])
            if name is None and "bone_uuid" in node:
                name = uuid2bone.get(str(node["bone_uuid"]))
            if name:
                out[k] = name
    except (KeyError, TypeError):
        pass
    if out:
        return out
    try:                                           # VRM 0.x: 名前は camelCase(leftHand / leftIndexProximal)
        for hb in ext["vrm0"]["humanoid"]["human_bones"]:
            k = re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), str(hb["bone"]))
            node = hb["node"]
            name = str(node["bone_name"]) if "bone_name" in node else uuid2bone.get(str(node.get("bone_uuid", "")))
            if name in arm.data.bones:
                out[k] = name
    except (KeyError, TypeError):
        pass
    return out


def _find(names, patterns, side=None):
    for p in patterns:
        if side is not None:
            s = side[0]
            p = p.format(s=s, S="left" if s == "l" else "right", lr=s)
        rx = re.compile(p, re.IGNORECASE)
        for n in names:
            if rx.match(n.lower() if not re.search(r"[^\x00-\x7f]", n) else n):
                return n
    return None


def bones(arm) -> dict:
    """{人型の名前: 骨の名前}。VRM の印、無ければ名前から探した分だけ。"""
    if arm is None or arm.type != "ARMATURE":
        return {}
    out = _vrm_map(arm)
    if out:
        return out
    names = [b.name for b in arm.data.bones]
    h = _find(names, _HEAD_PATTERNS)
    if h:
        out["head"] = h
    for side in ("left", "right"):
        hand = _find(names, _HAND_PATTERNS, side)
        if hand:
            out[f"{side}_hand"] = hand
        low = _find(names, _LOWER_ARM_PATTERNS, side)
        if low:
            out[f"{side}_lower_arm"] = low
        if hand:                                   # 指は手の子孫から、指の言葉で探す
            for b in arm.data.bones[hand].children_recursive:
                low_n = b.name.lower()
                for f, words in _FINGER_WORDS.items():
                    if any(w in low_n or w in b.name for w in words):
                        depth = len([p for p in b.parent_recursive if any(
                            w in p.name.lower() or w in p.name for w in words)])
                        part = FINGER_PARTS[min(depth + (0 if f == "thumb" else 1), 3)]
                        out.setdefault(f"{side}_{f}_{part}", b.name)
    return out


def hand_bones(arm, side=None, forearm: bool = True) -> set:
    """手(と前腕)と指の骨の名前。side は "left" / "right" / None(両方)。

    前腕まで含めるのは、手首で塗りを切ると手首に境目の線が出たため(デルタもん)。"""
    bm = bones(arm)
    sides = (side,) if side else ("left", "right")
    out = set()
    for s in sides:
        for k, v in bm.items():
            if not k.startswith(s + "_"):
                continue
            rest = k[len(s) + 1:]
            if rest == "hand" or (forearm and rest == "lower_arm") or rest.split("_")[0] in FINGERS:
                out.add(v)
    return out


def head_bone(arm):
    return bones(arm).get("head")
