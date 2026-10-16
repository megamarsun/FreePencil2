# FreePencil2 - Changelog

## [Unreleased]
### Fixed
- ビューポートのセル/マテリアル/モノクロで細い線が消えた(F12 は正常)。ビューポートのコンポジタの
  乗算は 1 番目の口のアルファを持ち込むので、線の絵を 1 番目に入れる(窓のある Blender で確認)
- **テクスチャで塗り分ける技法(AOV グループの line_texture に絵をつなぐ)が v2.8.0 から効いて
  いなかった**。頂点カラーが半分の明るさで届く不具合を直したとき、絵を混ぜる係数も 0 にしていた。
  絵の色を「足す」形にして戻した(つないでいなければ今と同じ)。mask_texture をつないだときは
  STEP2 / STEP0 がマスクの AOV を入れる(テスト 86 本目)
- **STEP0 の後に STEP4 でマスク/ラインを塗っても線が変わらなかった**。STEP0 は塗っていない色の
  AOV を作らず、STEP2 を押し直しても入れていなかった。「頂点カラーを塗る」を押した時点で入れ、
  STEP2 も塗ってある色を見て入れる。手描き背景では細い線(グループのコピー)にマスク/ラインが
  つながっておらず、どうやっても消えなかった。輪郭の外側の画素にもマスクが届くよう少し広げる
  (精密で細い輪郭が薄く残り、キャラで外へ太らせた輪郭が残った)(テスト 87 本目)
- **Half Fill を作り直した**。選んだ頂点のうち任意の 2 点と X/Y 平面だけで側を決めていて、
  正面を向いた面などでは黒い塊が出た。境目に沿って選んだ頂点の角を、面ごとに「その面の
  ほかの角の色」にそろえる(向きや側は要らない)。頂点ペイントのぼかしの境目が 1 本の線になる。
  STEP4 で選んでいる種類の色に効く(テスト 88 本目)
- **STEP2 を手で押すと背景が透過になった**(STEP0 は元に戻していた)。背景の透過は触らない
- **STEP5 の一括レンダーが、セルなど合成した絵を残さなかった**。カメラのフォルダに final.png
  (最終サイズ)も書き出す
- (v2.9 の総当りで発見して直したもの。どれも v2.9 の新機能の中)
  - マテリアル/モノクロからセルへ切り替えると線が全部消えた(前のノードを外す順番)
  - 背景を透過にすると、セル・マテリアル・モノクロで空や色が白く飛んだ(線の絵の外側を白に
    重ねると 2 倍になった。重ねた後に 1 で切る)
  - ビューポートでマテリアルが白く、セルの空が出なかった(STEP2 が表示を塗り分けのパスにした
    ままだった。コンポジタープレビューを入れたら合成に戻す。パスの物の外のアルファを 1 にする)
  - セルの影が材質で変わった(表面下散乱の材質で影がずれ、5.2 では服だけ明るかった)。日があれば
    法線 x 日の向き x 影のパスで取る(発光だけの材質は前の取り方)。日を回すと影がついて行く
    (テスト 85 本目)
- **キャラ/手描き背景で「マテリアル」「モノクロ」のプレビューにすると、色が消えて灰色になり、
  陰影が黒い線として描かれていた**(v2.8.0 から)。線の強弱の処理は、合成に入る絵の暗い所を
  すべて線として扱う。その絵が「材質の色や陰影の上に線」だったので、影まで黒く塗られた。
  線は白地に描いて強弱を付け、材質の色や陰影はその後で下に掛けるようにした。精密は今までどおり
  (v2.7 と同じ絵)。STEP3 の押し直しでも保たれる。4.5 / 5.2 で 3 仕上がり x 4 プレビューを撮って
  確認(テスト 82 本目、見え方の監査の基準を更新)

### Added
- **物ごとの線の太さ**(STEP0 の、選んでいるオブジェクトの「線の太さ(倍)」)。1 = そのまま、
  2 = 太く(+1px)、3 = もっと太く(+2px)、0.5 = 薄く、0 = 線を出さない。手前のキャラは太く、
  背景は薄く、地面の線は消す、などができる。全部 1 なら何も挿さず、絵は 1 画素も変わらない
  (見え方の監査で全場面 0.02% 以下)。値は材質の属性で読むので、動かしてもすぐ絵に出る
  - 太くする方は周りへ広げ(太い方が勝つ。輪郭の外側にも効く)、薄くする方は周りの一番小さい値を
    使う(地面 0 の隣のキャラの輪郭は消えない)。細線化の縮小の手前で掛ける
  - 強弱のある線と同じく、マテリアル/モノクロでは線を白地に描いてから下に掛ける(テスト 84 本目)
- **セルを別のソフトで重ねるための書き出し**(STEP5 のファイル出力に「セルの色」「セルの影」)。
  cel_color.png は影を付けない薄い色(物の外は透過)、cel_shadow.png は影の所だけ影の色で
  ほかは透過(乗算のレイヤーとして重ねる)。プレビューの種類に関係なく書き出す。白の上に
  cel_color、cel_shadow を乗算、line を重ねるとセルの絵になる(画像で確認、テスト 83 本目)
- キャラ/手描き背景の line.png を、強弱を付けた後の線にした(強弱の前の細い線で、絵と違っていた)
- セルの「影のしきい値」の既定を 0.7 -> 0.55。0.7 では日に斜めの面(既定の地面)まで影になった
- **プレビューの種類に「セル(影と色)」**(v2.9 の目玉)。線を白地に描いてから、材質の色を白へ
  寄せた薄い色と、2 階調のセルの影を敷く。物の外は空の色(切れば透過)。STEP3 の「プレビュー」で
  選ぶと、その場でビューポートと F12 に出る。つまみ: 影のしきい値、影の縁をなめらかに、色の薄さ、
  影の色、空の色、影の線(色・太さ)
  - 影は材質の光から取らない。アニメ調のモデルは発光や Shader to RGB の材質が多く、拡散の光が 0 で
    影が出なかった(試作で実測)。すべての材質に「白い拡散面が受けた光 -> Shader to RGB -> AOV
    (fp_shade)」を足し、材質の作りに関係なく同じ光と影を取る
  - 色は「拡散の色 + 発光」のパスから取る(発光だけの材質が灰色になった、テスト 81 で発見)
  - 線の太さ・密度などの線の処理は変えない(切っていれば今と 1 画素も変わらない。4.5 の見え方の
    監査で全場面 0.00%)。「FreePencil を外す」は影の AOV とノードも消す。テスト 81 本目

## [2.8.3] - 2026-10-03
### Fixed
- **STEP3 の「コンポジタープレビューを有効化」がその場で効く**ようにした。以前は STEP3 を
  押したときにしか見ず、チェックしても何も起きず、外してもビューポートのコンポジタが
  「常に」のまま残った。入れるとレンダー表示 + コンポジタ「常に」、外すとコンポジタを切る
  (4.2 は触らない)。GUI で確認
- 「FreePencil を外す」の確認に、何が消えるかを日本語で出す(既定では英語の操作名だけ)。
  全自動セットアップのすぐ下だったので間を空けた

### Added
- **FreePencil を外す**(STEP0 の「FreePencil を外す」、`freepencil.remove`)。note のコメントで
  「適用したあと戻す方法は？ アングルを変えて光源込みでレンダリングし直したい」と聞かれた。
  STEP0〜3 が足した色属性・材質の AOV ノード・FreePencil_Material・ビューレイヤーの AOV・
  コンポジタのノード・ノードグループを消し、変えた設定(背景の透過、色の変換、200%、
  パス、EEVEE の AO、透過材質の BLEND、pass_index、利用者のコンポジタの入出力とつなぎ)を戻す。
  元の値は、最初の STEP の入口で scene["fp_undo"] に控える(.blend に残る)。控えの無い
  ファイル(v2.8 以前)は足したものを消し、戻せない項目を知らせる。確認を出し、Ctrl+Z で
  取り消せる。4.5 / 5.2 で、STEP0 の前と外した後(保存して開き直してから)の絵が画素まで
  一致(テスト 80 本目、dev/note_assets/remove_check.py)
