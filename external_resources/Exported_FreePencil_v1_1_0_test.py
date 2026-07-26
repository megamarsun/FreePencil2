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


def create_node_tree_freepencil_v1_1_0_test():
    ng = bpy.data.node_groups.new('FreePencil_v1_1_0_test', 'CompositorNodeTree')
    ng.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    s = ng.interface.new_socket(name='alpha', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0
    s = ng.interface.new_socket(name='mecha_color', in_out='INPUT', socket_type='NodeSocketColor')
    s.default_value = (0.0, 0.0, 0.0, 1.0)
    n_0 = ng.nodes.new(_nt('CompositorNodeMixRGB'))
    n_0.name = 'Mix'
    n_0.label = 'freepencil'
    n_0.location = (-161.46719360351562, -3.7871856689453125)
    n_0.hide = False
    n_0.width = 137.07122802734375
    n_0.blend_type = 'MIX'
    n_0.use_alpha = False
    n_0.use_clamp = False
    n_0.inputs[1].default_value = (1.0, 1.0, 1.0, 1.0)

    n_1 = ng.nodes.new('CompositorNodeFilter')
    n_1.name = 'Filter'
    n_1.label = 'freepencil'
    n_1.location = (19.167556762695312, -0.9434661865234375)
    n_1.hide = False
    n_1.width = 100.0
    _set_filter(n_1, 'SOBEL')
    n_1.inputs[0].default_value = 1.0

    n_2 = ng.nodes.new('NodeGroupOutput')
    n_2.name = 'Group Output'
    n_2.label = ''
    n_2.location = (451.4671630859375, -0.0)
    n_2.hide = False

    n_3 = ng.nodes.new('NodeGroupInput')
    n_3.name = 'Group Input'
    n_3.label = ''
    n_3.location = (-361.4671936035156, -0.0)
    n_3.hide = False

    n_4 = ng.nodes.new(_nt('CompositorNodeValToRGB'))
    n_4.name = 'ColorRamp'
    n_4.label = 'freepencil'
    n_4.location = (173.86622619628906, 12.110574722290039)
    n_4.hide = False
    # ===== Compositor ColorRamp for n_4 =====
    # Original: 2 elements
    ramp = n_4.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2要素の場合: デフォルト要素を直接上書き
    # 要素0: pos=0.000000, color=(1.0, 1.0, 1.0, 1.0)
    # 要素1: pos=0.100000, color=(0.0, 0.0, 0.0, 1.0)
    
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    ramp.elements[1].position = 0.1000000015
    ramp.elements[1].color = (0.000000, 0.000000, 0.000000, 1.000000)
    # ColorRamp設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    
    # 検証
    

    # --- legacy implicit color->float conversion (RGB average) ---
    # Blender 4.5+ の新コンポジターは色→float の暗黙変換が輝度ベースのため、
    # 旧ファイル読込時に Blender が挿入するのと同じ Normal + Math を挟む。
    def link_avg(from_sock, to_sock):
        if bpy.app.version < (4, 5, 0):
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
    # Link 0: Group Input[alpha] -> Mix[Fac]
    ng.links.new(n_3.outputs[0], n_0.inputs[0])
    # Link 1: ColorRamp[Image] -> Group Output[Image]
    ng.links.new(n_4.outputs[0], n_2.inputs[0])
    # Link 2: Group Input[mecha_color] -> Mix[Image]
    ng.links.new(n_3.outputs[1], n_0.inputs[2])
    # Link 3: Mix[Image] -> Filter[Image]
    ng.links.new(n_0.outputs[0], n_1.inputs[1])
    # Link 4: Filter[Image] -> ColorRamp[Fac]  (color->float: RGB average)
    link_avg(n_1.outputs[0], n_4.inputs[0])
    # Debug: ノード一覧
    # Mix (CompositorNodeMixRGB) -> n_0
    # Filter (CompositorNodeFilter) -> n_1
    # Group Output (NodeGroupOutput) -> n_2
    # Group Input (NodeGroupInput) -> n_3
    # ColorRamp (CompositorNodeValToRGB) -> n_4

    return ng

# usage: ng = create_node_tree_freepencil_v1_1_0_test()

create_node_tree = create_node_tree_freepencil_v1_1_0_test  # backward‑compat alias