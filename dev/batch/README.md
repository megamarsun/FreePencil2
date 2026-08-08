# FreePencil バッチ評価パイプライン

BlenderKit キャッシュのモデルを大量に FreePencil (STEP1 + PROノード) で処理し、
線画レンダとメトリクスを収集して改良の判断材料を貯めるための一式。

## 使い方

1. `run_tests.bat` — 回帰テスト6本(モデル不要、1分以内)
2. `run_batch.bat [N]` — キャッシュから最大N体(既定100)を処理
   - まず `run_batch.bat 10` で試すのを推奨
   - 中断しても再実行すれば処理済みモデルはスキップされる(レジューム)
   - 失敗分をやり直す場合: `run_batch.bat 100 --retry-failed`
3. 結果: `out/report.html`(コンタクトシート+スコア表、スコア降順)

## 構成

| ファイル | 役割 |
|---|---|
| `run_batch.py` | ドライバ(スキャン→モデル毎にヘッドレスBlender起動→レポート)。タイムアウト・クラッシュ記録・レジューム対応 |
| `scan_models.py` | BlenderKit のモデルキャッシュ(既定 `~/blenderkit_data/models`、環境変数 `FP_MODEL_ROOT` で変更可)を走査して `out/models.json` を生成(materials等メッシュ無しアセットは対象外) |
| `fp_batch.py` | 1モデル分のヘッドレス実行(アドオン登録→正規化→STEP1→STEP2→STEP3→EEVEEレンダ→メトリクス) |
| `presets.json` | パラメータプリセット(default / fine_detail / coarse) |
| `make_report.py` | `out/metrics/*.json` を集計して `report.html` を生成 |
| `tests_smoke.py` | TDD回帰テスト(シード再現性・色距離違反ゼロ・fp_coreとオペレーター両方のヘッドレスノード生成) |

## アーキテクチャのポイント

- **STEP1〜3 すべて実オペレーターを呼ぶ**(`freepencil.auto_vertex_color` /
  `freepencil4.link_button` / `freepencil2.link_button`)。
  STEP2/3 のコアロジックは本体の `fp_core.py` に分離済みで、オペレーターは
  UI 処理(ビューポート切替・ウィンドウ生成・ポップアップ)を background モードで
  スキップする薄いラッパー。**バッチとUIが同一コードパス**なので同期の問題がない。
- リポジトリのフォルダ名(`22_FreePencil`)が数字始まりで import 不可のため、
  `%TEMP%\fp_addon_pkg\freepencil2` → リポジトリ のディレクトリジャンクションを
  一度だけ作成して登録する(コピーではないので常に最新コードで動く)。
- レンダは EEVEE Next(`BLENDER_EEVEE_NEXT`)。GPU 必須(RTX 4090 で確認済み)。

## メトリクス(v1)

- **ink_ratio** — 線画の黒画素率(少なすぎ=線が出ていない、多すぎ=ノイズ)
- **components** — 線の連結成分数(多すぎ=線が断片化)
- **distinct_colors / adjacent_color_pairs / min_distance_violations** — 塗り分け品質
- **step1_seconds / render_seconds** — パフォーマンス

score = 線密度45% + 断片化30% + 塗り分け違反率25%(`make_report.py` で調整可)

## 改良バックログ

1. スコアの重み・特徴量は v1 の仮置き。目視評価とすり合わせて調整する。
2. カメラは固定1アングル。多視点レンダで死角の線品質も評価したい。
3. プリセットのグリッド探索(同一モデル×複数プリセットでスコア比較)。
4. 失敗ケースはそのまま `tests_smoke.py` に固定化して回帰を防ぐ。