- **見え方の監査**(開発用、`dev/batch/visual_audit_run.py`、`install_all.py --test --audit`)。
  人が見て初めて見つかった不具合の場面(Blender 既定の不透明な背景 x 3 仕上がり、地面あり、
  背景透過、プレビューの切り替え一巡、手前と奥の窓の壁)を 4.5 / 5.2 で撮り、基準の絵
  (`dev/batch/visual_audit_baseline/`)と「基準 | 今回 | 違う所(赤)」で差の大きい順に並べる。
  合否は絵で見る。v2.8.2 の不透明背景の修正を戻すと、キャラの輪郭の強弱が消えた所が赤く
  出ることを確認した
- **手描き背景: 遠い区画をまとめる**(`fp_far_lod_px`、STEP0 で 500、STEP1 のつまみ)。
  遠くのビルの窓や帯は、どの仕上がりでも線が詰まって黒い縞の塊になった(「奥ほど線を
  減らす」は 2 -> 4 にしても変わらなかった。窓の色の段差がしきい値より強いため)。
  区画ごとにカメラから見た画面上の面積(横 1920 の絵の px^2)を出し、小さい区画を、
  残す区画の一番近い面へまとめる。遠くの高層が輪郭と数本の帯になり、手前は変わらない
  (大通り: 島 44916 -> 5808)。房の後に置くので手前の木の房は崩れない。同じメッシュを
  使う物は近い 3 本で測る。カメラにアニメーションがあれば動きの範囲(33 点)で一番
  近づく位置で測る(近づく先のビルの窓が消えない、画像で確認)。精密・キャラは通らない。
  mesh_islands.face_screen_area / merge_far_islands、vertex_color.far_lod_cameras。テスト 79 本目

### Changed
- **手描き背景の「細かすぎる縞を薄く」を既定で切った**(0。STEP3 の詳細に別のつまみ)。
  カメラが動くと、遠くの窓の格子が画素とのずれでコマごとに見え方を変え、薄める範囲と
  灰色の濃さが揺れて灰色のまだらがちらついた。縁石のような近い 2 本の線も細い二重線
  になった。大通りの飛行(24 コマ)で 1 つずつ切り替えて、この処理だけが原因と確認。
  ぼかし半径・向きのしきい値・白への寄せ方を変えても消えなかった。町では電線が
  途切れず 1 本の線になり、シャッターも黒い塊にならない。「つぶれ軽減」のつまみは
  詰まった線を薄くするだけになった
- **手描き背景の線を、薄めずに黒を残すようにした**。v2.8.2 までは、線の濃さ 0.75
  (一番濃い線が濃い灰色)、詰まった線を薄く 0.6、奥の線を薄く 0.35 で、白プレビューで
  精密(v2.7 相当)と並べると「色を薄くしただけ」に見えた。並木は灰色の面になっていた。
  線の濃さ 1.0、詰まった線を薄く 0.3、奥の線を薄く 0.15、細い線 0.6 -> 1.0 に変更。葉の陰と幹に黒が残り、
  町の手すりや網戸も黒い塊にはならない(並木道と町で 4 案を撮り比べて確認)。
  STEP0 を押し直したときに効く。開いただけの .blend は変わらない。STEP3 の「つぶれ軽減」
  「奥の線を控えめに」のつまみを動かすと、新しい割合で計算し直す

## [2.8.2] - 2026-09-28
### Fixed
- **モノクロ -> マテリアル と切り替えると陰影だけの絵になり、そのあと白を選んでも
  白にならなかった**。モノクロを下ろすとき、撤去するノードの入力元(ディフューズ
  直接光のパス)をグループの Image へつないでいて、白プレビューの Mix が外れた
  ままになった。立てる前の入力元を覚えておき、そこへ戻す。GUI のビューポートで
  プレビューを切り替えて見つけた(4.5 / 5.2 で画像確認、テスト 78 本目)
- **地面を地平線まで広げると、精密/キャラで地平線の手前が太い黒帯になっていた**
  (v2.4 から)。深度の線を「深度が何割変わったか(相対勾配)」で取っていて、
  平らな地面を低く見ると奥ほど値が大きくなり、帯になった。斜めから見た箱の側面が
  真っ黒になるのも同じ原因。深度を |Laplace(1/Z)| x Z に変えた。1/Z は平面上で
  画面の一次式なので平面ではちょうど 0、物の前後の段差は今までどおり線になる。
  地平線は1本の線になる。実モデル 5 体(アニメ少女・機関車・カメラ・家・車)x
  精密/キャラで差は 0.04% 以下、手描き背景(深度チャンネル OFF)は変化なし
  (4.5 / 5.2 で画像確認、テスト 77 本目)。開いただけの .blend は変わらず、
  STEP3 を押したときに新しい線の取り方になる
- 奥の距離の計測は、線の画素が少ない場面(球だけ等)では物の内側の深度で測る
- **背景を不透明のまま(Blender の既定)だと、キャラ/手描き背景の輪郭の強弱が
  ほとんど出ていなかった**。強弱は「物の外」を開いた所として輪郭を太らせるが、
  物の外をレンダーのアルファで見ていた。背景が不透明だとアルファは画面全体で 1
  になり、物の外が分からなかった(試験やデモはどれも背景を透過にしていたので
  気づかなかった)。深度で「物のある所」を取り、アルファが半端な縁はアルファの
  まま使う。背景を透過にしていれば 1 画素も変わらない(4.5 / 5.2、3 仕上がり x
  地面あり/なし で確認)。モノクロプレビューで背景の地に出ていた帯と、隙間埋めが
  不透明の背景で効いていなかったのも同じ原因(テスト 76 本目)
- **5.2 で最初にモノクロを選ぶと材質の色で出た**。陰影のパスをつなぐ前に立てる
- **5.2 の手描き背景で輪郭が二重になっていた**。5.x では SetAlpha の mode が
  「Type」ソケットに移り、設定を書く共通の関数が書き込み先を見つけられず、
  何もせずに戻っていた(「Apply Mask」のまま)。隙間埋めの Inpaint が色を外へ
  にじませ、元の縁とにじんだ縁の2本が線になった。STEP3 の本体の SetAlpha も
  同じで、5.2 だけ意図と違う合成になっていた。5.x の名前を足し、どこにも
  書けないときは警告を出す(テスト 72 本目)
- **細い線のつまみを動かした直後、線がほとんど消えていた**(STEP3 を押すと戻る)。
  合成だけを後から差し直していた。STEP3 ごと作り直す(テスト 67 本目)
- **テストノードを選ぶと STEP3 が止まっていた**。手描き背景では細い線がプロノード
  の出力を探して KeyError、5.x ではテストノード自体が Filter の入力の並びと
  Normal ノードの変更で作れなかった(テスト 68 本目)
- **硬境界ボーンがキャラ/手描き背景で効いていなかった**。v2.8 のボーンの色の
  なじませが、わざと残した段差までぼかしていた(テスト 70 本目)
- **「くぼみで線に強弱をつける」と「詰まった線は太らせない」がその場で効く**
  ように。他の強弱のつまみと同じく STEP3 ごと作り直す(テスト 69 本目)
- **仕上がりを変えたら、キャラの塗り方の目印も合わせる**。精密に戻してから
  STEP1 だけ押し直すと、古い目印でキャラの塗り方になっていた(テスト 71 本目)
- 細い線のつまみは、手描き背景の STEP0 で塗り分けを2枚作ったときだけ使える
  ように(それ以外は灰色にして作り方を出す)
- STEP4 の塗りボタンとノードの書き出し/読み込みが、3D ビュー/ノードエディタの
  外から呼ばれると落ちていたのを直した
- **v2.7 のファイルを開いて STEP3 / STEP0 を押すと白プレビューが外れていた**。
  v2.7 は白プレビューを ON/OFF で持ち、プレビューの種類が無かった。開いたときに
  種類が一度も書かれていないファイルなら白を種類へ移す。STEP0 も種類で判断する
  (テスト 75 本目)。空のプロファイルへの新規インストール(4.2/4.3/4.5/5.2)、
  v2.7 を入れた上への上書き(4.5/5.2)、保存して開き直し を別プロセスで通して確認
  (dev/batch/check_install_run.sh)。v2.7 のファイルは開いただけなら1画素も
  変わらない
