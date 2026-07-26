import bpy


def _sock(coll, idx, name):
    if 0 <= idx < len(coll) and coll[idx].name == name:
        return coll[idx]
    for s in coll:
        if s.name == name:
            return s
    return None


def _in(node, idx, name):
    return _sock(node.inputs, idx, name)


def create_node_tree_freepencil_v1_1_0_pro():
    ng = bpy.data.node_groups.new('FreePencil_v1_1_0_pro', 'CompositorNodeTree')
    ng.interface.new_socket(name='sample', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='color', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='line', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='Image', in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='Alpha', in_out='INPUT', socket_type='NodeSocketFloat')
    ng.interface.new_socket(name='Depth', in_out='INPUT', socket_type='NodeSocketFloat')
    ng.interface.new_socket(name='mecha_color', in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='bone_color', in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='gen_color', in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='mask_color', in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='line_color', in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='mat_color', in_out='INPUT', socket_type='NodeSocketColor')
    n_0 = ng.nodes.new('NodeReroute')
    n_0.name = 'Reroute'
    n_0.label = ''
    n_0.location = (-1460.3646240234375, 516.5006103515625)
    n_0.hide = False
    n_0.width = 100.0

    n_1 = ng.nodes.new('ShaderNodeMix')
    n_1.data_type = 'RGBA'
    n_1.clamp_factor = False
    n_1.factor_mode = 'UNIFORM'
    n_1.name = 'Mix.001'
    n_1.label = 'freepencil'
    n_1.location = (-1382.829345703125, -104.58700561523438)
    n_1.hide = True
    n_1.width = 100.0
    n_1.blend_type = 'MIX'
    n_1.data_type = 'RGBA'
    _s = _in(n_1, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_1, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_1, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_1, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_1, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_1, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_1, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_1, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_2 = ng.nodes.new('CompositorNodeFilter')
    n_2.name = 'Filter.002'
    n_2.label = 'freepencil'
    n_2.location = (-1385.846923828125, -152.4720458984375)
    n_2.hide = True
    n_2.width = 100.0
    _s = _in(n_2, 1, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_2, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Sobel'

    n_3 = ng.nodes.new('ShaderNodeMath')
    n_3.name = 'Normalize'
    n_3.label = 'freepencil'
    n_3.location = (-1373.765380859375, 178.70384216308594)
    n_3.hide = True
    n_3.width = 100.0
    n_3.operation = 'DIVIDE'
    _s = _in(n_3, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_4 = ng.nodes.new('ShaderNodeMath')
    n_4.name = 'DepthDenom'
    n_4.label = 'freepencil'
    n_4.location = (-1373.765380859375, 210.0)
    n_4.hide = True
    n_4.width = 100.0
    n_4.operation = 'ADD'
    _s = _in(n_4, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5
    _s = _in(n_4, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_5 = ng.nodes.new('CompositorNodeFilter')
    n_5.name = 'Filter.001'
    n_5.label = 'freepencil'
    n_5.location = (-1370.630859375, 136.13937377929688)
    n_5.hide = True
    n_5.width = 100.0
    _s = _in(n_5, 1, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_5, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Sobel'

    n_6 = ng.nodes.new('NodeReroute')
    n_6.name = 'Reroute.007'
    n_6.label = ''
    n_6.location = (388.550537109375, 505.73492431640625)
    n_6.hide = False
    n_6.width = 100.0

    n_7 = ng.nodes.new('NodeReroute')
    n_7.name = 'Reroute.004'
    n_7.label = ''
    n_7.location = (-1428.674072265625, -1101.8173828125)
    n_7.hide = False
    n_7.width = 100.0

    n_8 = ng.nodes.new('ShaderNodeMix')
    n_8.data_type = 'RGBA'
    n_8.clamp_factor = False
    n_8.factor_mode = 'UNIFORM'
    n_8.name = 'Mix.002'
    n_8.label = 'freepencil'
    n_8.location = (-1387.655029296875, -412.3651123046875)
    n_8.hide = True
    n_8.width = 100.0
    n_8.blend_type = 'MIX'
    n_8.data_type = 'RGBA'
    _s = _in(n_8, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_8, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_8, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_8, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_8, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_8, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_8, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_8, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_9 = ng.nodes.new('CompositorNodeFilter')
    n_9.name = 'Filter.003'
    n_9.label = 'freepencil'
    n_9.location = (-1390.4134521484375, -458.7274169921875)
    n_9.hide = True
    n_9.width = 100.0
    _s = _in(n_9, 1, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_9, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Sobel'

    n_10 = ng.nodes.new('ShaderNodeMix')
    n_10.data_type = 'RGBA'
    n_10.clamp_factor = False
    n_10.factor_mode = 'UNIFORM'
    n_10.name = 'Mix.012'
    n_10.label = 'freepencil'
    n_10.location = (-1387.655029296875, -709.3576049804688)
    n_10.hide = True
    n_10.width = 100.0
    n_10.blend_type = 'MIX'
    n_10.data_type = 'RGBA'
    _s = _in(n_10, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_10, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_10, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_10, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_10, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_10, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_10, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_10, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_11 = ng.nodes.new('CompositorNodeFilter')
    n_11.name = 'Filter.004'
    n_11.label = 'freepencil'
    n_11.location = (-1390.4134521484375, -755.7199096679688)
    n_11.hide = True
    n_11.width = 100.0
    _s = _in(n_11, 1, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_11, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Sobel'

    n_12 = ng.nodes.new('NodeReroute')
    n_12.name = 'Reroute.003'
    n_12.label = ''
    n_12.location = (-638.4863891601562, -1075.5462646484375)
    n_12.hide = False
    n_12.width = 100.0

    n_13 = ng.nodes.new('NodeReroute')
    n_13.name = 'Reroute.002'
    n_13.label = ''
    n_13.location = (-1390.1163330078125, -1068.9576416015625)
    n_13.hide = False
    n_13.width = 100.0

    n_14 = ng.nodes.new('NodeGroupInput')
    n_14.name = 'Group Input'
    n_14.label = ''
    n_14.location = (-1961.415771484375, 66.10179138183594)
    n_14.hide = False

    n_15 = ng.nodes.new('ShaderNodeValToRGB')
    n_15.name = 'ColorRamp.002'
    n_15.label = 'freepencil'
    n_15.location = (-1231.8099365234375, -155.42649841308594)
    n_15.hide = False
    # ===== Shader ColorRamp for n_15 =====
    # Original: 2 elements
    ramp = n_15.color_ramp
    
    # Blender の仕様: ColorRamp は最低 2 要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2 要素の場合: デフォルト要素を直接上書き
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    ramp.elements[1].position = 0.1400000006
    ramp.elements[1].color = (0.300000, 0.000000, 0.000000, 1.000000)
    # ColorRamp 設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    

    n_16 = ng.nodes.new('ShaderNodeMix')
    n_16.data_type = 'RGBA'
    n_16.clamp_factor = False
    n_16.factor_mode = 'UNIFORM'
    n_16.name = 'Mix.003'
    n_16.label = 'freepencil'
    n_16.location = (-445.372314453125, 107.95846557617188)
    n_16.hide = True
    n_16.width = 100.0
    n_16.blend_type = 'MULTIPLY'
    n_16.data_type = 'RGBA'
    _s = _in(n_16, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_16, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_16, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_16, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_16, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_16, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_16, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_16, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_17 = ng.nodes.new('ShaderNodeMix')
    n_17.data_type = 'RGBA'
    n_17.clamp_factor = False
    n_17.factor_mode = 'UNIFORM'
    n_17.name = 'Mix.004'
    n_17.label = 'freepencil'
    n_17.location = (-444.92645263671875, 61.34123992919922)
    n_17.hide = True
    n_17.width = 100.0
    n_17.blend_type = 'MULTIPLY'
    n_17.data_type = 'RGBA'
    _s = _in(n_17, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_17, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_17, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_17, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_17, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_17, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_17, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_17, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_18 = ng.nodes.new('GeometryNodeSwitch')
    n_18.input_type = 'RGBA'
    n_18.name = 'Switch.001'
    n_18.label = 'freepencil'
    n_18.location = (-939.1372680664062, -155.12098693847656)
    n_18.hide = False
    n_18.width = 100.0
    _s = _in(n_18, 0, 'Switch')
    if _s is not None:
        _s.default_value = True
    _s = _in(n_18, 1, 'False')
    if _s is not None:
        _s.default_value = (0.800000011920929, 0.800000011920929, 0.800000011920929, 1.0)

    n_19 = ng.nodes.new('ShaderNodeMix')
    n_19.data_type = 'RGBA'
    n_19.clamp_factor = False
    n_19.factor_mode = 'UNIFORM'
    n_19.name = 'Mix.010'
    n_19.label = 'freepencil'
    n_19.location = (-781.5869750976562, -135.650146484375)
    n_19.hide = False
    n_19.blend_type = 'MIX'
    n_19.data_type = 'RGBA'
    _s = _in(n_19, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_19, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_19, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_19, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_19, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_19, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_19, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_19, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_19, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_20 = ng.nodes.new('ShaderNodeValToRGB')
    n_20.name = 'ColorRamp.005'
    n_20.label = 'freepencil'
    n_20.location = (-383.46453857421875, -283.0209655761719)
    n_20.hide = True
    n_20.width = 200.0
    # ===== Shader ColorRamp for n_20 =====
    # Original: 2 elements
    ramp = n_20.color_ramp
    
    # Blender の仕様: ColorRamp は最低 2 要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2 要素の場合: デフォルト要素を直接上書き
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (0.000000, 0.000000, 0.000000, 1.000000)
    
    ramp.elements[1].position = 0.3777775168
    ramp.elements[1].color = (1.000000, 1.000000, 1.000000, 1.000000)
    # ColorRamp 設定
    ramp.interpolation = 'CARDINAL'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    

    n_21 = ng.nodes.new('CompositorNodeColorMatte')
    # skipped node properties ('CompositorNodeColorMatte' object has no attribute 'color_hue')

    n_22 = ng.nodes.new('CompositorNodeFilter')
    n_22.name = 'Filter'
    n_22.label = 'freepencil'
    n_22.location = (-1375.7027587890625, 436.0093688964844)
    n_22.hide = True
    n_22.width = 100.0
    _s = _in(n_22, 1, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_22, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Sobel'

    n_23 = ng.nodes.new('ShaderNodeMix')
    n_23.data_type = 'RGBA'
    n_23.clamp_factor = False
    n_23.factor_mode = 'UNIFORM'
    n_23.name = 'Mix'
    n_23.label = 'freepencil'
    n_23.location = (-1378.0037841796875, 480.1326599121094)
    n_23.hide = True
    n_23.width = 100.0
    n_23.blend_type = 'MIX'
    n_23.data_type = 'RGBA'
    _s = _in(n_23, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_23, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_23, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_23, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_23, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_23, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_23, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_23, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_24 = ng.nodes.new('GeometryNodeSwitch')
    n_24.input_type = 'RGBA'
    n_24.name = 'Switch.004'
    n_24.label = 'freepencil'
    n_24.location = (-943.3009033203125, 443.8624572753906)
    n_24.hide = False
    n_24.width = 100.0
    _s = _in(n_24, 0, 'Switch')
    if _s is not None:
        _s.default_value = True
    _s = _in(n_24, 1, 'False')
    if _s is not None:
        _s.default_value = (0.800000011920929, 0.800000011920929, 0.800000011920929, 1.0)

    n_25 = ng.nodes.new('ShaderNodeMix')
    n_25.data_type = 'RGBA'
    n_25.clamp_factor = False
    n_25.factor_mode = 'UNIFORM'
    n_25.name = 'Mix.007'
    n_25.label = 'freepencil'
    n_25.location = (-780.9413452148438, 456.88909912109375)
    n_25.hide = False
    n_25.blend_type = 'MIX'
    n_25.data_type = 'RGBA'
    _s = _in(n_25, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_25, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_25, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_25, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_25, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_25, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_25, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_25, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_25, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_26 = ng.nodes.new('ShaderNodeValToRGB')
    n_26.name = 'ColorRamp'
    n_26.label = 'freepencil'
    n_26.location = (-1230.60107421875, 447.91632080078125)
    n_26.hide = False
    # ===== Shader ColorRamp for n_26 =====
    # Original: 2 elements
    ramp = n_26.color_ramp
    
    # Blender の仕様: ColorRamp は最低 2 要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2 要素の場合: デフォルト要素を直接上書き
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    ramp.elements[1].position = 0.1400000006
    ramp.elements[1].color = (0.000000, 0.000000, 0.000000, 1.000000)
    # ColorRamp 設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    

    n_27 = ng.nodes.new('ShaderNodeValToRGB')
    n_27.name = 'ColorRamp.001'
    n_27.label = 'freepencil'
    n_27.location = (-1224.64306640625, 149.02577209472656)
    n_27.hide = False
    # ===== Shader ColorRamp for n_27 =====
    # Original: 2 elements
    ramp = n_27.color_ramp
    
    # Blender の仕様: ColorRamp は最低 2 要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2 要素の場合: デフォルト要素を直接上書き
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    ramp.elements[1].position = 0.1500000060
    ramp.elements[1].color = (0.000000, 0.120000, 0.000000, 1.000000)
    # ColorRamp 設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    

    n_28 = ng.nodes.new('ShaderNodeMix')
    n_28.data_type = 'RGBA'
    n_28.clamp_factor = False
    n_28.factor_mode = 'UNIFORM'
    n_28.name = 'Mix.009'
    n_28.label = 'freepencil'
    n_28.location = (-781.8668212890625, 163.2741241455078)
    n_28.hide = False
    n_28.blend_type = 'MIX'
    n_28.data_type = 'RGBA'
    _s = _in(n_28, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_28, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_28, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_28, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_28, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_28, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_28, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_28, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_28, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_29 = ng.nodes.new('GeometryNodeSwitch')
    n_29.input_type = 'RGBA'
    n_29.name = 'Switch.003'
    n_29.label = 'freepencil'
    n_29.location = (-937.5640869140625, 144.00184631347656)
    n_29.hide = False
    n_29.width = 100.0
    _s = _in(n_29, 0, 'Switch')
    if _s is not None:
        _s.default_value = True
    _s = _in(n_29, 1, 'False')
    if _s is not None:
        _s.default_value = (0.800000011920929, 0.800000011920929, 0.800000011920929, 1.0)

    n_30 = ng.nodes.new('ShaderNodeValToRGB')
    n_30.name = 'ColorRamp.003'
    n_30.label = 'freepencil'
    n_30.location = (-1229.496826171875, -439.9772033691406)
    n_30.hide = False
    # ===== Shader ColorRamp for n_30 =====
    # Original: 2 elements
    ramp = n_30.color_ramp
    
    # Blender の仕様: ColorRamp は最低 2 要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2 要素の場合: デフォルト要素を直接上書き
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    ramp.elements[1].position = 0.3499999940
    ramp.elements[1].color = (0.000000, 0.003000, 0.300000, 1.000000)
    # ColorRamp 設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    

    n_31 = ng.nodes.new('GeometryNodeSwitch')
    n_31.input_type = 'RGBA'
    n_31.name = 'Switch.002'
    n_31.label = 'freepencil'
    n_31.location = (-946.0177001953125, -452.8358459472656)
    n_31.hide = False
    n_31.width = 100.0
    _s = _in(n_31, 0, 'Switch')
    if _s is not None:
        _s.default_value = True
    _s = _in(n_31, 1, 'False')
    if _s is not None:
        _s.default_value = (0.800000011920929, 0.800000011920929, 0.800000011920929, 1.0)

    n_32 = ng.nodes.new('ShaderNodeMix')
    n_32.data_type = 'RGBA'
    n_32.clamp_factor = False
    n_32.factor_mode = 'UNIFORM'
    n_32.name = 'Mix.011'
    n_32.label = 'freepencil'
    n_32.location = (-782.275390625, -456.4102783203125)
    n_32.hide = False
    n_32.blend_type = 'MIX'
    n_32.data_type = 'RGBA'
    _s = _in(n_32, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_32, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_32, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_32, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_32, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_32, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_32, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_32, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_32, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_33 = ng.nodes.new('ShaderNodeMix')
    n_33.data_type = 'RGBA'
    n_33.clamp_factor = False
    n_33.factor_mode = 'UNIFORM'
    n_33.name = 'Mix.013'
    n_33.label = 'freepencil'
    n_33.location = (-782.275390625, -753.4027099609375)
    n_33.hide = False
    n_33.blend_type = 'MIX'
    n_33.data_type = 'RGBA'
    _s = _in(n_33, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_33, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_33, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_33, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_33, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_33, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_33, 6, 'A')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_33, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_33, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_34 = ng.nodes.new('ShaderNodeValToRGB')
    n_34.name = 'ColorRamp.006'
    n_34.label = 'freepencil'
    n_34.location = (-1229.496826171875, -736.9696655273438)
    n_34.hide = False
    # ===== Shader ColorRamp for n_34 =====
    # Original: 2 elements
    ramp = n_34.color_ramp
    
    # Blender の仕様: ColorRamp は最低 2 要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2 要素の場合: デフォルト要素を直接上書き
    ramp.elements[0].position = 0.0000000000
    ramp.elements[0].color = (1.000000, 1.000000, 1.000000, 1.000000)
    
    ramp.elements[1].position = 0.3499999940
    ramp.elements[1].color = (0.150000, 0.003000, 0.150000, 1.000000)
    # ColorRamp 設定
    ramp.interpolation = 'CONSTANT'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    

    n_35 = ng.nodes.new('GeometryNodeSwitch')
    n_35.input_type = 'RGBA'
    n_35.name = 'Switch.006'
    n_35.label = '丸みの線'
    n_35.location = (-946.0177001953125, -749.8283081054688)
    n_35.hide = False
    n_35.width = 100.0
    _s = _in(n_35, 0, 'Switch')
    if _s is not None:
        _s.default_value = True
    _s = _in(n_35, 1, 'False')
    if _s is not None:
        _s.default_value = (0.800000011920929, 0.800000011920929, 0.800000011920929, 1.0)

    n_36 = ng.nodes.new('CompositorNodeInpaint')
    # skipped node properties ('CompositorNodeInpaint' object has no attribute 'distance')

    n_37 = ng.nodes.new('CompositorNodeInvert')
    n_37.name = 'Invert.001'
    n_37.label = 'freepencil'
    n_37.location = (68.92464447021484, 111.568115234375)
    n_37.hide = True
    _s = _in(n_37, 1, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_37, 2, 'Invert Color')
    if _s is not None:
        _s.default_value = True
    _s = _in(n_37, 3, 'Invert Alpha')
    if _s is not None:
        _s.default_value = False

    n_38 = ng.nodes.new('CompositorNodeAlphaOver')
    n_38.name = 'Alpha Over.004'
    n_38.label = 'freepencil'
    n_38.location = (325.4501037597656, -364.7349548339844)
    n_38.hide = True
    _s = _in(n_38, 0, 'Background')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_38, 2, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_38, 3, 'Type')
    if _s is not None:
        _s.default_value = 'Over'
    _s = _in(n_38, 4, 'Straight Alpha')
    if _s is not None:
        _s.default_value = False

    n_39 = ng.nodes.new('CompositorNodeInvert')
    n_39.name = 'Invert'
    n_39.label = 'freepencil'
    n_39.location = (-279.2994689941406, -468.7112731933594)
    n_39.hide = False
    n_39.width = 100.0
    _s = _in(n_39, 1, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_39, 2, 'Invert Color')
    if _s is not None:
        _s.default_value = True
    _s = _in(n_39, 3, 'Invert Alpha')
    if _s is not None:
        _s.default_value = False

    n_40 = ng.nodes.new('ShaderNodeValToRGB')
    n_40.name = 'ColorRamp.004'
    n_40.label = 'freepencil'
    n_40.location = (31.499370574951172, -437.53955078125)
    n_40.hide = False
    n_40.width = 200.0
    # ===== Shader ColorRamp for n_40 =====
    # Original: 2 elements
    ramp = n_40.color_ramp
    
    # Blender の仕様: ColorRamp は最低 2 要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 2 要素の場合: デフォルト要素を直接上書き
    ramp.elements[0].position = 0.0000005020
    ramp.elements[0].color = (0.000000, 0.000000, 0.000000, 1.000000)
    
    ramp.elements[1].position = 0.8277776241
    ramp.elements[1].color = (1.000000, 1.000000, 1.000000, 1.000000)
    # ColorRamp 設定
    ramp.interpolation = 'EASE'
    ramp.color_mode = 'RGB'
    ramp.hue_interpolation = 'NEAR'
    

    n_41 = ng.nodes.new('CompositorNodeDilateErode')
    # skipped node properties ('CompositorNodeDilateErode' object has no attribute 'mode')

    n_42 = ng.nodes.new('NodeReroute')
    n_42.name = 'Reroute.001'
    n_42.label = ''
    n_42.location = (-443.4715881347656, 511.1692810058594)
    n_42.hide = False
    n_42.width = 100.0

    n_43 = ng.nodes.new('ShaderNodeMix')
    n_43.data_type = 'RGBA'
    n_43.clamp_factor = False
    n_43.factor_mode = 'UNIFORM'
    n_43.name = 'Mix.008'
    n_43.label = 'freepencil'
    n_43.location = (68.11617279052734, -91.61726379394531)
    n_43.hide = True
    n_43.width = 100.0
    n_43.blend_type = 'MIX'
    n_43.data_type = 'RGBA'
    _s = _in(n_43, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_43, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_43, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_43, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_43, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_43, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_43, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_44 = ng.nodes.new('CompositorNodeInvert')
    n_44.name = 'Invert.002'
    n_44.label = 'freepencil'
    n_44.location = (321.9562072753906, -320.15362548828125)
    n_44.hide = True
    _s = _in(n_44, 1, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_44, 2, 'Invert Color')
    if _s is not None:
        _s.default_value = True
    _s = _in(n_44, 3, 'Invert Alpha')
    if _s is not None:
        _s.default_value = False

    n_45 = ng.nodes.new('NodeGroupOutput')
    n_45.name = 'Group Output'
    n_45.label = ''
    n_45.location = (962.3602294921875, 187.07183837890625)
    n_45.hide = False

    n_46 = ng.nodes.new('CompositorNodeSetAlpha')
    n_46.name = 'Set Alpha'
    n_46.label = 'freepencil'
    n_46.location = (-72.31686401367188, -118.15411376953125)
    n_46.hide = True
    n_46.width = 100.0
    _s = _in(n_46, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Apply Mask'

    n_47 = ng.nodes.new('CompositorNodeAlphaOver')
    n_47.name = 'Alpha Over'
    n_47.label = 'freepencil'
    n_47.location = (74.92115783691406, -137.57373046875)
    n_47.hide = True
    n_47.width = 100.0
    _s = _in(n_47, 0, 'Background')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_47, 2, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_47, 3, 'Type')
    if _s is not None:
        _s.default_value = 'Over'
    _s = _in(n_47, 4, 'Straight Alpha')
    if _s is not None:
        _s.default_value = False

    n_48 = ng.nodes.new('CompositorNodeAlphaOver')
    n_48.name = 'Alpha Over.003'
    n_48.label = 'freepencil'
    n_48.location = (63.513275146484375, 161.19493103027344)
    n_48.hide = True
    _s = _in(n_48, 0, 'Background')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_48, 2, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_48, 3, 'Type')
    if _s is not None:
        _s.default_value = 'Over'
    _s = _in(n_48, 4, 'Straight Alpha')
    if _s is not None:
        _s.default_value = False

    n_49 = ng.nodes.new('ShaderNodeMix')
    n_49.data_type = 'RGBA'
    n_49.clamp_factor = False
    n_49.factor_mode = 'UNIFORM'
    n_49.name = 'Mix.005'
    n_49.label = 'freepencil'
    n_49.location = (-441.11676025390625, 11.718293190002441)
    n_49.hide = True
    n_49.width = 100.0
    n_49.blend_type = 'MULTIPLY'
    n_49.data_type = 'RGBA'
    _s = _in(n_49, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_49, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_49, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_49, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_49, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_49, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_49, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_49, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_50 = ng.nodes.new('ShaderNodeMix')
    n_50.data_type = 'RGBA'
    n_50.clamp_factor = False
    n_50.factor_mode = 'UNIFORM'
    n_50.name = 'Mix.014'
    n_50.label = 'freepencil'
    n_50.location = (-441.11676025390625, -43.85590362548828)
    n_50.hide = True
    n_50.width = 100.0
    n_50.blend_type = 'MULTIPLY'
    n_50.data_type = 'RGBA'
    _s = _in(n_50, 0, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_50, 1, 'Factor')
    if _s is not None:
        _s.default_value = (0.5, 0.5, 0.5)
    _s = _in(n_50, 2, 'A')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_50, 3, 'B')
    if _s is not None:
        _s.default_value = 0.0
    _s = _in(n_50, 4, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_50, 5, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_50, 8, 'A')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_50, 9, 'B')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)

    n_51 = ng.nodes.new('CompositorNodeColorMatte')
    # skipped node properties ('CompositorNodeColorMatte' object has no attribute 'color_hue')

    n_52 = ng.nodes.new('CompositorNodeAlphaOver')
    n_52.name = 'Alpha Over.002'
    n_52.label = 'freepencil'
    n_52.location = (347.9851989746094, 345.4447937011719)
    n_52.hide = True
    n_52.width = 171.73931884765625
    _s = _in(n_52, 2, 'Factor')
    if _s is not None:
        _s.default_value = 1.0
    _s = _in(n_52, 3, 'Type')
    if _s is not None:
        _s.default_value = 'Over'
    _s = _in(n_52, 4, 'Straight Alpha')
    if _s is not None:
        _s.default_value = False

    n_53 = ng.nodes.new('NodeReroute')
    n_53.name = 'Reroute.005'
    n_53.label = ''
    n_53.location = (-90.02175903320312, -1100.7286376953125)
    n_53.hide = False
    n_53.width = 100.0

    n_54 = ng.nodes.new('CompositorNodeAlphaOver')
    n_54.name = 'Alpha Over.001'
    n_54.label = 'freepencil'
    n_54.location = (359.64654541015625, 184.06251525878906)
    n_54.hide = False
    _s = _in(n_54, 0, 'Background')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)
    _s = _in(n_54, 3, 'Type')
    if _s is not None:
        _s.default_value = 'Over'
    _s = _in(n_54, 4, 'Straight Alpha')
    if _s is not None:
        _s.default_value = False

    n_55 = ng.nodes.new('GeometryNodeSwitch')
    n_55.input_type = 'RGBA'
    n_55.name = 'Switch.005'
    n_55.label = 'freepencil'
    n_55.location = (565.5455322265625, 206.56114196777344)
    n_55.hide = False
    n_55.width = 100.0
    _s = _in(n_55, 0, 'Switch')
    if _s is not None:
        _s.default_value = True

    n_56 = ng.nodes.new('CompositorNodeSetAlpha')
    n_56.name = 'Set Alpha.001'
    n_56.label = 'freepencil'
    n_56.location = (322.1084899902344, -270.73992919921875)
    n_56.hide = True
    _s = _in(n_56, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Apply Mask'

    try:
        n_57 = ng.nodes.new('CompositorNodeAntiAliasing')
        n_57.name = 'Anti-Aliasing.001'
        n_57.label = 'freepencil'
        n_57.location = (347.09661865234375, 306.0675354003906)
        n_57.hide = True
        n_57.width = 170.0
        _s = _in(n_57, 1, 'Threshold')
        if _s is not None:
            _s.default_value = 0.20000000298023224
        _s = _in(n_57, 2, 'Contrast Limit')
        if _s is not None:
            _s.default_value = 2.0
        _s = _in(n_57, 3, 'Corner Rounding')
        if _s is not None:
            _s.default_value = 0.25
    except Exception:
        n_57 = None  # Anti-Aliasing node not available; skipping

    n_58 = ng.nodes.new('ShaderNodeMath')
    n_58.name = 'Math'
    n_58.label = 'freepencil'
    n_58.location = (-1285.7027587890625, 406.0093688964844)
    n_58.hide = True
    n_58.operation = 'MULTIPLY'
    _s = _in(n_58, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_58, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_59 = ng.nodes.new('ShaderNodeMath')
    n_59.name = 'Math.001'
    n_59.label = 'freepencil'
    n_59.location = (-1280.630859375, 106.13937377929688)
    n_59.hide = True
    n_59.operation = 'MULTIPLY'
    _s = _in(n_59, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_59, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_60 = ng.nodes.new('ShaderNodeMath')
    n_60.name = 'Math.002'
    n_60.label = 'freepencil'
    n_60.location = (-1295.846923828125, -182.4720458984375)
    n_60.hide = True
    n_60.operation = 'MULTIPLY'
    _s = _in(n_60, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_60, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_61 = ng.nodes.new('ShaderNodeMath')
    n_61.name = 'Math.003'
    n_61.label = 'freepencil'
    n_61.location = (-1300.4134521484375, -488.7274169921875)
    n_61.hide = True
    n_61.operation = 'MULTIPLY'
    _s = _in(n_61, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_61, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_62 = ng.nodes.new('ShaderNodeMath')
    n_62.name = 'Math.004'
    n_62.label = 'freepencil'
    n_62.location = (-189.29946899414062, -498.7112731933594)
    n_62.hide = True
    n_62.operation = 'MULTIPLY'
    _s = _in(n_62, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_62, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_63 = ng.nodes.new('ShaderNodeMath')
    n_63.name = 'Math.005'
    n_63.label = 'freepencil'
    n_63.location = (164.92115783691406, -167.57373046875)
    n_63.hide = True
    n_63.operation = 'MULTIPLY'
    _s = _in(n_63, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_63, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_64 = ng.nodes.new('ShaderNodeMath')
    n_64.name = 'Math.006'
    n_64.label = 'freepencil'
    n_64.location = (-288.6430358886719, -358.555908203125)
    n_64.hide = True
    n_64.operation = 'MULTIPLY'
    _s = _in(n_64, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_64, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_65 = ng.nodes.new('ShaderNodeMath')
    n_65.name = 'Math.007'
    n_65.label = 'freepencil'
    n_65.location = (-548.4863891601562, -1105.5462646484375)
    n_65.hide = True
    n_65.operation = 'MULTIPLY'
    _s = _in(n_65, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_65, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_66 = ng.nodes.new('ShaderNodeMath')
    n_66.name = 'Math.008'
    n_66.label = 'freepencil'
    n_66.location = (-1300.4134521484375, -785.7199096679688)
    n_66.hide = True
    n_66.operation = 'MULTIPLY'
    _s = _in(n_66, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_66, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_67 = ng.nodes.new('ShaderNodeMath')
    n_67.name = 'Math.009'
    n_67.label = 'freepencil'
    n_67.location = (158.92465209960938, 81.568115234375)
    n_67.hide = True
    n_67.operation = 'MULTIPLY'
    _s = _in(n_67, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_67, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_68 = ng.nodes.new('ShaderNodeMath')
    n_68.name = 'Math.010'
    n_68.label = 'freepencil'
    n_68.location = (411.9562072753906, -350.15362548828125)
    n_68.hide = True
    n_68.operation = 'MULTIPLY'
    _s = _in(n_68, 1, 'Value')
    if _s is not None:
        _s.default_value = 0.5773502588272095
    _s = _in(n_68, 2, 'Value')
    if _s is not None:
        _s.default_value = 0.5

    n_69 = ng.nodes.new('ShaderNodeVectorMath')
    n_69.name = 'Vector Math'
    n_69.label = ''
    n_69.location = (-1335.7027587890625, 406.0093688964844)
    n_69.hide = True
    n_69.operation = 'DOT_PRODUCT'
    _s = _in(n_69, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_69, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_69, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_70 = ng.nodes.new('ShaderNodeVectorMath')
    n_70.name = 'Vector Math.001'
    n_70.label = ''
    n_70.location = (-1330.630859375, 106.13937377929688)
    n_70.hide = True
    n_70.operation = 'DOT_PRODUCT'
    _s = _in(n_70, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_70, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_70, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_71 = ng.nodes.new('ShaderNodeVectorMath')
    n_71.name = 'Vector Math.002'
    n_71.label = ''
    n_71.location = (-1345.846923828125, -182.4720458984375)
    n_71.hide = True
    n_71.operation = 'DOT_PRODUCT'
    _s = _in(n_71, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_71, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_71, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_72 = ng.nodes.new('ShaderNodeVectorMath')
    n_72.name = 'Vector Math.003'
    n_72.label = ''
    n_72.location = (-1350.4134521484375, -488.7274169921875)
    n_72.hide = True
    n_72.operation = 'DOT_PRODUCT'
    _s = _in(n_72, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_72, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_72, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_73 = ng.nodes.new('ShaderNodeVectorMath')
    n_73.name = 'Vector Math.004'
    n_73.label = ''
    n_73.location = (-239.29946899414062, -498.7112731933594)
    n_73.hide = True
    n_73.operation = 'DOT_PRODUCT'
    _s = _in(n_73, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_73, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_73, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_74 = ng.nodes.new('ShaderNodeVectorMath')
    n_74.name = 'Vector Math.005'
    n_74.label = ''
    n_74.location = (114.92115783691406, -167.57373046875)
    n_74.hide = True
    n_74.operation = 'DOT_PRODUCT'
    _s = _in(n_74, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_74, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_74, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_75 = ng.nodes.new('ShaderNodeVectorMath')
    n_75.name = 'Vector Math.006'
    n_75.label = ''
    n_75.location = (-338.6430358886719, -358.555908203125)
    n_75.hide = True
    n_75.operation = 'DOT_PRODUCT'
    _s = _in(n_75, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_75, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_75, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_76 = ng.nodes.new('ShaderNodeVectorMath')
    n_76.name = 'Vector Math.007'
    n_76.label = ''
    n_76.location = (-598.4863891601562, -1105.5462646484375)
    n_76.hide = True
    n_76.operation = 'DOT_PRODUCT'
    _s = _in(n_76, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_76, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_76, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_77 = ng.nodes.new('ShaderNodeVectorMath')
    n_77.name = 'Vector Math.008'
    n_77.label = ''
    n_77.location = (-1350.4134521484375, -785.7199096679688)
    n_77.hide = True
    n_77.operation = 'DOT_PRODUCT'
    _s = _in(n_77, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_77, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_77, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_78 = ng.nodes.new('ShaderNodeVectorMath')
    n_78.name = 'Vector Math.009'
    n_78.label = ''
    n_78.location = (108.92464447021484, 81.568115234375)
    n_78.hide = True
    n_78.operation = 'DOT_PRODUCT'
    _s = _in(n_78, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_78, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_78, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_79 = ng.nodes.new('ShaderNodeVectorMath')
    n_79.name = 'Vector Math.010'
    n_79.label = ''
    n_79.location = (361.9562072753906, -350.15362548828125)
    n_79.hide = True
    n_79.operation = 'DOT_PRODUCT'
    _s = _in(n_79, 1, 'Vector')
    if _s is not None:
        _s.default_value = (0.5773502588272095, 0.5773502588272095, 0.5773502588272095)
    _s = _in(n_79, 2, 'Vector')
    if _s is not None:
        _s.default_value = (0.0, 0.0, 0.0)
    _s = _in(n_79, 3, 'Scale')
    if _s is not None:
        _s.default_value = 1.0

    n_80 = ng.nodes.new('CompositorNodeSeparateColor')
    n_80.name = 'Separate Color'
    n_80.label = ''
    n_80.location = (-1392.829345703125, -104.58700561523438)
    n_80.hide = False
    _s = _in(n_80, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_81 = ng.nodes.new('CompositorNodeSetAlpha')
    n_81.name = 'Set Alpha.002'
    n_81.label = ''
    n_81.location = (-1392.829345703125, -104.58700561523438)
    n_81.hide = False
    _s = _in(n_81, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_82 = ng.nodes.new('CompositorNodeSeparateColor')
    n_82.name = 'Separate Color.001'
    n_82.label = ''
    n_82.location = (-1397.655029296875, -412.3651123046875)
    n_82.hide = False
    _s = _in(n_82, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_83 = ng.nodes.new('CompositorNodeSetAlpha')
    n_83.name = 'Set Alpha.003'
    n_83.label = ''
    n_83.location = (-1397.655029296875, -412.3651123046875)
    n_83.hide = False
    _s = _in(n_83, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_84 = ng.nodes.new('CompositorNodeSeparateColor')
    n_84.name = 'Separate Color.002'
    n_84.label = ''
    n_84.location = (-1397.655029296875, -709.3576049804688)
    n_84.hide = False
    _s = _in(n_84, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_85 = ng.nodes.new('CompositorNodeSetAlpha')
    n_85.name = 'Set Alpha.004'
    n_85.label = ''
    n_85.location = (-1397.655029296875, -709.3576049804688)
    n_85.hide = False
    _s = _in(n_85, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_86 = ng.nodes.new('CompositorNodeSeparateColor')
    n_86.name = 'Separate Color.003'
    n_86.label = ''
    n_86.location = (-791.5869750976562, -135.650146484375)
    n_86.hide = False
    _s = _in(n_86, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_87 = ng.nodes.new('CompositorNodeSetAlpha')
    n_87.name = 'Set Alpha.005'
    n_87.label = ''
    n_87.location = (-791.5869750976562, -135.650146484375)
    n_87.hide = False
    _s = _in(n_87, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_88 = ng.nodes.new('CompositorNodeSeparateColor')
    n_88.name = 'Separate Color.004'
    n_88.label = ''
    n_88.location = (-1388.0037841796875, 480.1326599121094)
    n_88.hide = False
    _s = _in(n_88, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_89 = ng.nodes.new('CompositorNodeSetAlpha')
    n_89.name = 'Set Alpha.006'
    n_89.label = ''
    n_89.location = (-1388.0037841796875, 480.1326599121094)
    n_89.hide = False
    _s = _in(n_89, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_90 = ng.nodes.new('CompositorNodeSeparateColor')
    n_90.name = 'Separate Color.005'
    n_90.label = ''
    n_90.location = (-790.9413452148438, 456.88909912109375)
    n_90.hide = False
    _s = _in(n_90, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_91 = ng.nodes.new('CompositorNodeSetAlpha')
    n_91.name = 'Set Alpha.007'
    n_91.label = ''
    n_91.location = (-790.9413452148438, 456.88909912109375)
    n_91.hide = False
    _s = _in(n_91, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_92 = ng.nodes.new('CompositorNodeSeparateColor')
    n_92.name = 'Separate Color.006'
    n_92.label = ''
    n_92.location = (-791.8668212890625, 163.2741241455078)
    n_92.hide = False
    _s = _in(n_92, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_93 = ng.nodes.new('CompositorNodeSetAlpha')
    n_93.name = 'Set Alpha.008'
    n_93.label = ''
    n_93.location = (-791.8668212890625, 163.2741241455078)
    n_93.hide = False
    _s = _in(n_93, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_94 = ng.nodes.new('CompositorNodeSeparateColor')
    n_94.name = 'Separate Color.007'
    n_94.label = ''
    n_94.location = (-792.275390625, -456.4102783203125)
    n_94.hide = False
    _s = _in(n_94, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_95 = ng.nodes.new('CompositorNodeSetAlpha')
    n_95.name = 'Set Alpha.009'
    n_95.label = ''
    n_95.location = (-792.275390625, -456.4102783203125)
    n_95.hide = False
    _s = _in(n_95, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_96 = ng.nodes.new('CompositorNodeSeparateColor')
    n_96.name = 'Separate Color.008'
    n_96.label = ''
    n_96.location = (-792.275390625, -753.4027099609375)
    n_96.hide = False
    _s = _in(n_96, 0, 'Image')
    if _s is not None:
        _s.default_value = (1.0, 1.0, 1.0, 1.0)

    n_97 = ng.nodes.new('CompositorNodeSetAlpha')
    n_97.name = 'Set Alpha.010'
    n_97.label = ''
    n_97.location = (-792.275390625, -753.4027099609375)
    n_97.hide = False
    _s = _in(n_97, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    n_98 = ng.nodes.new('CompositorNodeSeparateColor')
    n_98.name = 'Separate Color.009'
    n_98.label = ''
    n_98.location = (58.116172790527344, -91.61726379394531)
    n_98.hide = False

    n_99 = ng.nodes.new('CompositorNodeSetAlpha')
    n_99.name = 'Set Alpha.011'
    n_99.label = ''
    n_99.location = (58.116172790527344, -91.61726379394531)
    n_99.hide = False
    _s = _in(n_99, 2, 'Type')
    if _s is not None:
        _s.default_value = 'Replace Alpha'

    def _link(f, fi, fsock, t, ti, tsock):
        a = _sock(f.outputs, fi, fsock)
        b = _in(t, ti, tsock)
        if a is not None and b is not None:
            ng.links.new(a, b)

    # links:
    _link(n_14, 1, 'Alpha', n_23, 0, 'Factor')
    _link(n_14, 2, 'Depth', n_5, 0, 'Image')
    _link(n_14, 2, 'Depth', n_4, 0, 'Value')
    _link(n_14, 3, 'mecha_color', n_23, 7, 'B')
    _link(n_14, 4, 'bone_color', n_1, 7, 'B')
    _link(n_14, 5, 'gen_color', n_8, 7, 'B')
    _link(n_14, 0, 'Image', n_0, 0, 'Input')
    _link(n_14, 7, 'line_color', n_7, 0, 'Input')
    _link(n_14, 6, 'mask_color', n_13, 0, 'Input')
    _link(n_6, 0, 'Output', n_45, 1, 'color')
    _link(n_58, 0, 'Value', n_26, 0, 'Factor')
    _link(n_59, 0, 'Value', n_3, 0, 'Value')
    _link(n_4, 0, 'Value', n_3, 1, 'Value')
    _link(n_3, 0, 'Value', n_27, 0, 'Factor')
    _link(n_60, 0, 'Value', n_15, 0, 'Factor')
    _link(n_61, 0, 'Value', n_30, 0, 'Factor')
    _link(n_49, 2, 'Result', n_17, 7, 'B')
    _link(n_17, 2, 'Result', n_16, 7, 'B')
    _link(n_0, 0, 'Output', n_42, 0, 'Input')
    _link(n_13, 0, 'Output', n_12, 0, 'Input')
    _link(n_7, 0, 'Output', n_53, 0, 'Input')
    _link(n_30, 0, 'Color', n_31, 2, 'True')
    _link(n_15, 0, 'Color', n_18, 2, 'True')
    _link(n_27, 0, 'Color', n_29, 2, 'True')
    _link(n_14, 1, 'Alpha', n_1, 0, 'Factor')
    _link(n_14, 1, 'Alpha', n_8, 0, 'Factor')
    _link(n_53, 0, 'Output', n_43, 7, 'B')
    _link(n_21, 0, 'Image', n_36, 0, 'Image')
    _link(n_16, 2, 'Result', n_21, 0, 'Image')
    _link(n_36, 0, 'Image', n_46, 0, 'Image')
    _link(n_62, 0, 'Value', n_46, 1, 'Alpha')
    _link(n_41, 0, 'Mask', n_39, 0, 'Color')
    _link(n_63, 0, 'Value', n_40, 0, 'Factor')
    _link(n_46, 0, 'Image', n_43, 6, 'A')
    _link(n_46, 0, 'Image', n_47, 1, 'Foreground')
    _link(n_47, 0, 'Image', n_55, 1, 'False')
    _link(n_64, 0, 'Value', n_41, 0, 'Mask')
    _link(n_65, 0, 'Value', n_20, 0, 'Factor')
    _link(n_20, 0, 'Color', n_51, 0, 'Image')
    _link(n_26, 0, 'Color', n_24, 2, 'True')
    _link(n_29, 0, 'Output', n_28, 7, 'B')
    _link(n_18, 0, 'Output', n_19, 7, 'B')
    _link(n_31, 0, 'Output', n_32, 7, 'B')
    _link(n_24, 0, 'Output', n_25, 7, 'B')
    _link(n_42, 0, 'Output', n_6, 0, 'Input')
    _link(n_66, 0, 'Value', n_34, 0, 'Factor')
    _link(n_34, 0, 'Color', n_35, 2, 'True')
    _link(n_35, 0, 'Output', n_33, 7, 'B')
    _link(n_50, 2, 'Result', n_49, 7, 'B')
    _link(n_14, 8, 'mat_color', n_10, 7, 'B')
    _link(n_14, 1, 'Alpha', n_10, 0, 'Factor')
    _link(n_14, 1, 'Alpha', n_54, 2, 'Factor')
    _link(n_52, 0, 'Image', n_57, 0, 'Image')
    _link(n_57, 0, 'Image', n_55, 2, 'True')
    _link(n_48, 0, 'Image', n_37, 0, 'Color')
    _link(n_36, 0, 'Image', n_48, 1, 'Foreground')
    _link(n_67, 0, 'Value', n_43, 0, 'Factor')
    _link(n_68, 0, 'Value', n_56, 1, 'Alpha')
    _link(n_38, 0, 'Image', n_44, 0, 'Color')
    _link(n_40, 0, 'Color', n_38, 1, 'Foreground')
    _link(n_54, 0, 'Image', n_52, 0, 'Background')
    _link(n_56, 0, 'Image', n_52, 1, 'Foreground')
    _link(n_42, 0, 'Output', n_54, 1, 'Foreground')
    _link(n_53, 0, 'Output', n_56, 0, 'Image')
    _link(n_56, 0, 'Image', n_45, 2, 'line')
    _link(n_55, 0, 'Output', n_45, 0, 'sample')
    _link(n_22, 0, 'Image', n_69, 0, 'Vector')
    _link(n_69, 1, 'Value', n_58, 0, 'Value')
    _link(n_5, 0, 'Image', n_70, 0, 'Vector')
    _link(n_70, 1, 'Value', n_59, 0, 'Value')
    _link(n_2, 0, 'Image', n_71, 0, 'Vector')
    _link(n_71, 1, 'Value', n_60, 0, 'Value')
    _link(n_9, 0, 'Image', n_72, 0, 'Vector')
    _link(n_72, 1, 'Value', n_61, 0, 'Value')
    _link(n_39, 0, 'Color', n_73, 0, 'Vector')
    _link(n_73, 1, 'Value', n_62, 0, 'Value')
    _link(n_47, 0, 'Image', n_74, 0, 'Vector')
    _link(n_74, 1, 'Value', n_63, 0, 'Value')
    _link(n_51, 0, 'Image', n_75, 0, 'Vector')
    _link(n_75, 1, 'Value', n_64, 0, 'Value')
    _link(n_12, 0, 'Output', n_76, 0, 'Vector')
    _link(n_76, 1, 'Value', n_65, 0, 'Value')
    _link(n_11, 0, 'Image', n_77, 0, 'Vector')
    _link(n_77, 1, 'Value', n_66, 0, 'Value')
    _link(n_37, 0, 'Color', n_78, 0, 'Vector')
    _link(n_78, 1, 'Value', n_67, 0, 'Value')
    _link(n_44, 0, 'Color', n_79, 0, 'Vector')
    _link(n_79, 1, 'Value', n_68, 0, 'Value')
    _link(n_1, 2, 'Result', n_81, 0, 'Image')
    _link(n_80, 3, 'Alpha', n_81, 1, 'Alpha')
    _link(n_81, 0, 'Image', n_2, 0, 'Image')
    _link(n_8, 2, 'Result', n_83, 0, 'Image')
    _link(n_82, 3, 'Alpha', n_83, 1, 'Alpha')
    _link(n_83, 0, 'Image', n_9, 0, 'Image')
    _link(n_10, 2, 'Result', n_85, 0, 'Image')
    _link(n_84, 3, 'Alpha', n_85, 1, 'Alpha')
    _link(n_85, 0, 'Image', n_11, 0, 'Image')
    _link(n_19, 2, 'Result', n_87, 0, 'Image')
    _link(n_86, 3, 'Alpha', n_87, 1, 'Alpha')
    _link(n_87, 0, 'Image', n_49, 6, 'A')
    _link(n_23, 2, 'Result', n_89, 0, 'Image')
    _link(n_88, 3, 'Alpha', n_89, 1, 'Alpha')
    _link(n_89, 0, 'Image', n_22, 0, 'Image')
    _link(n_25, 2, 'Result', n_91, 0, 'Image')
    _link(n_90, 3, 'Alpha', n_91, 1, 'Alpha')
    _link(n_91, 0, 'Image', n_16, 6, 'A')
    _link(n_28, 2, 'Result', n_93, 0, 'Image')
    _link(n_92, 3, 'Alpha', n_93, 1, 'Alpha')
    _link(n_93, 0, 'Image', n_17, 6, 'A')
    _link(n_32, 2, 'Result', n_95, 0, 'Image')
    _link(n_94, 3, 'Alpha', n_95, 1, 'Alpha')
    _link(n_95, 0, 'Image', n_50, 6, 'A')
    _link(n_33, 2, 'Result', n_97, 0, 'Image')
    _link(n_96, 3, 'Alpha', n_97, 1, 'Alpha')
    _link(n_97, 0, 'Image', n_50, 7, 'B')
    _link(n_46, 0, 'Image', n_98, 0, 'Image')
    _link(n_43, 2, 'Result', n_99, 0, 'Image')
    _link(n_98, 3, 'Alpha', n_99, 1, 'Alpha')

    return ng

# usage: ng = create_node_tree_freepencil_v1_1_0_pro()

create_node_tree = create_node_tree_freepencil_v1_1_0_pro  # backward-compat alias