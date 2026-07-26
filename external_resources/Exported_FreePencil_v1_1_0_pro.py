import bpy



def _set_filter(node, value):
    """5.x は filter_type プロパティが Type 入力ソケットに移った。"""
    import bpy
    if bpy.app.version < (5, 0, 0):
        node.filter_type = value
        return
    _MAP = {'SOFTEN': 'Soften', 'SHARPEN': 'Box Sharpen',
            'SHARPEN_DIAMOND': 'Diamond Sharpen', 'LAPLACE': 'Laplace',
            'SOBEL': 'Sobel', 'PREWITT': 'Prewitt', 'KIRSCH': 'Kirsch',
            'SHADOW': 'Shadow'}
    sock = node.inputs.get('Type')
    if sock is not None:
        sock.default_value = _MAP.get(value, value)


def _nt(name):
    """Blender 5.x で共有ノードへ移った型名を読み替える。"""
    import bpy
    if bpy.app.version < (5, 0, 0):
        return name
    return {
        'CompositorNodeValToRGB': 'ShaderNodeValToRGB',
        'CompositorNodeMixRGB': 'ShaderNodeMixRGB',
        'CompositorNodeMath': 'ShaderNodeMath',
    }.get(name, name)


def create_node_tree_freepencil_v1_1_0_pro():
    ng = bpy.data.node_groups.new('FreePencil_v1_1_0_pro', 'CompositorNodeTree')
    ng.interface.new_socket(name='sample', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='color', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='line', in_out='OUTPUT', socket_type='NodeSocketColor')
    # 入力ソケット（default_value は旧 .blend と同一値。未接続ソケットは
    # この値のまま使われる前提でノードが組まれているため必ず設定する）
    s = ng.interface.new_socket(name='Image', in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (1.0, 1.0, 1.0, 1.0)
    s = ng.interface.new_socket(name='Alpha', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0
    s = ng.interface.new_socket(name='Depth', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0
    s = ng.interface.new_socket(name='mecha_color', in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    s = ng.interface.new_socket(name='bone_color', in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    s = ng.interface.new_socket(name='gen_color', in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    s = ng.interface.new_socket(name='mask_color', in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    s = ng.interface.new_socket(name='line_color', in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    s = ng.interface.new_socket(name='mat_color', in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    n_0 = ng.nodes.new('NodeReroute')
    n_0.name = 'Reroute'
    n_0.label = ''
    n_0.location = (-1460.3646240234375, 516.5006103515625)
    n_0.hide = False
    n_0.width = 16.0

    n_1 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_1.name = 'Mix.001'
    n_1.label = 'freepencil'
    n_1.location = (-1382.829345703125, -104.58700561523438)
    n_1.hide = True
    n_1.width = 100.0
    n_1.blend_type = 'MIX'
    n_1.use_alpha = False
    n_1.use_clamp = False
    n_1.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_2 = ng.nodes.new('CompositorNodeFilter')
    n_2.name = 'Filter.002'
    n_2.label = 'freepencil'
    n_2.location = (-1385.846923828125, -152.4720458984375)
    n_2.hide = True
    n_2.width = 100.0
    _set_filter(n_2, 'SOBEL')
    n_2.inputs[0].default_value = 1.0

    # 深度は相対勾配 |∇Z|/(Z+0.5) に変更(2026-07-23)。
    # 旧 Normalize は背景(遠クリップ)が分母を支配し、シーン内部の
    # 深度差(家具の前後など)が 0.001 以下に潰れて線にならなかった。
    # 相対勾配は「深度が何%変わったか」なのでシーンスケールに依らない
    n_3 = ng.nodes.new(_nt('CompositorNodeMath'))
    n_3.name = 'Normalize'  # 旧ノード名を維持(参照互換)
    n_3.label = 'freepencil'
    n_3.location = (-1373.765380859375, 178.70384216308594)
    n_3.hide = True
    n_3.width = 100.0
    n_3.operation = 'DIVIDE'
    n_3.use_clamp = True

    n_3b = ng.nodes.new(_nt('CompositorNodeMath'))
    n_3b.name = 'DepthDenom'
    n_3b.label = 'freepencil'
    n_3b.location = (-1373.765380859375, 210.0)
    n_3b.hide = True
    n_3b.width = 100.0
    n_3b.operation = 'ADD'
    n_3b.inputs[1].default_value = 0.5

    n_4 = ng.nodes.new('CompositorNodeFilter')
    n_4.name = 'Filter.001'
    n_4.label = 'freepencil'
    n_4.location = (-1370.630859375, 136.13937377929688)
    n_4.hide = True
    n_4.width = 100.0
    _set_filter(n_4, 'SOBEL')
    n_4.inputs[0].default_value = 1.0

    n_5 = ng.nodes.new('NodeReroute')
    n_5.name = 'Reroute.007'
    n_5.label = ''
    n_5.location = (388.550537109375, 505.73492431640625)
    n_5.hide = False
    n_5.width = 16.0

    n_6 = ng.nodes.new('NodeReroute')
    n_6.name = 'Reroute.004'
    n_6.label = ''
    n_6.location = (-1428.674072265625, -1101.8173828125)
    n_6.hide = False
    n_6.width = 16.0

    n_7 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_7.name = 'Mix.002'
    n_7.label = 'freepencil'
    n_7.location = (-1387.655029296875, -412.3651123046875)
    n_7.hide = True
    n_7.width = 100.0
    n_7.blend_type = 'MIX'
    n_7.use_alpha = False
    n_7.use_clamp = False
    n_7.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_8 = ng.nodes.new('CompositorNodeFilter')
    n_8.name = 'Filter.003'
    n_8.label = 'freepencil'
    n_8.location = (-1390.4134521484375, -458.7274169921875)
    n_8.hide = True
    n_8.width = 100.0
    _set_filter(n_8, 'SOBEL')
    n_8.inputs[0].default_value = 1.0

    n_9 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_9.name = 'Mix.012'
    n_9.label = 'freepencil'
    n_9.location = (-1387.655029296875, -709.3576049804688)
    n_9.hide = True
    n_9.width = 100.0
    n_9.blend_type = 'MIX'
    n_9.use_alpha = False
    n_9.use_clamp = False
    n_9.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_10 = ng.nodes.new('CompositorNodeFilter')
    n_10.name = 'Filter.004'
    n_10.label = 'freepencil'
    n_10.location = (-1390.4134521484375, -755.7199096679688)
    n_10.hide = True
    n_10.width = 100.0
    _set_filter(n_10, 'SOBEL')
    n_10.inputs[0].default_value = 1.0

    n_11 = ng.nodes.new('NodeReroute')
    n_11.name = 'Reroute.003'
    n_11.label = ''
    n_11.location = (-638.4863891601562, -1075.5462646484375)
    n_11.hide = False
    n_11.width = 16.0

    n_12 = ng.nodes.new('NodeReroute')
    n_12.name = 'Reroute.002'
    n_12.label = ''
    n_12.location = (-1390.1163330078125, -1068.9576416015625)
    n_12.hide = False
    n_12.width = 16.0

    n_13 = ng.nodes.new('NodeGroupInput')
    n_13.name = 'Group Input'
    n_13.label = ''
    n_13.location = (-1961.415771484375, 66.10179138183594)
    n_13.hide = False

    n_14 = ng.nodes.new(_nt('CompositorNodeValToRGB'))
    n_14.name = 'ColorRamp.002'
    n_14.label = 'freepencil'
    n_14.location = (-1231.8099365234375, -155.42649841308594)
    n_14.hide = False
    # ===== Compositor ColorRamp for n_14 =====
    # Original: 2 elements
    ramp = n_14.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2要素の場合: デフォルト要素を直接上書き
    # 要素0: pos=0.000000, color=(1.0, 1.0, 1.0, 1.0)
    # 要素1: pos=0.200000, color=(1.0, 0.0, 0.0, 1.0)
    
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    # 初期値調整(2026-07-16): チャンネル色は最終段 n_39 で「RGB平均→線の
    # 不透明度」として効く(平均が高いほど線が薄い)。他チャンネルと同様に
    # 暗色化+しきい値0.14(ボーン塗り自体はウェイト加重平均の柔らかい
    # ブレンドなので、通常このチャンネルから強い線は出ない)
    ramp.elements[1].position = 0.1400000000
    ramp.elements[1].color = (0.300000, 0.000000, 0.000000, 1.000000)
    # ColorRamp設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'

    # 検証


    n_15 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_15.name = 'Mix.003'
    n_15.label = 'freepencil'
    n_15.location = (-445.372314453125, 107.95846557617188)
    n_15.hide = True
    n_15.width = 100.0
    n_15.blend_type = 'MULTIPLY'
    n_15.use_alpha = False
    n_15.use_clamp = False
    n_15.inputs[0].default_value = 1.0

    n_16 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_16.name = 'Mix.004'
    n_16.label = 'freepencil'
    n_16.location = (-444.92645263671875, 61.34123992919922)
    n_16.hide = True
    n_16.width = 100.0
    n_16.blend_type = 'MULTIPLY'
    n_16.use_alpha = False
    n_16.use_clamp = False
    n_16.inputs[0].default_value = 1.0

    n_17 = ng.nodes.new('CompositorNodeSwitch')
    n_17.name = 'Switch.001'
    n_17.label = 'freepencil'
    n_17.location = (-939.1372680664062, -155.12098693847656)
    n_17.hide = False
    n_17.width = 100.0


    n_18 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_18.name = 'Mix.010'
    n_18.label = 'freepencil'
    n_18.location = (-781.5869750976562, -135.650146484375)
    n_18.hide = False
    n_18.blend_type = 'MIX'
    n_18.use_alpha = False
    n_18.use_clamp = False
    n_18.inputs[0].default_value = 1.0
    n_18.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_19 = ng.nodes.new(_nt('CompositorNodeValToRGB'))
    n_19.name = 'ColorRamp.005'
    n_19.label = 'freepencil'
    n_19.location = (-383.46453857421875, -283.0209655761719)
    n_19.hide = True
    n_19.width = 200.0
    # ===== Compositor ColorRamp for n_19 =====
    # Original: 2 elements
    ramp = n_19.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2要素の場合: デフォルト要素を直接上書き
    # 要素0: pos=0.000000, color=(0.0, 0.0, 0.0, 1.0)
    # 要素1: pos=0.377778, color=(1.0, 1.0, 1.0, 1.0)
    
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (0.000000, 0.000000, 0.000000, 1.000000)
    
    ramp.elements[1].position = 0.3777775168
    ramp.elements[1].color = (1.000000, 1.000000, 1.000000, 1.000000)
    # ColorRamp設定
    ramp.interpolation = 'CARDINAL'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    
    # 検証
    

    n_20 = ng.nodes.new('CompositorNodeColorMatte')
    n_20.name = 'Color Key.001'
    n_20.label = 'freepencil'
    n_20.location = (-448.48406982421875, 151.79574584960938)
    n_20.hide = True
    n_20.width = 100.0
    n_20.color_hue = 0.07666666805744171
    n_20.color_saturation = 0.17500001192092896
    n_20.color_value = 0.21666666865348816
    n_20.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_21 = ng.nodes.new('CompositorNodeFilter')
    n_21.name = 'Filter'
    n_21.label = 'freepencil'
    n_21.location = (-1375.7027587890625, 436.0093688964844)
    n_21.hide = True
    n_21.width = 100.0
    _set_filter(n_21, 'SOBEL')
    n_21.inputs[0].default_value = 1.0

    n_22 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_22.name = 'Mix'
    n_22.label = 'freepencil'
    n_22.location = (-1378.0037841796875, 480.1326599121094)
    n_22.hide = True
    n_22.width = 100.0
    n_22.blend_type = 'MIX'
    n_22.use_alpha = False
    n_22.use_clamp = False
    n_22.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_23 = ng.nodes.new('CompositorNodeSwitch')
    n_23.name = 'Switch.004'
    n_23.label = 'freepencil'
    n_23.location = (-943.3009033203125, 443.8624572753906)
    n_23.hide = False
    n_23.width = 100.0


    n_24 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_24.name = 'Mix.007'
    n_24.label = 'freepencil'
    n_24.location = (-780.9413452148438, 456.88909912109375)
    n_24.hide = False
    n_24.blend_type = 'MIX'
    n_24.use_alpha = False
    n_24.use_clamp = False
    n_24.inputs[0].default_value = 1.0
    n_24.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_25 = ng.nodes.new(_nt('CompositorNodeValToRGB'))
    n_25.name = 'ColorRamp'
    n_25.label = 'freepencil'
    n_25.location = (-1230.60107421875, 447.91632080078125)
    n_25.hide = False
    # ===== Compositor ColorRamp for n_25 =====
    # Original: 2 elements
    ramp = n_25.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2要素の場合: デフォルト要素を直接上書き
    # 要素0: pos=0.000000, color=(1.0, 1.0, 1.0, 1.0)
    # 要素1: pos=0.200000, color=(0.0, 0.0, 0.0, 1.0)
    
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    # 初期値調整(2026-07-16): mecha線しきい値 0.2→0.14(スイープで実測した
    # 感度0.5〜0.7の改善方向を既定に反映。fp_line_sensitivity でさらに調整可)
    ramp.elements[1].position = 0.1400000000
    ramp.elements[1].color = (0.000000, 0.000000, 0.000000, 1.000000)
    # ColorRamp設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    
    # 検証
    

    n_26 = ng.nodes.new(_nt('CompositorNodeValToRGB'))
    n_26.name = 'ColorRamp.001'
    n_26.label = 'freepencil'
    n_26.location = (-1224.64306640625, 149.02577209472656)
    n_26.hide = False
    # ===== Compositor ColorRamp for n_26 =====
    # Original: 2 elements
    ramp = n_26.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2要素の場合: デフォルト要素を直接上書き
    # 要素0: pos=0.000000, color=(1.0, 1.0, 1.0, 1.0)
    # 要素1: pos=0.300000, color=(0.0, 1.0, 0.0, 1.0)
    
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    # 初期値調整(2026-07-16): depth(シルエット)線。旧(0,1,0)は平均0.33で
    # 輪郭が65%グレーだった → 暗緑で濃度~90%に。しきい値 0.3→0.22
    # 強化(2026-07-18): 本番シーン(ARIAの部屋)で深度線が弱かったため
    # しきい値 0.22→0.15、色 (0,0.3,0)→(0,0.12,0) で濃度~96%に
    ramp.elements[1].position = 0.1500000000
    ramp.elements[1].color = (0.000000, 0.120000, 0.000000, 1.000000)
    # ColorRamp設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    
    # 検証
    

    n_27 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_27.name = 'Mix.009'
    n_27.label = 'freepencil'
    n_27.location = (-781.8668212890625, 163.2741241455078)
    n_27.hide = False
    n_27.blend_type = 'MIX'
    n_27.use_alpha = False
    n_27.use_clamp = False
    n_27.inputs[0].default_value = 1.0
    n_27.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_28 = ng.nodes.new('CompositorNodeSwitch')
    n_28.name = 'Switch.003'
    n_28.label = 'freepencil'
    n_28.location = (-937.5640869140625, 144.00184631347656)
    n_28.hide = False
    n_28.width = 100.0


    n_29 = ng.nodes.new(_nt('CompositorNodeValToRGB'))
    n_29.name = 'ColorRamp.003'
    n_29.label = 'freepencil'
    n_29.location = (-1229.496826171875, -439.9772033691406)
    n_29.hide = False
    # ===== Compositor ColorRamp for n_29 =====
    # Original: 2 elements
    ramp = n_29.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2要素の場合: デフォルト要素を直接上書き
    # 要素0: pos=0.000000, color=(1.0, 1.0, 1.0, 1.0)
    # 要素1: pos=0.500000, color=(0.0, 0.009075075387954712, 1.0, 1.0)
    
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    # 初期値調整(2026-07-16): gen線を暗青化(濃度~90%)、しきい値 0.5→0.35
    ramp.elements[1].position = 0.3500000000
    ramp.elements[1].color = (0.000000, 0.003000, 0.300000, 1.000000)
    # ColorRamp設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    
    # 検証
    

    n_30 = ng.nodes.new('CompositorNodeSwitch')
    n_30.name = 'Switch.002'
    n_30.label = 'freepencil'
    n_30.location = (-946.0177001953125, -452.8358459472656)
    n_30.hide = False
    n_30.width = 100.0


    n_31 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_31.name = 'Mix.011'
    n_31.label = 'freepencil'
    n_31.location = (-782.275390625, -456.4102783203125)
    n_31.hide = False
    n_31.blend_type = 'MIX'
    n_31.use_alpha = False
    n_31.use_clamp = False
    n_31.inputs[0].default_value = 1.0
    n_31.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_32 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_32.name = 'Mix.013'
    n_32.label = 'freepencil'
    n_32.location = (-782.275390625, -753.4027099609375)
    n_32.hide = False
    n_32.blend_type = 'MIX'
    n_32.use_alpha = False
    n_32.use_clamp = False
    n_32.inputs[0].default_value = 1.0
    n_32.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_33 = ng.nodes.new(_nt('CompositorNodeValToRGB'))
    n_33.name = 'ColorRamp.006'
    n_33.label = 'freepencil'
    n_33.location = (-1229.496826171875, -736.9696655273438)
    n_33.hide = False
    # ===== Compositor ColorRamp for n_33 =====
    # Original: 2 elements
    ramp = n_33.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2要素の場合: デフォルト要素を直接上書き
    # 要素0: pos=0.000000, color=(1.0, 1.0, 1.0, 1.0)
    # 要素1: pos=0.500000, color=(1.0, 0.009075075387954712, 1.0, 1.0)
    
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    # 初期値調整(2026-07-16): mat線を暗マゼンタ化(旧は平均0.67=33%濃度しか
    # 出ていなかった)、しきい値 0.5→0.35
    ramp.elements[1].position = 0.3500000000
    ramp.elements[1].color = (0.150000, 0.003000, 0.150000, 1.000000)
    # ColorRamp設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    
    # 検証
    

    n_34 = ng.nodes.new('CompositorNodeSwitch')
    n_34.name = 'Switch.006'
    n_34.label = '丸みの線'
    n_34.location = (-946.0177001953125, -749.8283081054688)
    n_34.hide = False
    n_34.width = 100.0


    n_35 = ng.nodes.new('CompositorNodeInpaint')
    n_35.name = 'Inpaint.001'
    n_35.label = 'freepencil'
    n_35.location = (-252.7880401611328, 130.02801513671875)
    n_35.hide = False
    n_35.distance = 0

    n_36 = ng.nodes.new('CompositorNodeInvert')
    n_36.name = 'Invert.001'
    n_36.label = 'freepencil'
    n_36.location = (68.92464447021484, 111.568115234375)
    n_36.hide = True
    n_36.inputs[0].default_value = 1.0

    n_37 = ng.nodes.new('CompositorNodeAlphaOver')
    n_37.name = 'Alpha Over.004'
    n_37.label = 'freepencil'
    n_37.location = (325.4501037597656, -364.7349548339844)
    n_37.hide = True
    n_37.inputs[0].default_value = 1.0
    n_37.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_38 = ng.nodes.new('CompositorNodeInvert')
    n_38.name = 'Invert'
    n_38.label = 'freepencil'
    n_38.location = (-279.2994689941406, -468.7112731933594)
    n_38.hide = False
    n_38.width = 100.0
    n_38.inputs[0].default_value = 1.0

    n_39 = ng.nodes.new(_nt('CompositorNodeValToRGB'))
    n_39.name = 'ColorRamp.004'
    n_39.label = 'freepencil'
    n_39.location = (31.499370574951172, -437.53955078125)
    n_39.hide = False
    n_39.width = 200.0
    # ===== Compositor ColorRamp for n_39 =====
    # Original: 2 elements
    ramp = n_39.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2要素の場合: デフォルト要素を直接上書き
    # 要素0: pos=0.000001, color=(0.0, 0.0, 0.0, 1.0)
    # 要素1: pos=0.827778, color=(1.0, 1.0, 1.0, 1.0)
    
    ramp.elements[0].position = 0.0000005020
    ramp.elements[0].color = (0.000000, 0.000000, 0.000000, 1.000000)
    
    ramp.elements[1].position = 0.8277776241
    ramp.elements[1].color = (1.000000, 1.000000, 1.000000, 1.000000)
    # ColorRamp設定
    ramp.interpolation = 'EASE'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    
    # 検証
    

    n_40 = ng.nodes.new('CompositorNodeDilateErode')
    n_40.name = 'Dilate/Erode'
    n_40.label = 'freepencil'
    n_40.location = (-136.20980834960938, -473.8502502441406)
    n_40.hide = False
    n_40.width = 100.0
    n_40.mode = 'STEP'
    n_40.distance = 0
    n_40.edge = 0.0

    n_41 = ng.nodes.new('NodeReroute')
    n_41.name = 'Reroute.001'
    n_41.label = ''
    n_41.location = (-443.4715881347656, 511.1692810058594)
    n_41.hide = False
    n_41.width = 16.0

    n_42 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_42.name = 'Mix.008'
    n_42.label = 'freepencil'
    n_42.location = (68.11617279052734, -91.61726379394531)
    n_42.hide = True
    n_42.width = 100.0
    n_42.blend_type = 'MIX'
    n_42.use_alpha = False
    n_42.use_clamp = False

    n_43 = ng.nodes.new('CompositorNodeInvert')
    n_43.name = 'Invert.002'
    n_43.label = 'freepencil'
    n_43.location = (321.9562072753906, -320.15362548828125)
    n_43.hide = True
    n_43.inputs[0].default_value = 1.0

    n_44 = ng.nodes.new('NodeGroupOutput')
    n_44.name = 'Group Output'
    n_44.label = ''
    n_44.location = (962.3602294921875, 187.07183837890625)
    n_44.hide = False

    n_45 = ng.nodes.new('CompositorNodeSetAlpha')
    n_45.name = 'Set Alpha'
    n_45.label = 'freepencil'
    n_45.location = (-72.31686401367188, -118.15411376953125)
    n_45.hide = True
    n_45.width = 100.0

    n_46 = ng.nodes.new('CompositorNodeAlphaOver')
    n_46.name = 'Alpha Over'
    n_46.label = 'freepencil'
    n_46.location = (74.92115783691406, -137.57373046875)
    n_46.hide = True
    n_46.width = 100.0
    n_46.inputs[0].default_value = 1.0
    n_46.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_47 = ng.nodes.new('CompositorNodeAlphaOver')
    n_47.name = 'Alpha Over.003'
    n_47.label = 'freepencil'
    n_47.location = (63.513275146484375, 161.19493103027344)
    n_47.hide = True
    n_47.inputs[0].default_value = 1.0
    n_47.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_48 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_48.name = 'Mix.005'
    n_48.label = 'freepencil'
    n_48.location = (-441.11676025390625, 11.718293190002441)
    n_48.hide = True
    n_48.width = 100.0
    n_48.blend_type = 'MULTIPLY'
    n_48.use_alpha = False
    n_48.use_clamp = False
    n_48.inputs[0].default_value = 1.0

    n_49 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_49.name = 'Mix.014'
    n_49.label = 'freepencil'
    n_49.location = (-441.11676025390625, -43.85590362548828)
    n_49.hide = True
    n_49.width = 100.0
    n_49.blend_type = 'MULTIPLY'
    n_49.use_alpha = False
    n_49.use_clamp = False
    n_49.inputs[0].default_value = 1.0

    n_50 = ng.nodes.new('CompositorNodeColorMatte')
    n_50.name = 'Color Key'
    n_50.label = 'freepencil'
    n_50.location = (-378.6430358886719, -328.555908203125)
    n_50.hide = True
    n_50.width = 191.45843505859375
    n_50.color_hue = 0.10000000149011612
    n_50.color_saturation = 0.13750000298023224
    n_50.color_value = 0.16249999403953552
    n_50.inputs[1].default_value = (0.0, 0.0, 0.0, 1.0)

    n_51 = ng.nodes.new('CompositorNodeAlphaOver')
    n_51.name = 'Alpha Over.002'
    n_51.label = 'freepencil'
    n_51.location = (347.9851989746094, 345.4447937011719)
    n_51.hide = True
    n_51.width = 171.73931884765625
    n_51.inputs[0].default_value = 1.0

    n_52 = ng.nodes.new('NodeReroute')
    n_52.name = 'Reroute.005'
    n_52.label = ''
    n_52.location = (-90.02175903320312, -1100.7286376953125)
    n_52.hide = False
    n_52.width = 16.0

    n_53 = ng.nodes.new('CompositorNodeAlphaOver')
    n_53.name = 'Alpha Over.001'
    n_53.label = 'freepencil'
    n_53.location = (359.64654541015625, 184.06251525878906)
    n_53.hide = False
    # 初期値調整(2026-07-16): 背景ベースを薄緑→白に(透過縁の緑にじみ防止、
    # 不透明ビューでも紙らしい見た目に)
    n_53.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_54 = ng.nodes.new('CompositorNodeSwitch')
    n_54.name = 'Switch.005'
    n_54.label = 'freepencil'
    n_54.location = (565.5455322265625, 206.56114196777344)
    n_54.hide = False
    n_54.width = 100.0

    n_55 = ng.nodes.new('CompositorNodeSetAlpha')
    n_55.name = 'Set Alpha.001'
    n_55.label = 'freepencil'
    n_55.location = (322.1084899902344, -270.73992919921875)
    n_55.hide = True

    n_56 = ng.nodes.new('CompositorNodeAntiAliasing')
    n_56.name = 'Anti-Aliasing.001'
    n_56.label = 'freepencil'
    n_56.location = (347.09661865234375, 306.0675354003906)
    n_56.hide = True

    # (2026-07-17) bone チャンネルのぼかし+細線化チェーン(n_57〜n_61)は
    # ユーザー判断で撤去: ボーン塗りは元のウェイト加重平均(柔らかいブレンド)
    # が正で、境界を線として出す方式自体が不要だった。

    # --- version-aware helper for Switch sockets ---
    is_45_plus = bpy.app.version >= (4, 5, 0)

    def sw_idx_off():
        # 4.5+: 0=Check,1=Off,2=On / 4.4-: 0=Off,1=On
        return 1 if is_45_plus else 0

    def sw_idx_on():
        return 2 if is_45_plus else 1

    def set_check(sw, value=True):
        if hasattr(sw, "check"):
            sw.check = bool(value)
        elif hasattr(sw, "switch"):
            sw.switch = bool(value)
        if is_45_plus:
            for lk in list(sw.inputs[0].links):
                sw.id_data.links.remove(lk)

    set_check(n_17, True)
    set_check(n_23, True)
    set_check(n_28, True)
    set_check(n_30, True)
    set_check(n_34, True)
    set_check(n_54, True)

    # --- legacy implicit color->float conversion (RGB average) ---
    # Blender 4.5+ の新コンポジターは色→float の暗黙変換が輝度ベースに
    # 変わったため、旧ファイル読込時に Blender 自身が挿入するのと同じ
    # Normal(-1,-1,-1) + Math(MULTIPLY 1/sqrt(3)) を挟んで
    # 2.9x 当時の RGB 平均変換を再現する。
    def link_avg(from_sock, to_sock):
        if not is_45_plus:
            ng.links.new(from_sock, to_sock)
            return
        nrm = ng.nodes.new('CompositorNodeNormal')
        nrm.label = 'freepencil'
        nrm.hide = True
        nrm.outputs[0].default_value = (-1.0, -1.0, -1.0)
        mul = ng.nodes.new(_nt('CompositorNodeMath'))
        mul.label = 'freepencil'
        mul.hide = True
        mul.operation = 'MULTIPLY'
        mul.inputs[1].default_value = 0.5773502588272095
        x, y = from_sock.node.location
        nrm.location = (x + 40.0, y - 30.0)
        mul.location = (x + 90.0, y - 30.0)
        ng.links.new(from_sock, nrm.inputs[0])
        ng.links.new(nrm.outputs[1], mul.inputs[0])
        ng.links.new(mul.outputs[0], to_sock)

    # links:
    # Debug: リンク情報
    # Link 0: Group Input[Alpha] -> Mix[Fac]
    ng.links.new(n_13.outputs[1], n_22.inputs[0])
    # Link 1: Group Input[Depth] -> Sobel(生Z) と 分母(Z+0.5) [相対深度勾配]
    ng.links.new(n_13.outputs[2], n_4.inputs[1])
    ng.links.new(n_13.outputs[2], n_3b.inputs[0])
    # Link 2: Group Input[mecha_color] -> Mix[Image]
    ng.links.new(n_13.outputs[3], n_22.inputs[2])
    # Link 3: Group Input[bone_color] -> Mix.001[Image]
    ng.links.new(n_13.outputs[4], n_1.inputs[2])
    # Link 4: Group Input[gen_color] -> Mix.002[Image]
    ng.links.new(n_13.outputs[5], n_7.inputs[2])
    # Link 5: Group Input[Image] -> Reroute[Input]
    ng.links.new(n_13.outputs[0], n_0.inputs[0])
    # Link 6: Group Input[line_color] -> Reroute.004[Input]
    ng.links.new(n_13.outputs[7], n_6.inputs[0])
    # Link 7: Group Input[mask_color] -> Reroute.002[Input]
    ng.links.new(n_13.outputs[6], n_12.inputs[0])
    # Link 8: Reroute.007[Output] -> Group Output[color]
    ng.links.new(n_5.outputs[0], n_44.inputs[1])
    # Link 9: Mix[Image] -> Filter[Image]
    ng.links.new(n_22.outputs[0], n_21.inputs[1])
    # Link 10: Mix.001[Image] -> Filter.002[Image]
    ng.links.new(n_1.outputs[0], n_2.inputs[1])
    # Link 11: Mix.002[Image] -> Filter.003[Image]
    ng.links.new(n_7.outputs[0], n_8.inputs[1])
    # Link 12: Filter[Image] -> ColorRamp[Fac]  (color->float: RGB average)
    link_avg(n_21.outputs[0], n_25.inputs[0])
    # Link 13: Sobel(Z) -> ÷(Z+0.5) -> ColorRamp.001[Fac] [相対深度勾配]
    link_avg(n_4.outputs[0], n_3.inputs[0])
    ng.links.new(n_3b.outputs[0], n_3.inputs[1])
    ng.links.new(n_3.outputs[0], n_26.inputs[0])
    # Link 14: Filter.002[Image] -> ColorRamp.002[Fac]  (color->float: RGB average)
    link_avg(n_2.outputs[0], n_14.inputs[0])
    # Link 15: Filter.003[Image] -> ColorRamp.003[Fac]  (color->float: RGB average)
    link_avg(n_8.outputs[0], n_29.inputs[0])
    # Link 16: (旧 Normalize -> Filter.001 は相対深度勾配化により廃止)
    # Link 17: Mix.009[Image] -> Mix.004[Image]
    ng.links.new(n_27.outputs[0], n_16.inputs[1])
    # Link 18: Mix.010[Image] -> Mix.005[Image]
    ng.links.new(n_18.outputs[0], n_48.inputs[1])
    # Link 19: Mix.005[Image] -> Mix.004[Image]
    ng.links.new(n_48.outputs[0], n_16.inputs[2])
    # Link 20: Mix.004[Image] -> Mix.003[Image]
    ng.links.new(n_16.outputs[0], n_15.inputs[2])
    # Link 21: Reroute[Output] -> Reroute.001[Input]
    ng.links.new(n_0.outputs[0], n_41.inputs[0])
    # Link 22: Reroute.002[Output] -> Reroute.003[Input]
    ng.links.new(n_12.outputs[0], n_11.inputs[0])
    # Link 23: Reroute.004[Output] -> Reroute.005[Input]
    ng.links.new(n_6.outputs[0], n_52.inputs[0])
    # Link 24: ColorRamp.003[Image] -> Switch.002[On]
    ng.links.new(n_29.outputs[0], n_30.inputs[sw_idx_on()])
    # Link 25: ColorRamp.002[Image] -> Switch.001[On]
    ng.links.new(n_14.outputs[0], n_17.inputs[sw_idx_on()])
    # Link 26: ColorRamp.001[Image] -> Switch.003[On]
    ng.links.new(n_26.outputs[0], n_28.inputs[sw_idx_on()])
    # Link 27: Group Input[Alpha] -> Mix.001[Fac]
    ng.links.new(n_13.outputs[1], n_1.inputs[0])
    # Link 28: Group Input[Alpha] -> Mix.002[Fac]
    ng.links.new(n_13.outputs[1], n_7.inputs[0])
    # Link 29: Reroute.005[Output] -> Mix.008[Image]
    ng.links.new(n_52.outputs[0], n_42.inputs[2])
    # Link 30: Color Key.001[Image] -> Inpaint.001[Image]
    ng.links.new(n_20.outputs[0], n_35.inputs[0])
    # Link 31: Mix.003[Image] -> Color Key.001[Image]
    ng.links.new(n_15.outputs[0], n_20.inputs[0])
    # Link 32: Inpaint.001[Image] -> Set Alpha[Image]
    ng.links.new(n_35.outputs[0], n_45.inputs[0])
    # Link 33: Invert[Color] -> Set Alpha[Alpha]  (color->float: RGB average)
    link_avg(n_38.outputs[0], n_45.inputs[1])
    # Link 34: Dilate/Erode[Mask] -> Invert[Color]
    ng.links.new(n_40.outputs[0], n_38.inputs[1])
    # Link 35: Alpha Over[Image] -> ColorRamp.004[Fac]  (color->float: RGB average)
    link_avg(n_46.outputs[0], n_39.inputs[0])
    # Link 36: Set Alpha[Image] -> Mix.008[Image]
    ng.links.new(n_45.outputs[0], n_42.inputs[1])
    # Link 37: Set Alpha[Image] -> Alpha Over[Image]
    ng.links.new(n_45.outputs[0], n_46.inputs[2])
    # Link 38: Alpha Over[Image] -> Switch.005[Off]
    ng.links.new(n_46.outputs[0], n_54.inputs[sw_idx_off()])
    # Link 39: Color Key[Image] -> Dilate/Erode[Mask]  (color->float: RGB average)
    link_avg(n_50.outputs[0], n_40.inputs[0])
    # Link 40: Reroute.003[Output] -> ColorRamp.005[Fac]  (color->float: RGB average)
    link_avg(n_11.outputs[0], n_19.inputs[0])
    # Link 41: ColorRamp.005[Image] -> Color Key[Image]
    ng.links.new(n_19.outputs[0], n_50.inputs[0])
    # Link 42: ColorRamp[Image] -> Switch.004[On]
    ng.links.new(n_25.outputs[0], n_23.inputs[sw_idx_on()])
    # Link 43: Switch.003[Image] -> Mix.009[Image]
    ng.links.new(n_28.outputs[0], n_27.inputs[2])
    # Link 44: Switch.001[Image] -> Mix.010[Image]
    ng.links.new(n_17.outputs[0], n_18.inputs[2])
    # Link 45: Switch.002[Image] -> Mix.011[Image]
    ng.links.new(n_30.outputs[0], n_31.inputs[2])
    # Link 46: Mix.007[Image] -> Mix.003[Image]
    ng.links.new(n_24.outputs[0], n_15.inputs[1])
    # Link 47: Switch.004[Image] -> Mix.007[Image]
    ng.links.new(n_23.outputs[0], n_24.inputs[2])
    # Link 48: Reroute.001[Output] -> Reroute.007[Input]
    ng.links.new(n_41.outputs[0], n_5.inputs[0])
    # Link 49: Mix.012[Image] -> Filter.004[Image]
    ng.links.new(n_9.outputs[0], n_10.inputs[1])
    # Link 50: Filter.004[Image] -> ColorRamp.006[Fac]  (color->float: RGB average)
    link_avg(n_10.outputs[0], n_33.inputs[0])
    # Link 51: ColorRamp.006[Image] -> Switch.006[On]
    ng.links.new(n_33.outputs[0], n_34.inputs[sw_idx_on()])
    # Link 52: Switch.006[Image] -> Mix.013[Image]
    ng.links.new(n_34.outputs[0], n_32.inputs[2])
    # Link 53: Mix.014[Image] -> Mix.005[Image]
    ng.links.new(n_49.outputs[0], n_48.inputs[2])
    # Link 54: Mix.011[Image] -> Mix.014[Image]
    ng.links.new(n_31.outputs[0], n_49.inputs[1])
    # Link 55: Mix.013[Image] -> Mix.014[Image]
    ng.links.new(n_32.outputs[0], n_49.inputs[2])
    # Link 56: Group Input[mat_color] -> Mix.012[Image]
    ng.links.new(n_13.outputs[8], n_9.inputs[2])
    # Link 57: Group Input[Alpha] -> Mix.012[Fac]
    ng.links.new(n_13.outputs[1], n_9.inputs[0])
    # Link 58: Group Input[Alpha] -> Alpha Over.001[Fac]
    ng.links.new(n_13.outputs[1], n_53.inputs[0])
    # Link 59: Alpha Over.002[Image] -> Anti-Aliasing.001[Image]
    ng.links.new(n_51.outputs[0], n_56.inputs[0])
    # Link 60: Anti-Aliasing.001[Image] -> Switch.005[On]
    ng.links.new(n_56.outputs[0], n_54.inputs[sw_idx_on()])
    # Link 61: Alpha Over.003[Image] -> Invert.001[Color]
    ng.links.new(n_47.outputs[0], n_36.inputs[1])
    # Link 62: Inpaint.001[Image] -> Alpha Over.003[Image]
    ng.links.new(n_35.outputs[0], n_47.inputs[2])
    # Link 63: Invert.001[Color] -> Mix.008[Fac]  (color->float: RGB average)
    link_avg(n_36.outputs[0], n_42.inputs[0])
    # Link 64: Invert.002[Color] -> Set Alpha.001[Alpha]  (color->float: RGB average)
    link_avg(n_43.outputs[0], n_55.inputs[1])
    # Link 65: Alpha Over.004[Image] -> Invert.002[Color]
    ng.links.new(n_37.outputs[0], n_43.inputs[1])
    # Link 66: ColorRamp.004[Image] -> Alpha Over.004[Image]
    ng.links.new(n_39.outputs[0], n_37.inputs[2])
    # Link 67: Alpha Over.001[Image] -> Alpha Over.002[Image]
    ng.links.new(n_53.outputs[0], n_51.inputs[1])
    # Link 68: Set Alpha.001[Image] -> Alpha Over.002[Image]
    ng.links.new(n_55.outputs[0], n_51.inputs[2])
    # Link 69: Reroute.001[Output] -> Alpha Over.001[Image]
    ng.links.new(n_41.outputs[0], n_53.inputs[2])
    # Link 70: Reroute.005[Output] -> Set Alpha.001[Image]
    ng.links.new(n_52.outputs[0], n_55.inputs[0])
    # Link 71: Set Alpha.001[Image] -> Group Output[line]
    ng.links.new(n_55.outputs[0], n_44.inputs[2])
    # Link 72: Switch.005[Image] -> Group Output[sample]
    ng.links.new(n_54.outputs[0], n_44.inputs[0])
    # Debug: ノード一覧
    # Reroute (NodeReroute) -> n_0
    # Mix.001 (CompositorNodeMixRGB) -> n_1
    # Filter.002 (CompositorNodeFilter) -> n_2
    # Normalize (CompositorNodeNormalize) -> n_3
    # Filter.001 (CompositorNodeFilter) -> n_4
    # Reroute.007 (NodeReroute) -> n_5
    # Reroute.004 (NodeReroute) -> n_6
    # Mix.002 (CompositorNodeMixRGB) -> n_7
    # Filter.003 (CompositorNodeFilter) -> n_8
    # Mix.012 (CompositorNodeMixRGB) -> n_9
    # Filter.004 (CompositorNodeFilter) -> n_10
    # Reroute.003 (NodeReroute) -> n_11
    # Reroute.002 (NodeReroute) -> n_12
    # Group Input (NodeGroupInput) -> n_13
    # ColorRamp.002 (CompositorNodeValToRGB) -> n_14
    # Mix.003 (CompositorNodeMixRGB) -> n_15
    # Mix.004 (CompositorNodeMixRGB) -> n_16
    # Switch.001 (CompositorNodeSwitch) -> n_17
    # Mix.010 (CompositorNodeMixRGB) -> n_18
    # ColorRamp.005 (CompositorNodeValToRGB) -> n_19
    # Color Key.001 (CompositorNodeColorMatte) -> n_20
    # Filter (CompositorNodeFilter) -> n_21
    # Mix (CompositorNodeMixRGB) -> n_22
    # Switch.004 (CompositorNodeSwitch) -> n_23
    # Mix.007 (CompositorNodeMixRGB) -> n_24
    # ColorRamp (CompositorNodeValToRGB) -> n_25
    # ColorRamp.001 (CompositorNodeValToRGB) -> n_26
    # Mix.009 (CompositorNodeMixRGB) -> n_27
    # Switch.003 (CompositorNodeSwitch) -> n_28
    # ColorRamp.003 (CompositorNodeValToRGB) -> n_29
    # Switch.002 (CompositorNodeSwitch) -> n_30
    # Mix.011 (CompositorNodeMixRGB) -> n_31
    # Mix.013 (CompositorNodeMixRGB) -> n_32
    # ColorRamp.006 (CompositorNodeValToRGB) -> n_33
    # Switch.006 (CompositorNodeSwitch) -> n_34
    # Inpaint.001 (CompositorNodeInpaint) -> n_35
    # Invert.001 (CompositorNodeInvert) -> n_36
    # Alpha Over.004 (CompositorNodeAlphaOver) -> n_37
    # Invert (CompositorNodeInvert) -> n_38
    # ColorRamp.004 (CompositorNodeValToRGB) -> n_39
    # Dilate/Erode (CompositorNodeDilateErode) -> n_40
    # Reroute.001 (NodeReroute) -> n_41
    # Mix.008 (CompositorNodeMixRGB) -> n_42
    # Invert.002 (CompositorNodeInvert) -> n_43
    # Group Output (NodeGroupOutput) -> n_44
    # Set Alpha (CompositorNodeSetAlpha) -> n_45
    # Alpha Over (CompositorNodeAlphaOver) -> n_46
    # Alpha Over.003 (CompositorNodeAlphaOver) -> n_47
    # Mix.005 (CompositorNodeMixRGB) -> n_48
    # Mix.014 (CompositorNodeMixRGB) -> n_49
    # Color Key (CompositorNodeColorMatte) -> n_50
    # Alpha Over.002 (CompositorNodeAlphaOver) -> n_51
    # Reroute.005 (NodeReroute) -> n_52
    # Alpha Over.001 (CompositorNodeAlphaOver) -> n_53
    # Switch.005 (CompositorNodeSwitch) -> n_54
    # Set Alpha.001 (CompositorNodeSetAlpha) -> n_55
    # Anti-Aliasing.001 (CompositorNodeAntiAliasing) -> n_56
    return ng

# usage: ng = create_node_tree_freepencil_v1_1_0_pro()

create_node_tree = create_node_tree_freepencil_v1_1_0_pro  # backward‑compat alias