- **ファイル出力の color.png が真っ白だった**(v2.7 から)。color はグループの
  Image 入力の素通しで、STEP0 の既定の白プレビュー中は白になっていた。レンダーの
  色から取る(テスト 74 本目)。STEP5 でカメラ2台 x 4 パス x 3 仕上がりを
  4.5 / 5.2 で書き出して確認: 線は透明地に黒で最終サイズ(2倍レンダでも等倍)
- **パネルを整理**(67 項目 -> STEP3 の普段の表示は 7 項目)。ほぼ自動で決まるので、
  見ながら加減するつまみだけを出した。
  - 「奥ほど細く / 線を減らす / 薄く」を「奥の線を控えめに」1本に、「詰まった線を
    薄く / 細かすぎる縞を薄く」を「つぶれ軽減」1本にまとめた(1.0 で v2.8.0 の
    手描き背景の既定と同じ値。STEP0 の出力は 4.5 / 5.2 とも1画素も変わらない)
  - 「詰まった線は太らせない」は中の固定値(1.0)にして消した
  - 稜線の起伏・尺度、葉を房には STEP0 が決めるのでパネルから外した
  - 線の濃さ・縁・葉の隙間・チャンネル別・ノードの種類・AA・2倍レンダ・感度は
    STEP3 の「詳細」(閉じてある)へ。ファイル出力は STEP5 へ
- **5.x でプロパティを scene["名前"] で書いても本当の値が変わらなかった**。
  5.x では登録したプロパティとカスタムプロパティが別になった。白の旧トグルを
  種類に合わせる処理(v2.8.1 の最初の修正)も 5.2 では効いていなかった。
  フックを止めてふつうに書く(_write_quiet)。テスト 73 本目
- 見つけ方: パネルの項目とボタンを総当りするスクリプト
  (dev/batch/audit_panel.py)。項目を1つずつ変えて、変えた直後と STEP3 の後を
  撮り、4.5 と 5.2 で比べた

## [2.8.1] - 2026-09-26
### Fixed
- **プレビューの種類を切り替えたあと、STEP3 の作り直しで別の種類に戻っていた**。
  プレビューは「種類」(マテリアル/白/モノクロ)と旧トグル(白)の2か所に持って
  いて、パネルで種類を切り替えても旧トグルが残っていた。STEP3 の作り直し
  (強弱などのスライダーを動かしたときも)は旧トグルを見て掛け直していたので、
  「白」を選んでいるのに材質の色で出たり、「モノクロ」「マテリアル」を選んで
  いるのに白で出たりした。種類だけを見るようにし、旧トグルは種類に合わせる。
  しきい値の計測も種類を見て、モノクロ中はいったん外して測る(テスト 66 本目)

## [2.8.0] - 2026-09-26
### Added
- **塗り方(オブジェクトごと): 自動 / メカ / キャラ** `Object.fp_paint_as`。
  ロボット・背景・人間を別々に3つの仕上がりで撮って棲み分けを見たところ、
  リグ付きのロボット(ザク)が人と同じざっくり塗りになり、胴体が1色でパネルの
  線が消えた。自動では、リグ単位で「ボーン1本がウェイトの 99% 以上を持つ頂点の
  割合」を測り、0.9 以上かつボーン 8 本以上ならメカとして塗る。実測: ザク 0.95
  (59本) / 人 7 体 0.15〜0.80 / デッサン人形の頭だけのリグ 0.93(2本、ボーン数で
  除外)。1オブジェクトずつ測ると、別オブジェクトの頭がロボットに見えた。
  手動の「キャラ」はリグの無い人にも効き、顔や腕の線の塊が消えた(テスト 65 本目)
- **キャラの強弱の既定を「ほんのり」(強さ 0.6)に**。1.0 は輪郭が太すぎた。
  太い手描きの線はスライダーで上げればその場で効く
- **細かすぎる縞を薄く(つぶれ軽減)** `fp_lw_stripe_fade`(手描き背景 1.0、ほかは 0)。
  水平の線が何段も並ぶ面(シャッター・ルーバー・手すり・棚)を真横に近い
  低い位置から見ると、奥で縞が画面の画素より細かくなり、黒くつぶれて
  カメラが動くとちらつく。縞はメカの塗りから出ていて、色の段差がしきい値より
  はるかに強いので、勾配を弱める・色をぼかす方法は効かなかった(ぼかすと
  境目がにじむ)。そこで「メカの塗りを 12px(200% 基準)でぼかしてから
  出した輪郭」に乗らない細い線のうち、細い線が 45〜70% を超えて詰まり、
  しかも線の向きがそろっている所(構造テンソルの向きのそろい具合 0.75〜0.95)を、
  奥(深度で奥とみなす所)だけ、線の絵を 12px でぼかして白へ 60% 寄せた物へ
  寄せる(縞が淡い灰色のもやになる)。白へ薄めた版は白く抜けた所がまだらに
  見え、ぼかしだけの版はモアレの黒い斑が灰色の面に残った。向きの項が無い版は試験場では
  きれいだったが、町の木・電線・ベランダ、BlenderKit のカエデの樹冠と C62 の
  ボイラーまで白く抜けた(画像で確認)。奥度や詰まりのしきい値で絞ると
  中ほどのシャッターのモアレが戻った。縞の上では向きがほぼ 1、葉は
  0.5〜0.85 に散るので、向きで分けると縞だけに効く。しきい値の後で混ぜるので、
  線が消える/出るの切り替わりでなく、濃さがなめらかに下がる。しきい値の前で
  混ぜた版は薄くした所の境目に段が出た(画像で確認して捨てた)。
  カメラを下ろしていく試験動画で、半径 4/8/12/16px と標本数・前ぼかしを
  比べ、12px がいちばんちらつかなかった(向きの項を足してもちらつきは同じ)。
  生成後にその場で効く(テスト 63 本目: 奥の縞が薄くなり手前は残る、
  64 本目: 向きのばらばらな茂みは薄くならない)。
  あわせて、細い線(メカの分割)の複製グループに深度がつながっていなかった
  場合があり、奥ほど細く・減らすが細い線に効かないことがあったのを直した
- **詰まった線を薄く(つぶれ軽減)** `fp_lw_dense`(手描き背景 0.6、ほかは 0)。
  密度を上げた町で、手すりの縦桟・網戸とブラインドの窓・外階段・シャッターが
  黒い塊になった。距離で薄くする「奥ほど薄く」は手前の細かい物に効かない。
  画面上の「線と線の間の狭い隙間」(芯の閉じで埋まる所)と「線より太いインクの
  塊」(芯の開きで残る所)を数え、その多い所の線を周りの陰影へ向けて薄くする。
  インクの量で測った版は輪郭1本まで薄くなり、白へ向けて薄くした版は壁の灰色
  まで白い筋になった(どちらも画像で確認して捨てた)。輪郭・電柱・窓枠は黒のまま。
  生成後にその場で効く(テスト 62 本目)
- **強弱の強さ・線の濃さ・縁をやわらかく が生成後にその場で効く**。動かすと
  STEP3 を作り直す(0.1〜0.3 秒)。キャラの線を弱めにしたいとき、見ながら
  下げられる(テスト 60 本目)
