"""VRM(MToon)の下ごしらえ(v3.0)。STEP0 が VRM のモデルを見つけたら材質をセルで描ける形にする。

デルタもん(BlendAI、VRM 1.0)で見つけたこと:
  - VRM アドオンは材質に「MToon の出力」(グループ)を足し、EEVEE はそちらで描く。発光で色を
    出すので、セルにすると肌が真っ白・髪の色が抜けた → 止める
  - 隣の普通の材質(Principled)の出力は VRM アドオンがミュートしている。止めただけでは何も
    描かれず、セルでは全部影の色(髪がカーキ、白い服が薄紫)になった → ミュートを解く
  - その Principled は金属 1.0(glTF の既定のまま)。拡散の色が 0 になり真っ黒だった → 0
  - MToon の輪郭(ジオメトリノードの裏返しの殻)はキャラの日をさえぎり体じゅうが影の色に
    なった → トゥーン用の殻と同じく切る(auto_setup.outline_shells)
元の値は材質に控え、「FreePencil を外す」で戻す(restore)。
"""

import json
import re

import bpy

KEY = "fp_vrm_prep"
MTOON_OUT = "Mtoon1Material.Mtoon1Output"
COMPAT_OUT = "Mtoon1Material.CompatibleMaterialOutput"
COMPAT_SHADER = "Mtoon1Material.CompatibleShader"
OUTLINE_PREFIX = "MToon Outline"


def _mats(objs):
    seen = []
    for o in objs:
        for s in getattr(o, "material_slots", ()):
            m = s.material
            if m is not None and m not in seen and m.use_nodes and m.node_tree is not None:
                seen.append(m)
    return seen


def mtoon_materials(objs) -> list:
    return [m for m in _mats(objs) if MTOON_OUT in m.node_tree.nodes]


def is_outline_modifier(md) -> bool:
    """MToon の輪郭(VRM アドオンが足すジオメトリノード)。"""
    return md.type == "NODES" and md.name.startswith(OUTLINE_PREFIX)


def prepare(objs) -> list:
    """MToon の材質を Principled で描くようにする。直した材質の名前。"""
    done = []
    for m in mtoon_materials(objs):
        if KEY in m:
            continue
        nodes = m.node_tree.nodes
        rec = {}
        mt = nodes[MTOON_OUT]
        rec["mtoon_mute"] = mt.mute
        if hasattr(mt, "is_active_output"):     # VRM アドオンはグループのノード。出力のノードのこともある
            rec["mtoon_active"] = mt.is_active_output
        po = nodes.get(COMPAT_OUT)
        if po is not None:
            rec["compat_mute"], rec["compat_active"] = po.mute, po.is_active_output
            po.mute = False
            po.is_active_output = True
        mt.mute = True          # 出力を切り替えた後に(5.2 は切り替えでほかの出力のミュートが解けた)
        ps = nodes.get(COMPAT_SHADER)
        if ps is not None and "Metallic" in ps.inputs and not ps.inputs["Metallic"].links:
            rec["metallic"] = ps.inputs["Metallic"].default_value
            ps.inputs["Metallic"].default_value = 0.0
        m[KEY] = json.dumps(rec)
        done.append(m.name)
    return done


def restore(m) -> None:
    """prepare の前に戻す(「FreePencil を外す」から呼ぶ)。"""
    if KEY not in m:
        return
    try:
        rec = json.loads(m[KEY])
    except (TypeError, ValueError):
        rec = {}
    nodes = m.node_tree.nodes if m.node_tree else {}
    mt = nodes.get(MTOON_OUT)
    po = nodes.get(COMPAT_OUT)
    if po is not None and "compat_mute" in rec:
        po.mute = bool(rec["compat_mute"])
        po.is_active_output = bool(rec["compat_active"])
    if mt is not None and rec.get("mtoon_active") and hasattr(mt, "is_active_output"):
        mt.is_active_output = True
    if mt is not None and "mtoon_mute" in rec:
        mt.mute = bool(rec["mtoon_mute"])      # ミュートは出力を戻した後に(prepare と同じ理由)
    ps = nodes.get(COMPAT_SHADER)
    if ps is not None and "metallic" in rec:
        ps.inputs["Metallic"].default_value = float(rec["metallic"])
    del m[KEY]


