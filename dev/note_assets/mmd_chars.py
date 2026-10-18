"""MMD の 4 体の材質の名前(半透明の重ね / 顔と目)。mmd_fix.py と mmd_dance_render.py が使う。"""
CHARS = {
    "Alicia": dict(mesh="Alicia", overlay=["hairShadow", "tere", "hacyu", "tear", "hau"],
                   face=["face", "eye", "eyehole", "eyebrush"]),
    "Akari": dict(mesh="Akari", overlay=["Shadow", "Blush", "Highlight", "Star", "Heart", "Vein", "Frame", "Circle Eyes",
                           "Squint", "Bra Shine"],
                  face=["Face", "Eye", "White Eyes", "Lash", "Brow"]),
    "Miku": dict(mesh="Tda", overlay=["髪影", "チーク", "ハイライト"],
                 face=["顔", "黒目", "白目", "まつ毛", "眉毛"]),
    "Serval": dict(mesh="サーバル", overlay=["カゲ", "影", "ハダカゲ", "ほほ", "紅潮", "てれ", "ハイライト", "星", "グル目", "丸目",
                            "涙", "汗", "怒", "=U", "!?"],
                   face=["顔", "白目", "瞳", "まつげ", "まゆ", "ハナセン"]),
}