- **キャラ(リグ付き)はざっくり塗り + ボーン塗り**(キャラ/手描き背景のとき)。
  リグ(Armature)の付いたオブジェクトは角度や UV シームで分けず、大きいパーツ
  (全体の2%以上)ごとに1色、小さいパーツ(髪のカード、まつ毛など)はマテリアル
  ごとに1色へまとめる。関節まわりは元からあるボーン塗り(ウェイトでぼかした
  bone_color)がつなぐ。角度で細かく分けていたときは、ジョギングさせた
  anime-girl の腕・髪・顔が線で黒く潰れていた(4体で比較)。つながり単位だけ
  だと髪が 568 島に割れて黒いまま、マテリアル単位だけだと服が1マテリアルの
  モデルでスカートとブラウスの境目まで消えた。島をボーン境界で切る案は、
  関節を横切る切れ目の線が出たので採らない(2026-07 に差し戻した実験と同じ)。
  精密はリグ付きでも v2.7 のまま(テスト 59 本目)。
  ボーン塗りはさらに隣の頂点と8回平均する。粗いケージでウェイトが1辺で
  切り替わると(デッサン人形の胸: spine_02 -> 03)、サブディビジョンがその段差を
  数px の帯に広げ、線でも無地でもない灰色の塊になっていた。2回で消え、4回で
  anime-girl の肘の暗い斑も消え、8回で人形の胸の中央の点と man_01 の胸を横切る
  暗い帯も消えた(人だけのテスト場で 4/8/16 回を比較。悪化なし)。密なメッシュはほぼ変わらない(テスト 61 本目)。
  ミラーモディファイアで左右を作っているモデルは左右が同じ塗りになり、脚が
  交差しても間に線が出ない(デッサン人形)。ミラーを適用してから STEP0 を掛ける
- **細い線(手描き背景)** `fp_fine_lines`: 塗り分けを2枚持って合成する。
  手描きの塗り(下限14度・稜線0.45、切れすぎの抑えあり)から線を作り、
  メカの塗り(下限5度・稜線0.25、**抑えなし** = 建物の角や窓枠まで全部分ける)
  の線をこの濃さで重ねる。背景の既定は 0.6。STEP3 のスライダーで生成後に
  その場で変えられる(細い線の部分だけ組み直す)。STEP0 は塗りを2回するので
  背景だけ時間が倍になる。0.35 ではアパートの窓枠が精密より明らかに少なく、
  BlenderKit 6体と町で 3 案を比べて決めた。メカの塗りにも抑え(島/面 0.08)を
  掛けていた間は、箱を結合した低ポリの建物が「切れすぎ」と誤判定されて
  179度まで上げられ、建物の角に線が出なかった(町の家: 137面に箱23個)
- **STEP0 に「仕上がり」のプルダウン**。v2.7 を壊さないための切り分け。
  - **精密(メカ)**: v2.7 と同じ出力。下限5度・稜線0.25・強弱なし。既定
  - **キャラ(手描き)**: AO の強弱 ON、下限14度・稜線0.45、しきい値の計測
    まで STEP0 が1ボタンで済ませる(測らないと既定値のまま動いていた)
  - **手描き背景**: キャラの中身に、セット向けの特殊処理を足す。
    奥の扱い(細く1.0・減らす2.0・薄く0.35。輪郭 = 深度の段差は減らさない)、
    葉を房にまとめる(4)、葉の隙間埋め(6px)、線の濃さ 0.75、線の強さ 0.5
    (背景は細く。太いのは寄ったときだけ)、地面(他のどの物よりも2倍以上
    広い薄い平面)を塗らない、深度チャンネル OFF(地平線の帯)。
    30 体を並べた町のデモ(30秒)で決めた
    塗り分けを2枚持ち(下の「細い線」)、メカの線を 0.6 で重ねる。
  下の「なめらかな形の分割」「線の強弱」はすべてキャラ側に入る。
  精密側は v2.7 から値を変えていない(テスト 49 本目で3つを確かめる。
  公開前に BlenderKit 8 体の精密出力を開発初期の出力と比べ、全画素一致)。
  以下で「強弱」とあるのは、この「キャラ(手描き)」のこと。
- **詰まりの守りをなだらかに**: 隙間のマスクは画素ごとに 0/1 なので、
  線に沿って太い区間と細い区間が交互に出て、車のフェンダーの縁が破線に
  見えた(実測: 町のデモ、守り 0 だと連続した1本の線になるが車輪が黒く
  埋まる)。到達幅の 1.5 倍でぼかして 1.5 倍に戻す。輪郭が1本の線に
  なり、車輪や帆船・機関車の詰まりは守られたまま(画像で確認)。
- **強弱の線に SMAA + 縁のぼかし**: 太らせた線は2値で決めるので、縁が
  ギザギザのまま 50% 縮小に入り、1080p で縁が 0/0.5/1 の3値しか無かった
  (実測: 町のデモを4倍拡大)。縮小の前に SMAA(しきい0.05・コントラスト
  0.1)と 2px のぼかし(`fp_lw_soften`、1080p で 1px)を掛ける。1px では
  SMAA だけとほぼ同じで、2px で段が消えた。精密(v2.7)は触らない。
- **線の濃さ** `fp_lw_ink`: 一番濃い線の表示上の濃さ。1 = 黒(既定)、
  0.75 で濃い灰色。町のデモは 0.75。
- **葉を房にまとめる(手描き背景)**: 葉カードは1枚ずつ別の島で、隣の葉と
  必ず違う色になるため葉ごとに輪郭が出て、遠くでは黒い塊になる。小さい
  島を 3D 位置で K 房に分けて房ごとに1色にする(`mesh_islands.
  clump_small_islands`、既定 0 = 通らない)。葉かどうかは「小さい島が
  200 以上、面積の半分以上、面数中央 4 以下、辺の 3 割以上がメッシュの端」
  で判定する。数だけで判定すると機関車のリベット(2万島)まで房になった
  (実測)。ヤシの小葉は房ではなく稜線の起伏が線を出しており、まだ黒い。
- **葉の隙間を埋める(手描き背景、既定 0)**: 葉の間から空が見える穴の縁が
  線になるので、検出グループの手前で AOV の穴を Inpaint で埋め、閉じた
  alpha を渡す(`gap_fill.py`)。alpha を渡さないと白に載せる段で穴が戻る。
- **線の強弱(くぼみ)**: 開いたところ(輪郭)を太く、くぼみ(AO)に入る
  ところほど細くする。線画の常識どおりで、くぼみに入る所で細くなるのが
  入り抜き。当初は逆(くぼみを太く)にしていて、目や眉が太く輪郭が細い
  絵になって「逆では」と指摘を受けた。`fp_lw_deep_thick` で戻せる。
  強弱を作るには「線に沿って連続に変わるスカラー場」
  が必要で、曲率・線の密度・形の太さはどれも線の途中で不連続に飛ぶため
  使えなかった。コンポジタに届くパスを全て出して比べた結果、AO と光
  (Diffuse Direct)だけが使えた。AO は形だけで決まるので、光と違って
  カメラを回しても絵柄が動かない。
  実測(スザンヌ・120フレーム、段分けと濃さの強弱を入れた後): 真っ黒率
  45.1% -> 97.7%、隣接フレーム差 1.67% -> 1.27%(出荷どおりの経路。
  「なし」側は仕上がり「精密」= v2.7 そのもの)。
- **詰まった線は太らせない**: 薄い縁を斜めから見るとメッシュの輪が
  数本の平行線になり、まとめて太って黒い帯になる(スザンヌの耳、車の
  グリル)。線の密度を見て、詰まっているところは太らせる前の線に戻す。
- **島を細かく切らない / 線を弱める**: 強弱ONのときに線の量を減らす。
  島の細かさは既定 1.0(無効)。0.4 まで下げると耳は綺麗になるが、
  線の感度 0.5 ではスザンヌの口の輪郭が消える(感度0.25なら両立)。
- **奥の扱い(深度)**: 「奥ほど細く」「奥ほど線を減らす」「奥ほど薄く」。
  町のように奥へ続くセットで、遠くのモデルは線が詰まって黒い塊になる。
  24案を同じ2フレームで並べて比べた(dev/note_assets/eval_far_ideas.py):
  既存の「遠景つぶれ軽減」は局所密度なので強弱の太い線が全部引っかかり
  手前まで灰色になる、奥をぼかすのは塊が灰色の塊になるだけ、局所的に
  1px 削る/開きはほぼ効かない。一番絵に見えたのは「奥ほど強弱を切って
  線を間引き、少し紙の色へ寄せる」だった。深度パスから奥度 0..1 を
  作り(距離はしきい値の計測と一緒に測る: 線の画素の深度の 5%〜95% 点)、
  太らせる幅に (1 - 奥度) を掛け、検出グループの ColorRamp の手前で
  勾配を 1/(1 + (s-1)·奥度) にし、最後に紙の色へ寄せる。既定は全部 OFF
  (ノードを1つも挿さない)。背景の深度はクリップ距離なので、奥度は
  シルエットの中だけで取り正規化ぼかしで外へ伸ばす(そうしないと手前の
  輪郭まで外側が削れた。テスト 51 本目)。
