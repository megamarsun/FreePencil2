---
name: freepencil
description: Blender の線画アドオン FreePencil2 で、3D モデルから線画(アニメ調の輪郭線)を作る・直すとき。STEP0〜5、セル、線の消去や追加などの手直しを AI が行うときに使う
---

# FreePencil2 を AI が使うとき

中身(進め方・各ボタンの使いどころ・次の一手)は**アドオンの中**にある。版がずれないよう、ここには入口だけを書く。

1. Blender の Python で AI 用のボタンを押し、出てきた指示に従う:
   ```python
   import bpy, sys
   bpy.ops.freepencil.ai_guide()
   fp = next(m for n, m in sys.modules.items() if n.endswith("freepencil2.ai"))
   print(fp.guide())
   ```
2. 以後は `fp.auto()` / `fp.render()` / `fp.erase_lines()` / `fp.add_lines()` などを使う。
   どの関数もボタン(`bpy.ops.freepencil*`)も、押した後に `[FreePencil AI]` で始まる行で
   「何が変わったか・何を見るか・次に何をするか」を出す。`fp.last()` でも読める。
3. **判断は必ず絵で行う。** `fp.render()` が返す画像(`image` と目盛り付きの `grid_image`)を開いて見る。
   線の量などの数値は補助。数値が良くても絵が破綻していれば破綻している。
4. 筆は使えないので、直す場所は `where` で言葉にする:
   `{'objects': [...]}` / `{'material': '名前の一部'}` / `{'vertex_group': '名前'}` /
   `{'rect': (x0, y0, x1, y1)}`(カメラ画面の割合、左上が 0,0、見えている面だけ)。
5. 1 手直すたびに別の名前で撮り、前後を見比べる。悪くなったら `fp.undo()`。
