# note / GitHub 用アセットの生成

配布ページに載せる画像を、すべてスクリプトから作り直せるようにしたもの。
手作業の加工はしない。**一時ディレクトリには置かない**（v2.5.0 公開時、
スクラッチパッドに置いた生成物とスクリプトを一式失った）。

出力先は既定で `dev/note_assets/out/`。このフォルダは配布ZIPからも
git からも除外される。

## 作例レンダー

```bat
blender -b --factory-startup --python render_samples.py -- ^
  --blend <asset.blend> --name mecha --out out --res 1600
```

同じカメラで2枚出る。

- `<name>_line.png` — 最終線画（白マテリアル + PROコンポジタ）
- `<name>_paint.png` — 塗り分けの状態（mecha_color 頂点カラーをそのまま表示）

そのあと透過PNGを白背景に載せてトリミングする。

```bat
python compose_samples.py
```

- `01_<name>_line.png` — 線画（幅1600）
- `03_<name>_paint.png` — 塗り分け
- `04_paint_to_line.png` — 「塗り分け → 線画」の対比図（キャプション付き）

## UI スクリーンショット

GUI の Blender を2フェーズで動かす。フェーズ1で撮影用の .blend を作り、
フェーズ2でそれを開いて撮る。**ファイルを渡して起動するとスプラッシュが
出ない**ので、この順序が要る。

```bat
blender -b --factory-startup --python ui_prepare.py -- ^
  --blend <asset.blend> --save out\ui_scene.blend

blender --factory-startup -p 0 0 2400 1400 out\ui_scene.blend ^
  --python ui_shots.py -- --out out

python compose_ui.py
```

撮影は日本語UI・UIスケール1.25。実際にインストールされている拡張機能を
有効化して撮るので、**同期を先に済ませること**（`scripts\sync_extension.bat`）。

## 計測

```bat
blender -b --factory-startup --python time_step0.py -- --blend <asset.blend> --name mecha
```

STEP0 を押してから終わるまでの実時間。記事に載せる「処理時間」はこれ。
STEP1 単体の時間ではない。

## 改変チェック

```bat
blender -b --factory-startup --python verify_mutation.py -- --blend <asset.blend>
```

STEP0 がモデルの何を書き換えるかを前後比較で出す。
「モデルを改変しない」と書いてよいかの判断に使う。推測で書かないこと。