- しきい値を測るボタン。線の画素における 1-AO の分位点を1回のレンダで
  読む。実モデル11体で 20%点が 0.0013〜0.0193 と15倍ひらくため、
  固定値では配れない。カット内で固定するのはフレームごとに測り直すと
  ちらつくため(実測26%)。

- **太さを段ではなく連続に決める**。以前は 5 段の硬いしきい値と整数の
  膨張で太さを決めていた。段分けが働いていなかった頃(下の Fixed)は
  実質 1 段で、太さの変化は元の線の濃淡から連続的に出ていたので絵は
  綺麗だった。段分けを直した途端、1本の線の途中で太さが段になって
  切れ、眉や耳の縁が別々の線に見えた(実測)。段の境目で線が切れるのは
  設計の問題なので段をやめた。線の芯を距離で薄れる形(Feather)に膨らませ、
  「どこまでを線と見なすか」のしきい値をくぼみの深さで連続的に動かす。
  しきい値は float なので、整数画素の壁(6/5/4/3/2 が縮小後 3/2/2/2/1 に
  潰れる)も無くなった。太さの範囲は 12/8/5/3/2 の最小〜最大
  (縮小後 2〜7px)。スザンヌの耳・カメラのレンズ・車のグリルで詰まりの
  守りが効くことを確認。
- **濃さの強弱** (`fp_lw_tone`, 既定 0.25)。太さと同じ深さから連続に
  決める。一番深い所は黒のまま、一番浅い所は表示で (1 - 0.6×tone)。
  掛け算はリニアで行われ出力で sRGB に変わるので、表示の濃さを決めて
  からリニアの倍率へ変換して掛ける(そうしないとリニア 0.78 が表示 0.5
  になった)。0.5 だと輪郭が灰色になって汚く見えたので 0.25。
- くぼみのなめらかさ(`fp_lw_ao_blur`)の既定を 4 -> **12**。太さは深さに
  連続に追従するので、深さを線に沿ってならすと入り抜きがなめらかになる。
  「太い層は途切れ、細い層はつながる、それを重ねる」という案は、いまの
  連続版がその層を無限に重ねた形で、残っていたのは深さの変わる速さ
  だった。4/12/24 を出荷どおりの経路で比べ、12 は眉の端がなめらかに
  細り、カメラのレンズと車も締まって見えた。24 は眉全体が太くなる。
- 評価スクリプトと動画は pct=100 で解像度を2倍にして保存時に縮めて
  いたが、アドオンは倍率を見て太さとぼかしを pct/200 で割るので、その
  経路では**強弱が本来の半分**で写っていた。使う人は細線化 ON(pct=200)
  が既定なので、これまで見せていた絵は実物より弱かった。出荷どおりの
  経路(pct=200 でアドオンに縮小させる)に揃えた。

### Changed
- **なめらかな形の分割(強弱スタイルのとき)**。「一様に滑らかで構造線が無い」
  モデルは分割線を人工的に作るが、下限が 5度 だとなめらかに曲がる面の
  どこでも超えるので、切れ目が形と関係ない場所に落ちていた。下限を
  **5度 -> 14度**、STEP0 が入れる稜線の起伏を **0.25 -> 0.45** にした
  (仕上がり「強弱」のとき。「精密」は v2.7 のまま 5度 / 0.25)。
  役割が別で、両方いる。角度はスザンヌの耳を横切る線を消し(13->14度で
  直る)、稜線は角度を上げたときに消える口の輪郭を取り戻す。
  BlenderKit の実アセット60体で確認:
  - 下限が触るのは4体だけ。残り56体は構造線・曲率・多パーツ・リグ・
    サブサーフのどれかで先に決まるので下限に届かない
  - 稜線は全体に効く。0.25/0.35/0.45/0.50 を振ってどの値でもどのモデルも
    内側の線が減らず(最小 99.9%)、中央は 100/111/123/132%。0.50 は上限で
    余地が無く、ハンガーの屋根が詰まりはじめるので 0.45
  - 平らな面では稜線の残差がほぼゼロなので、メカと壺は1画素も変わらない
  - 「内側の線」が減った3体は原寸で見ると全部改善だった。eggs_bowl は
    卵1個ごとの偽の同心円(輪切りのオリーブに見えた)が消えて輪郭が残り、
    formal-shoe は舌革の階段状のギザギザが消え、cleaver_knife は柄の
    余計な斜線が消えた。数値の減少はゴミが減った量で、後退は0体

### Removed
- **使っていない・内部のつまみを整理**(v2.8 の開発中に足したもの13個)。
  絵は変わらない(BlenderKit 5体 x 精密/キャラ/手描き背景 + 町で前後を画像比較)。
  - 消した: 曲面ぼかし3個(既定OFFで UI にも無く、STEP0 も使わない)、
    詰まりの半径・しきい値(どこからも参照されていない)、島を細かく切らない・
    線を弱める(既定 1.0 = 何もしない。2枚の塗りで役目を終えた)
  - 定数にした: くぼみの半径 0.6・くぼみのなめらかさ 12・2値化 0.7・
    濃さ 1.0・濃さの強弱 0.25・くぼみを太く(逆向き、OFF 固定)
  - UI から外した: 遠景のつぶれ軽減(v2.6 から。どのモードも使わず、手描き
    背景の奥の扱いに置き換わった。.blend の値と API は残る)、測った
    しきい値4つ・奥の始まり/終わりの表示(計測ボタンは残す)
- STEP0 のチェック項目は閉じた「詳細」へ。サイドバーで「…」に切れていた
  名前は1行上に出す。ツールチップ・進み具合の表示など 113 件を日本語化

### Fixed
- **モノクロプレビューが STEP3 の作り直しで外れていた**。白プレビューだけ
  掛け直していて、表示はモノクロなのに材質の色で出た(町が灰色になった)。
  テスト 57 本目
- **5.x でモノクロプレビューが動いていなかった**。コンポジタの Map Range が
  5.x に無く、エラーで止まっていた。ShaderNodeMapRange に読み替える
- **細線化したときのアニメーションレンダー**。F12 は等倍で出るように
  したが(下の項)、アニメーションでは縮小を外すフック(render_pre)が
  効かず、2倍のキャンバスに半分の絵が入っていた(実測: 被写体の幅 0.50)。
  render_init/complete に移して両方で等倍にする(テスト 55 本目)。
- **強弱を BlenderKit 60体で回して見つけた5件**(仕上がり「強弱」のみ)。
  精密側は触っていない。
  - 帆船の船体と機関車のボイラーが黒い塊になった。詰まりの守りが
    「線の密度」で測っていて、密度 1(真っ黒)でないと 100% にならず、
    密度 0.3 の所では 2 割しか効かなかった。密度をやめ、「太らせたら
    隣とつながるか」を閉じ(膨張→収縮)で直接測る。半径を 3段(最大幅の
    1/2, 1, 2 倍)にして、狭い所ほど強く抑える。守りは太らせた絵と元の
    線を混ぜるのではなく、広がりそのものをゼロまで縮める(混ぜると
    半端な灰色になり、点線にも見えた)。芯が消えないようしきい値に
    余裕を入れる(Feather の芯はちょうど 1.0 で > 1.0 は偽)
  - 芯の2値化 0.15 -> **0.7**。細い線が密集して灰色に見える所が全部
    芯になって塗り潰れた。芯は「濃い ∧ 周り(3px ぼかし)も濃い」画素だけ
    にし、芯から外れた薄い線は**元の線を MAX で足し戻す**ので消えない
  - テレビのベゼル内側に点線が並んだ。太らせた領域の先端(Feather の裾)
    でしきい値が AO の粒で揺れて孤立点になっていた。裾を使わないよう
    半径を最大幅の 1.5 倍にし、ぼかした ink が半分未満の孤立点は落とす
  - 平板の縁に周期的なうねり。Feather の距離が斜めの縁で階段状に落ちる
    ので、3px ぼかしてならす
  - **輪郭を外側へ太らせた分が透明背景で消えていた**。シルエットの外は
    レンダーレイヤーのアルファが 0 で、Set Alpha がそれをそのまま使う。
    線を描いた画素は MAX でアルファも立てる(テスト t50)
  - gain 1.4 -> 1.0、線を弱める倍率 1.2 -> 1.0。どちらも上の点線の犯人
    候補として調べて違ったが、足し戻しがある今は要らない
  - 詰まりの半径・しきい値のつまみをパネルから外した(閉じで直接測る
    ので使わない。プロパティは互換のため残す)