# 顔と目の材質(物をまたいで 1 色にそろえる)。デルタもんは Mat_Face と Mat_Eyes、VRoid は FaceMouth・EyeWhite・
# EyeIris・FaceBrow・FaceEyeline など
FACE_EYE_RE = re.compile(r"face|eye|brow|lash|mouth|顔|目|眉|まつ", re.IGNORECASE)


def characters(objs) -> list:
    """VRM のアーマチュアで動く物。"""
    from . import humanoid
    return [o for o in objs if o.type == "MESH" and humanoid.is_vrm(humanoid.armature_of(o))]


def finish(objs) -> dict:
    """STEP1 の塗り分けの後: 目・手・口の線を VRM 向けに直す。直した数。

    デルタもんで 1 つずつ画像で決めた:
      - 目が顔と別の物で、物の境に黒い丸い縁が出た → 顔と目の材質を物をまたいで 1 色に
      - 指の重みが節ごとに切り替わり、節ごとに線が入って手が黒っぽく見えた → そういうモデルだけ手ごとに
        前腕から指先を 1 色に(merge_hand)
      - 口が形の切れ目で線が出なかった → 口の中を塗り分けて 0.02 開ける(ai.mouth_line)
    """
    from . import ai, cel_shade
    chars = characters(objs)
    if not chars:
        return {}
    names = [o.name for o in chars]
    out = {}
    mats = [m.name for m in _mats(chars) if FACE_EYE_RE.search(m.name)
            and not cel_shade.is_highlight_material(m)]
    if mats:
        r = ai.merge({"objects": names, "material": mats}, across=True, undo=False, refresh=False)
        out["eyes"] = 0 if r.get("warnings") else len(mats)
    for side in ("left", "right"):
        out[f"{side}_hand"] = sum(merge_hand(o, side) for o in chars)
    r = ai.mouth_line(names, open=0.02, undo=False, refresh=False)
    out["mouth"] = 0 if r.get("warnings") else 1
    return out


# 指の頂点のうち、1 本の骨の重みが 95% 以上の物の割合。これ以上なら節ごとに段の付いた塗りになる
# (デルタもん 0.56 で節ごとに線、天宮翼 0.07 で線なし)
HARD_FINGER_SHARE = 0.3


def hard_finger_share(obj) -> float:
    """指の重みが節ごとに切り替わっている度合い(0〜1)。"""
    from . import humanoid
    arm = humanoid.armature_of(obj)
    fb = set()
    for s in ("left", "right"):
        for k, v in humanoid.hand_groups(arm, s, forearm=False).items():
            if k != "palm":
                fb |= v
    gi = {g.index for g in obj.vertex_groups if g.name in fb}
    n = hard = 0
    for v in obj.data.vertices:
        ws = [g.weight for g in v.groups if g.group in gi]
        if not ws:
            continue
        tot = sum(g.weight for g in v.groups if g.weight > 0)
        n += 1
        hard += max(ws) / max(tot, 1e-6) >= 0.95
    return hard / n if n else 0.0


def merge_hand(obj, side: str) -> int:
    """指の節ごとの線を消す: 指の重みが節ごとに切り替わるモデルだけ、前腕から指先を 1 色に。

    骨の塗り(bone_color)は重みで色を混ぜるので、重みがなだらかなら節に線は出ない(天宮翼)。
    デルタもんは指の重みが節ごとに切り替わり、節ごとに線が入って手が黒っぽく見えた。
    なだらかなモデルまで 1 色にすると、指どうしの境の線が消えて重なった指がミトンに見えた。
    指ごと・甲ごとに面で塗ると、混ぜた色との境に段ができ、拳にぎざぎざの線が出た(天宮翼)。"""
    from . import ai
    if hard_finger_share(obj) < HARD_FINGER_SHARE:
        return 0
    r = ai.merge({"objects": [obj.name], "bones": f"{side}_hand"}, undo=False, refresh=False)
    return 0 if r.get("warnings") else 1