- **密なモデルは最大幅を自動で下げる**。フルHD で5体を回すと、帆船の
  索具や機関車の足回りは間隔が中くらいの線が全部太って画面が重かった
  (詰まりの守りは「隣とつながる所」しか止めない)。しきい値の計測で
  線の密度(シルエットに占める線の割合)も測り、密度 5% で最大幅そのまま、
  50% で 1/4 に直線で落とす。実測(フルHD): スザンヌ 0.02 / カメラ 0.22 /
  メカ 0.41 / 機関車 0.42 / 帆船 0.55。
- **しきい値の計測が太らせた後の絵を読んでいた**。STEP3 が強弱の鎖を
  組んでから測るので、合成の入り口を辿ると鎖の出口に当たる。密度が
  0.08 -> 0.54 に膨れ、AO のしきい値も太らせた画素で決まっていた。鎖の
  入口(元の線)を読む。計測の解像度も 50% -> 100%(50% だと線が相対的に
  倍の太さになり密度が膨れた)。計測中は白プレビューを立てる(陰影を
  線と数えないため)。
- **線の強弱の段分けが働いていなかった**。しきい値の計測は生の AO を
  25% で PNG(8bit)に書いて読み、合成は 4px ぼかした AO を使っていた。
  ぼかしは透明な背景(AO=0)を輪郭へ引き込むので合成側の d は計測側より
  1桁大きく、線の画素の 88% が一番細い段に入っていた(実測: しきい値
  0.004〜0.094 に対し合成側の 20% 点が 0.136。最初のしきい値 0.0039 は
  1/255 = 8bit の量子化そのもの)。段の割合は [0.2, 0.4, 2.7, 8.7, 88] %。
  これまで「強弱」に見えていたのは元の線の濃淡で、段は効いていなかった。
  直し方: ぼかす前に背景を「開いている(AO=1)」で埋め、計測も合成と同じ
  鎖(dep_chain)を通した値を EXR で読む。ぼかしの半径はレンダー倍率で
  割る。直した後の割合は [37, 13, 13, 15, 21] %。
- **段の向きが逆だった**。一番浅い所に一番太い段が当たっていた
  (コメントは「くぼんでいる側から太い順」だったが、ループが k=0 =
  一番浅い側から levels[0] を当てていた)。段分けが働いていなかったので
  表に出ず、直した途端に輪郭だけが太った(実測)。深い側を太く、深い側を
  濃く、に揃えた(その後、段そのものを連続に置き換えた。上の Added)。
  テスト 48 本目は最終画像で「深い所の線ほど周りのインクが多い」ことを
  確かめる。段の頃に向きを戻すと 47/48 で落ちることを確認した。
- **細線化したときの F12 の出力**。コンポジタの中で 0.5 に縮めていたため、
  2倍のキャンバスに半分の大きさの絵が入っていた。実測(1920x1080 を指定):
  細線化OFF は 1920x1080 で被写体が31.6%を占めるのに対し、ON は
  3840x2160 で 7.9% しかなかった。ファイル出力(STEP5)はバッファの
  大きさで書くので正しく、F12 と STEP5 で絵が食い違っていた。
  レンダーの間だけ Composite 側の縮小を外し、等倍で出すようにした
  (占有 31.6% で一致)。ビューポートのプレビューとファイル出力は
  今までどおり。
- 2値化が既存機能を無効にしていた。線の濃さを変える機能が、強弱の
  2値化(0.15)で元に戻っていた。実測(インク量の変化率): 遠景つぶれ軽減
  0->0.9 が 73.26% -> 1.47% になっていた。太さは2値化した芯から、
  濃さは元の線から取るように直して 32.82% まで回復。

## [2.7.0] - 2026-08-23
### Changed
- **Line sensitivity now defaults to 0.5 (was 1.0), and STEP0 sets it.**
  The paint separation was already correct, but many boundaries never
  reached the detection threshold, so no line appeared. Whether a line
  shows is decided by RGB distance (measured cut-off 0.05-0.14), and
  neighbouring colours that are close in luminance - pale blue against
  white, for instance - sat below it.

  Measured ink at 1920, no supersampling:

  | model | 1.0 | 0.5 |
  |---|---|---|
  | tank | 0.0855 | 0.0919 |
  | mech | 0.1048 | 0.1110 |
  | ship | 0.0482 | 0.0534 |
  | camera | 0.0894 | 0.1004 |

  Rigging that used to break into dashes is now continuous, and no noise
  was introduced; the dense mech stays clean even at 0.35, so 0.5 leaves
  headroom. **This changes the output of existing files** - raise the
  slider back to 1.0 in STEP3 to get the previous look.

## [2.6.2] - 2026-08-08
### Fixed
- **A file saved in 5.2 and opened in 4.5 can now be repaired by pressing
  STEP3.** 5.x keeps the scene compositor as a *node group*; open that
  .blend in 4.x and the group stays wired in as `scene.node_tree`, which
  4.x cannot drive. Measured on a Suzanne line-art file:

  | | ink |
  |---|---|
  | as built in 5.2 | 0.0065 |
  | opened in 4.5 | 0.9286 (near black) |
  | 4.5, after pressing STEP3 — **before** this fix | **1.0000 (fully black — worse)** |
  | 4.5, after pressing STEP3 — after this fix | **0.0067 (recovered)** |

  A 4.x scene tree is embedded data and never appears in
  `bpy.data.node_groups`, so a tree that *is* in there came from 5.x.
  `compat.discard_foreign_scene_tree` detects exactly that and swaps in a
  fresh embedded tree before STEP3 builds. The manual previously told
  people to delete the node groups by hand; that section is rewritten.

- **Node group version stamps now include the Blender generation.** The
  4.x and 5.x graphs are built from different exported files, but both
  stamped the same version number, so a group carried across generations
  looked current and was never rebuilt. The stamp is now `2-4x` / `2-5x`.

  Verified in both directions and same-version: 4.5 -> 5.2 gives 0.0067 ->
  0.0065, and 4.5 -> 4.5 is unchanged at 0.0067.

## [2.6.1] - 2026-08-08
### Removed
- **"This to Quads" is gone.** It rewrote the mesh permanently and paid the
  cost of an Edit-mode round trip for it, but barely touched the drawing.
  Measured over 8 models: **6 of them came out with the ink ratio unchanged
  to the last digit**, while the time went up anyway — 0.6s to 7.1s on an
  A320, 6.5s to 22.9s on an Audi. Face count only moves when the mesh
  happens to have triangles to merge; the Edit-mode entry is paid either
  way. On a 10.6M-face production set it cost 31 seconds and 13.8 GB, and
  quietly cut the mesh from 10,594,485 to 9,040,042 faces — every time
  STEP1 was pressed. (`dev/batch/HANDOFF.md` had already recorded the same
  finding on 5 models in an earlier round.)

  Old files that still have the setting saved are unaffected: the property
  no longer exists, so the value is simply never read. Default output is
  unchanged — 360/360 colour attributes identical before and after removal.

### Added
- **STEP0 / STEP2 / STEP3 now say what they did.** They only ever popped up
  on failure, so a successful run looked like nothing had happened. Each
  now reports whether the node group was created, updated, or already up to
  date, along with its name and node count, the AOVs that were enabled, and
  the file-output passes and destination.

### Fixed
- `dev/batch/hash_paint.py` unpacked `append_objects()` backwards —
  it returns `(meshes, others)` — and normalised the scene against the
  armatures instead of the meshes. The 348/348 comparison it produced is
  still valid (both sides ran through the identical harness), but the tool
  was wrong and is fixed.
- `mesh_islands.py` built `loop_poly` assuming loops are packed in face
  order while the face-centre code explicitly honoured `loop_start`. Only
  one of the two would have been right on a mesh that broke the assumption.
  The check now lives in one place and both paths use it.
- `mesh_islands.connected_components` returned a silently wrong labelling
  if it hit its 200-round runaway guard. It raises now.
- `scripts/install_all.py` read the add-on version from a module that was
  still the pre-install one, so a freshly installed 2.6.0 reported 2.5.0.
  It reloads first, cross-checks against `bl_info` in the installed file,
  and fails the run if the two disagree.

## [2.6.0] - 2026-08-08
### Added
- **Far crush relief (STEP3).** In deep sets — a shop floor, a street, a
  classroom — distant props pack so tightly on screen that their lines
  merge into solid black. Measured on a corridor of 26 receding shelf rows
  at 1200px, the share of pixels whose entire 3x3 neighbourhood is ink:

  | distance | off | **amount 0.6** | amount 1.0 |
  |---|---|---|---|
  | near | 0.0001 | 0.0000 | 0.0000 |
  | mid | 0.1178 | **0.0000** | 0.0000 |
  | far | **0.2387** | **0.0000** | 0.0000 |
  | ink left in the far band | 0.4378 | **0.1419** | 0.0033 |

  Fading by distance would erase the far geometry along with the mess, so
  the trigger is **local line density** instead: crushing *is* saturated
  density, and a distant silhouette that is not crowded survives. Five
  nodes are inserted just before the group's `line` output —
  `alpha *= 1 - amount * clamp((blur(mask) - threshold) / (1 - threshold))`.
  Amount defaults to 0, which inserts nothing and leaves existing images
  bit-identical. Moving the slider re-applies in place; back to 0 removes
  the nodes and restores the original wiring.

  Note 1.0 is too strong (0.3% of the far lines survive); start at 0.5-0.7.

  The nodes are located by following the wiring back from the `line`
  output, not by node name — the same exported file yields different
  auto-assigned names on 4.2 and 4.5, which broke a name-based first cut.

### Performance
- **STEP1 no longer redoes the same mesh once per linked duplicate.** A
  production set (a department store) had 1,186 mesh objects sharing only
  159 mesh datablocks: summed over objects that is 711M faces against
  89.2M of actual data — the same mesh was painted up to 14 times, and
  every pass but the last was thrown away. Worse, the colour seed comes
  from the *object* name, so which pass won depended on iteration order.
  STEP1 now paints one representative per mesh datablock, chosen by lowest
  object name so the result no longer depends on selection order.

- **Island detection moved from bmesh to numpy arrays** (new
  `mesh_islands.py`). Everything it needs — loop→edge, loop→face, face
  normals, areas, centres, sharp/seam/material flags — comes out of
  `foreach_get` in one call each, so no BMesh is built at all.

  | mesh | before | after |
  |---|---|---|
  | 3,189,380 faces | 55.8s | **32.1s** |
  | 10,594,485 faces | 201.3s | **112.6s** |

  Connected components use Shiloach-Vishkin. Hooking *roots* rather than
  nodes is what makes it viable: the node-hooking version needed 96 rounds
  and 5.66s where root-hooking with edge contraction converges in 3 rounds
  and 0.24s.

  The paint output is unchanged, verified by sha1 over every colour
  attribute of 8 models: **348/348 identical**. Reaching that required
  reproducing three accidents of the old code, each found by measurement:
  BMesh reports a zero normal for degenerate faces where the mesh API
  returns (0,0,1), and `calc_face_angle` then returns exactly 60° for them;
  triangle centres differ by 1 ULP because the mesh API divides by 3 while
  BMesh multiplies by 1/3, and that coordinate feeds the colour-jitter
  hash; and Blender sums n-gon (n>=5) vertices in reverse order.

- **Cheaper preparation.** `apply_face_colors` writes all corners with one
  numpy `foreach_set` instead of walking `polygon.loop_indices` (8.7s on a
  3.2M-face mesh). The dihedral angle of each edge is computed once and
  shared between the auto-threshold and the boundary test (it used to run
  7.94M times over 4.79M edges). `many_loose_parts` only asks whether the
  selection has 8 or more parts, which is already true when 8 or more
  objects are selected, so nothing is counted at all in a large scene.
  `_channel_painted` reads each mesh datablock once, smallest first.

### Fixed
- `fp_batch.lineart_metrics` loaded the render with a relative path, which
  Blender resolves against something other than the working directory, so
  a batch run with a relative `--out` failed after rendering. Third place
  this same trap has appeared; resolved at the source now.

- **mask_color did nothing useful on Blender 5.x.** Reported by a user: on
  5.2, painting the mask channel only erased lines around brightness 0.2,
  had almost no effect from 0.4 to 0.8, and white did nothing at all. On
  4.2 / 4.3 / 4.5 the same file erased every painted area regardless of
  brightness, which is the intended behaviour for a mask.

  The 5.x compositor node group is a separate exported file. That export
  ran with a `try/except` around each node's property block, and 5.x moved
  `color_hue` / `color_saturation` / `color_value` from node properties to
  input sockets. The exporter hit an `AttributeError`, wrote
  `# skipped node properties (...)`, and dropped the **entire** block —
  name, label, position and socket values — for four nodes:

  | node | lost | consequence |
  |---|---|---|
  | Color Key (mask chain) | key colour black -> white default, tolerances | mask inverted |
  | Color Key.001 (inpaint) | key tolerances | slightly different matte |
  | Inpaint.001 | name / label only | none (default matched) |
  | Dilate/Erode | name / label only | none (defaults matched) |

  The mask chain keys out **black**; leaving it at the white default made
  painted (bright) areas transparent instead of opaque, flipping the
  channel. Restored the 4.x values. All four Blender versions now produce
  identical results, pinned by `t36`.

  Also checked and cleared as false alarms: `Filter` (Sobel),
  `Dilate/Erode` and `Set Alpha` merely moved their settings from node
  properties to input sockets in 5.x, with matching values; and the
  `Normal` -> `Vector Math (dot product)` port is exact — the compositor
  Normal node computes `-dot(in, normalize(dir))`, so direction
  `(-1,-1,-1)` equals a dot with `(0.5774, 0.5774, 0.5774)` (measured).

### Changed
- **STEP4 channel labels now say what the channels do.** `mask_color` was
  labelled "White erases lines" since the 2023 original, which reads as
  white-specific; brightness is in fact irrelevant, so it is now "paint to
  erase lines". `line_color` was labelled just "Line Color" with no hint
  that it sets line *darkness* and never adds lines; it is now
  "Line Color(line darkness)". Manual section 5 rewritten to match.
- **File Output passes are now selectable, and default to line / color /
  light.** The third slot used to be the shadow pass, which on EEVEE rarely
  comes out clean enough to use; diffuse direct light composites far more
  easily. Shadow is still available as an opt-in checkbox.

  | pass | source | default |
  |---|---|---|
  | line | PRO group output | on |
  | color | PRO group output | on |
  | light | Diffuse Direct render pass | on |
  | shadow | Shadow render pass | off |

  The checkbox name is the written filename. Unchecking everything skips
  the File Output node entirely. Only the passes you select get enabled on
  the view layer. The Render Layers socket for diffuse direct is `DiffDir`
  on 4.x and `Diffuse Direct` on 5.x; `compat.render_layer_socket` resolves
  either. Existing files: rerun STEP3 to rewire.
- **Generated node trees are now laid out automatically.** Coordinates came
  straight from the exported .blend, where nothing had been arranged: the
  PRO group had 97 overlapping node pairs out of 80 nodes, and 47 of its 97
  links ran right-to-left. STEP3 now runs a layered pass (longest-path
  layering + iterated barycentre ordering) over every tree it builds.

  | tree | overlaps | backward links |
  |---|---|---|
  | scene root | 1 -> 0 | 3 -> 1 |
  | AOV group | 11 -> 0 | 0 -> 0 |
  | PRO group | 97 -> 0 | 47 -> 0 |

  Positions only; links, socket values and render output are untouched
  (mecha still renders ink 0.03765 / silhouette 0.32275 / 1487 components).

### Performance
- **STEP1 is much faster on multi-part models.** Profiling a 138-part /
  889k-face asset showed 93% of the time inside `bpy.ops` calls, almost
  all of it `object.mode_set`: the per-object loop entered and left Edit
  mode for every object, and each switch re-evaluates the whole scene
  depsgraph, so the cost grew with part count.

  The bmesh was only ever read (islands are derived from faces/edges; the
  colours are written afterwards through the data API), so Edit mode was
  never needed. It now uses `bmesh.new()` + `from_mesh()`. Edit mode is
  only entered when "This to Quads" is on, which genuinely rewrites the
  mesh.

  `ensure_vertex_color` likewise stopped using
  `geometry.color_attribute_add` — the data API takes the object directly,
  where the operator worked on whatever was active and forced a mode
  switch per attribute (four per object).

  | model | parts / faces | before | after |
  |---|---|---|---|
  | mecha | 155 / 50k | 8.7 s | **1.32 s** |
  | tank | 43 / 421k | 19.4 s | **7.84 s** |
  | carriage | 138 / 889k | 191 s | **~15 s** |
  | C62 | 1 / 1279k | 28 s | 27.1 s |

  Output is bit-identical on the mecha (ink 0.03765, silhouette 0.32275,
  1487 components — same as the shipped v2.5.0).

### Added
- Blender 4.2 LTS and 4.3 are now covered by the test matrix. The full
  smoke suite (33 tests) runs on 4.2 / 4.3 / 4.5 / 5.2, and rendered line
  output stays within 1.1% ink across all four.
- `compat.HAS_AOV_IN_VIEWPORT_COMPOSITOR` marks whether the viewport
  compositor evaluates AOV outputs (4.3+).
- Support tier table in README and the manual.

### Fixed
- **Blank white viewport on Blender 4.2.** STEP2 and STEP3 both switched
  the viewport to Rendered mode unconditionally. Blender 4.2's viewport
  compositor does not evaluate AOV outputs, so the preview showed nothing
  but white. Measured by isolating the graph: a plain `Invert` and a node
  group both render fine in 4.2, only the AOV input comes through empty —
  so there is no way around it from the add-on side. On 4.2 the viewport
  is now left alone, the preview toggle is disabled with an explanation,
  and the panel says to render with F12.
- Minimum Blender version disagreed between `bl_info` (4.3.0) and
  `blender_manifest.toml` (4.2.0). Both are 4.2.0 now, and a test pins
  version and minimum-version agreement between the two files.

## [2.5.0] - 2026-07-26
### Added
- Blender 5.2 support. The same package now works on both 4.5 and 5.2.
  Version differences are absorbed in `compat.py`, and a 5.x-native
  compositor node script is shipped alongside the 4.x one.
- Progress bar for STEP1 / STEP0. Long vertex color passes no longer
  freeze Blender; the operator runs modally and can be cancelled with ESC.
- STEP0 now turns on the white material preview, so line art is visible
  right after the one-button setup.

### Changed
- Island boundaries are driven by sharp edges instead of Freestyle marks.
  The previous approach temporarily overwrote the user's sharp edges with
  the Freestyle marks and restored them afterwards, which was destructive
  and prone to leaving the mesh in a modified state. STEP1 no longer
  modifies the mesh at all.
  Note: Blender 5.0 removed the `use_freestyle_mark` Python property on
  mesh elements in favour of the attribute API; Freestyle itself and its
  edge marks are still available.
- STEP3 no longer opens a separate compositor window.
- The sidebar starts with only STEP0 expanded.

### Fixed
- Node groups are now regenerated when the shipped graph changes. Files
  containing an older group were previously stuck with it forever.
- Vertex color export honours `render_color_index`, so glTF exports carry
  the painted colors.
- Node export (`node_io`) produced scripts that failed to run when the
  tree contained an Anti-Aliasing node.
- Distribution zip no longer bundles development files.

## [2.4.0] - 2026-07-23
### Added
- Per-channel line strength sliders (STEP3): depth / mecha / bone /
  material / generate, live-updating the generated node group from the
  sidebar. 0 fully disables a channel (ramp colors whitened, restorable).
- White material preview toggle (STEP3): a compositor Mix switches the
  PRO group's Image input between the beauty pass and white, giving an
  instant pure-line-art preview without touching any material.
- 2x supersampling option (STEP3, and STEP0 default ON): render at 200%
  and scale the Composite / File Output results back to 50% for crisp
  1px lines.
- STEP0 per-item toggles, including automatic AOV configuration from the
  scene (painted-channel detection by value, material-ID linkage).
### Changed
- Depth channel reworked to a relative depth gradient
  (Sobel(Z) / (Z + 0.5)) instead of frame min-max normalization, which
  the far clip dominated; interior depth steps now produce lines and the
  depth slider is effective. Regenerate STEP3 nodes in existing files.
### Fixed
- Channel strength 0 previously still drew strong edges (gradients
  exceed the ramp's 1.0 position cap).

## [2.3.0] - 2026-07-18
### Added
- STEP0 "Full Auto": one button that analyzes the scene (rig detection,
  material blend modes), applies recommended settings and runs STEP1-3.
- Part tint (mecha color): touching objects get different brightness bands
  so part boundaries (hairline, collar, assembly seams) become lines.
- Hard boundary bones (`fp_bone_hard_names`): comma-separated bone names
  whose weight region is painted with the dominant color only, producing a
  line at the boundary (e.g. "head,neck" for a jaw line).
- Auto edge angle (STEP1): per-object sharp-edge threshold from the
  dihedral-angle distribution, with guards for rigged/multi-part models.
- Seam/material boundaries and minimum island area merge options for STEP1.
- Line sensitivity (STEP3): scales the node group's line-detection ramps.
- File Output in STEP3: optional node writing line / color / Shadow passes
  as PNGs (default `//render/`).
- STEP5 "Camera Batch Render": per-camera checkboxes and one button that
  renders every checked camera into `//camera_renders/NN_<camera>/`.
### Changed
- Sidebar UI reorganized into collapsible sub-panels (STEP0-STEP5) with
  fixed ordering; full Japanese/English translations for all new strings.
- Depth channel defaults strengthened (threshold 0.22 -> 0.15, darker line
  color) for clearer silhouette and step lines.
- STEP2/STEP3 core logic extracted to `fp_core.py`; operators are
  headless-safe (no UI popups in background mode).
### Fixed
- Crash when running STEP1 headless (popup menu in background mode).
- STEP1 failure on selected meshes with zero faces.

## [2.2.0] - 2026-07-10
### Added
- Reproducible color seed for Auto Vertex Color (STEP1): a "Random seed each run"
  toggle, a Seed field, and a randomize button. Turning the toggle off reproduces
  exactly the same island colors for a given seed and mesh.
### Changed
- Island color generation now uses a process-independent hash of the object name,
  so colors are reproducible across Blender sessions (previously the built-in
  `hash()` was salted per process).

## [2.1.2] - 2025-08-15
### Fixed
- Automatically enable Z-depth pass for compositing when generating Pro node

## [2.1.1] - 2025-08-01
### Changed
- Translation dictionary moved to `locale/*.po` files and loaded at runtime

## [2.1.0] - 2025-06-27
### Added
- Color-noise scale, min neighbor color distance, max color retries の 3 プロパティを追加
- メインパネルに UI スライダーを配置

## [2.0.0] - 2025-04-04

### Added
- Dynamic translation support for EnumProperty items using `items=callback() + pgettext()`
- Full Japanese translation coverage for Blender 4.3.2+
- `description()` method for operator tooltips

### Changed
- Panel structure restored to match main branch (UI clarity improved)
- Translation registration moved to be first in register() function
- Debug translation utilities removed to prevent interference

### Fixed
- Enum dropdown labels not being translated
- Tooltips and buttons displaying incorrect language under Japanese UI
