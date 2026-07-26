import bpy

def create_node_tree_freepencil_aov_group_v1_1_0():
    ng = bpy.data.node_groups.new('FreePencil_aov_Group_v1_1_0', 'ShaderNodeTree')
    ng.interface.new_socket(name='line_texture', in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='mask_texture', in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='bone_color', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='gen_color', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='line_color', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='mask_color', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='mat_color', in_out='OUTPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket(name='mecha_color', in_out='OUTPUT', socket_type='NodeSocketColor')
    n_0 = ng.nodes.new('ShaderNodeVertexColor')
    n_0.name = 'Color Attribute.001'
    n_0.label = 'freepencil_v_2'
    n_0.location = (-272.9571533203125, 0.0)
    n_0.hide = False
    n_0.layer_name = 'bone_color'

    n_1 = ng.nodes.new('ShaderNodeOutputAOV')
    n_1.name = 'AOV Output.001'
    n_1.label = 'freepencil_v_2'
    n_1.location = (0.0, 0.0)
    n_1.hide = False
    n_1.aov_name = 'bone_color'
    n_1.inputs[1].default_value = 0.0

    n_2 = ng.nodes.new('ShaderNodeMix')
    n_2.name = 'Mix'
    n_2.label = 'freepencil_v_2'
    n_2.location = (-272.9571533203125, -121.0)
    n_2.hide = False
    n_2.blend_type = 'MIX'
    n_2.data_type = 'RGBA'
    n_2.inputs[0].default_value = 0.5
    n_2.inputs[1].default_value = (0.5, 0.5, 0.5)
    n_2.inputs[2].default_value = 0.0
    n_2.inputs[3].default_value = 0.0
    n_2.inputs[4].default_value = (0.0, 0.0, 0.0)
    n_2.inputs[5].default_value = (0.0, 0.0, 0.0)
    n_2.inputs[8].default_value = (0.0, 0.0, 0.0)
    n_2.inputs[9].default_value = (0.0, 0.0, 0.0)

    n_3 = ng.nodes.new('ShaderNodeOutputAOV')
    n_3.name = 'AOV Output.002'
    n_3.label = 'freepencil_v_2'
    n_3.location = (0.0, -116.0)
    n_3.hide = False
    n_3.aov_name = 'gen_color'
    n_3.inputs[1].default_value = 0.0

    n_4 = ng.nodes.new('ShaderNodeMix')
    n_4.name = 'Mix.001'
    n_4.label = 'freepencil_v_2'
    n_4.location = (-512.9571533203125, 0.0)
    n_4.hide = False
    n_4.blend_type = 'MIX'
    n_4.data_type = 'RGBA'
    n_4.inputs[0].default_value = 0.5
    n_4.inputs[1].default_value = (0.5, 0.5, 0.5)
    n_4.inputs[2].default_value = 0.0
    n_4.inputs[3].default_value = 0.0
    n_4.inputs[4].default_value = (0.0, 0.0, 0.0)
    n_4.inputs[5].default_value = (0.0, 0.0, 0.0)
    n_4.inputs[7].default_value = (0.5, 0.5, 0.5, 1.0)
    n_4.inputs[8].default_value = (0.0, 0.0, 0.0)
    n_4.inputs[9].default_value = (0.0, 0.0, 0.0)

    n_5 = ng.nodes.new('ShaderNodeOutputAOV')
    n_5.name = 'AOV Output.004'
    n_5.label = 'freepencil_v_2'
    n_5.location = (0.0, -232.0)
    n_5.hide = False
    n_5.aov_name = 'line_color'
    n_5.inputs[1].default_value = 0.0

    n_6 = ng.nodes.new('ShaderNodeOutputAOV')
    n_6.name = 'AOV Output.005'
    n_6.label = 'freepencil_v_2'
    n_6.location = (0.0, -348.0)
    n_6.hide = False
    n_6.aov_name = 'mask_color'
    n_6.inputs[1].default_value = 0.0

    n_7 = ng.nodes.new('ShaderNodeVertexColor')
    n_7.name = 'Color Attribute.003'
    n_7.label = 'freepencil_v_2'
    n_7.location = (-272.9571533203125, -310.0)
    n_7.hide = False
    n_7.layer_name = 'line_color'

    n_8 = ng.nodes.new('ShaderNodeOutputAOV')
    n_8.name = 'AOV Output.003'
    n_8.label = 'freepencil_v_2'
    n_8.location = (0.0, -464.0)
    n_8.hide = False
    n_8.aov_name = 'mat_color'
    n_8.inputs[1].default_value = 0.0

    n_9 = ng.nodes.new('ShaderNodeVertexColor')
    n_9.name = 'Color Attribute'
    n_9.label = 'freepencil_v_2'
    n_9.location = (-1242.9571533203125, 0.0)
    n_9.hide = False
    n_9.layer_name = 'mecha_color'

    n_10 = ng.nodes.new('ShaderNodeValToRGB')
    n_10.name = 'ColorRamp'
    n_10.label = ''
    n_10.location = (-272.9571533203125, -627.0)
    n_10.hide = True
    n_10.width = 172.9571533203125
    # ===== Shader ColorRamp for n_10 =====
    # Original: 8 elements
    ramp = n_10.color_ramp
    
    # Blenderの仕様: ColorRampは最低2要素が必要
    # 戦略: デフォルト要素を直接上書きする
    
    # 8要素の場合: 手動削除後に再構築
    # Blender 4.3対応: clear()の代わりに手動削除
    elements_to_remove = list(ramp.elements)
    for elem in elements_to_remove:
        try:
            ramp.elements.remove(elem)
        except:
            pass
    
    # 削除後の確認
    
    # 要素1: pos=0.000000, color=(0.0, 0.0014692827826365829, 1.0, 1.0)
    elem_0 = ramp.elements.new(0.0000000000)
    elem_0.color = (0.000000, 0.001469, 1.000000, 1.000000)
    
    # 要素2: pos=0.122727, color=(1.0, 0.0, 0.11048056185245514, 1.0)
    elem_1 = ramp.elements.new(0.1227272674)
    elem_1.color = (1.000000, 0.000000, 0.110481, 1.000000)
    
    # 要素3: pos=0.297727, color=(0.05597496032714844, 1.0, 0.0, 1.0)
    elem_2 = ramp.elements.new(0.2977271676)
    elem_2.color = (0.055975, 1.000000, 0.000000, 1.000000)
    
    # 要素4: pos=0.451136, color=(0.0, 0.08322811126708984, 1.0, 1.0)
    elem_3 = ramp.elements.new(0.4511362910)
    elem_3.color = (0.000000, 0.083228, 1.000000, 1.000000)
    
    # 要素5: pos=0.567613, color=(1.0, 0.0, 0.06960153579711914, 1.0)
    elem_4 = ramp.elements.new(0.5676134229)
    elem_4.color = (1.000000, 0.000000, 0.069602, 1.000000)
    
    # 要素6: pos=0.707102, color=(0.07641482353210449, 1.0, 0.0, 1.0)
    elem_5 = ramp.elements.new(0.7071019411)
    elem_5.color = (0.076415, 1.000000, 0.000000, 1.000000)
    
    # 要素7: pos=0.864630, color=(0.0, 0.07300901412963867, 1.0, 1.0)
    elem_6 = ramp.elements.new(0.8646302223)
    elem_6.color = (0.000000, 0.073009, 1.000000, 1.000000)
    
    # 要素8: pos=1.000000, color=(1.0, 0.0, 0.07471179962158203, 1.0)
    elem_7 = ramp.elements.new(1.0000000000)
    elem_7.color = (1.000000, 0.000000, 0.074712, 1.000000)
    
    # ColorRamp設定
    ramp.interpolation = 'LINEAR'
    ramp.color_mode = 'HSL'
    ramp.hue_interpolation = 'CCW'
    
    # 検証
    

    n_11 = ng.nodes.new('ShaderNodeMix')
    n_11.name = 'Mix.004'
    n_11.label = ''
    n_11.location = (-272.9571533203125, -431.0)
    n_11.hide = False
    n_11.blend_type = 'ADD'
    n_11.data_type = 'RGBA'
    n_11.inputs[0].default_value = 0.5
    n_11.inputs[1].default_value = (0.5, 0.5, 0.5)
    n_11.inputs[2].default_value = 0.0
    n_11.inputs[3].default_value = 0.0
    n_11.inputs[4].default_value = (0.0, 0.0, 0.0)
    n_11.inputs[5].default_value = (0.0, 0.0, 0.0)
    n_11.inputs[8].default_value = (0.0, 0.0, 0.0)
    n_11.inputs[9].default_value = (0.0, 0.0, 0.0)

    n_12 = ng.nodes.new('ShaderNodeObjectInfo')
    n_12.name = 'Object Info'
    n_12.label = ''
    n_12.location = (-1002.9571533203125, 0.0)
    n_12.hide = False

    n_13 = ng.nodes.new('ShaderNodeVertexColor')
    n_13.name = 'Color Attribute.002'
    n_13.label = 'freepencil_v_2'
    n_13.location = (-512.9571533203125, -189.0)
    n_13.hide = False
    n_13.layer_name = 'mask_color'

    n_14 = ng.nodes.new('ShaderNodeRGBToBW')
    n_14.name = 'RGB to BW'
    n_14.label = ''
    n_14.location = (-512.9571533203125, -310.0)
    n_14.hide = False

    n_15 = ng.nodes.new('ShaderNodeTexCoord')
    n_15.name = 'Texture Coordinate'
    n_15.label = 'freepencil_v_2'
    n_15.location = (-762.9571533203125, 0.0)
    n_15.hide = False

    n_16 = ng.nodes.new('ShaderNodeMix')
    n_16.name = 'Mix.002'
    n_16.label = ''
    n_16.location = (-1002.9571533203125, -154.0)
    n_16.hide = False
    n_16.blend_type = 'MIX'
    n_16.data_type = 'RGBA'
    n_16.inputs[0].default_value = 0.5
    n_16.inputs[1].default_value = (0.5, 0.5, 0.5)
    n_16.inputs[2].default_value = 0.0
    n_16.inputs[3].default_value = 0.0
    n_16.inputs[4].default_value = (0.0, 0.0, 0.0)
    n_16.inputs[5].default_value = (0.0, 0.0, 0.0)
    n_16.inputs[8].default_value = (0.0, 0.0, 0.0)
    n_16.inputs[9].default_value = (0.0, 0.0, 0.0)

    n_17 = ng.nodes.new('NodeGroupInput')
    n_17.name = 'Group Input'
    n_17.label = ''
    n_17.location = (-1242.9571533203125, -121.0)
    n_17.hide = False

    n_18 = ng.nodes.new('ShaderNodeOutputAOV')
    n_18.name = 'AOV Output'
    n_18.label = 'freepencil_v_2'
    n_18.location = (0.0, -580.0)
    n_18.hide = False
    n_18.aov_name = 'mecha_color'
    n_18.inputs[1].default_value = 0.0

    n_19 = ng.nodes.new('ShaderNodeMix')
    n_19.name = 'Mix.005'
    n_19.label = ''
    n_19.location = (-272.9571533203125, -670.0)
    n_19.hide = False
    n_19.blend_type = 'MIX'
    n_19.data_type = 'RGBA'
    n_19.inputs[1].default_value = (0.5, 0.5, 0.5)
    n_19.inputs[2].default_value = 0.0
    n_19.inputs[3].default_value = 0.0
    n_19.inputs[4].default_value = (0.0, 0.0, 0.0)
    n_19.inputs[5].default_value = (0.0, 0.0, 0.0)
    n_19.inputs[8].default_value = (0.0, 0.0, 0.0)
    n_19.inputs[9].default_value = (0.0, 0.0, 0.0)

    n_20 = ng.nodes.new('ShaderNodeSeparateXYZ')
    n_20.name = 'Separate XYZ'
    n_20.label = ''
    n_20.location = (-512.9571533203125, -455.0)
    n_20.hide = False

    n_21 = ng.nodes.new('ShaderNodeMix')
    n_21.name = 'Mix.003'
    n_21.label = ''
    n_21.location = (-512.9571533203125, -412.0)
    n_21.hide = True
    n_21.blend_type = 'MIX'
    n_21.data_type = 'RGBA'
    n_21.inputs[1].default_value = (0.5, 0.5, 0.5)
    n_21.inputs[2].default_value = 0.0
    n_21.inputs[3].default_value = 0.0
    n_21.inputs[4].default_value = (0.0, 0.0, 0.0)
    n_21.inputs[5].default_value = (0.0, 0.0, 0.0)
    n_21.inputs[7].default_value = (0.5, 0.5, 0.5, 1.0)
    n_21.inputs[8].default_value = (0.0, 0.0, 0.0)
    n_21.inputs[9].default_value = (0.0, 0.0, 0.0)

    n_22 = ng.nodes.new('ShaderNodeHueSaturation')
    n_22.name = 'Hue Saturation Value'
    n_22.label = ''
    n_22.location = (-762.9571533203125, -486.5872497558594)
    n_22.hide = False
    n_22.inputs[0].default_value = 0.5
    n_22.inputs[1].default_value = 2.0
    n_22.inputs[2].default_value = 2.0
    n_22.inputs[3].default_value = 1.0

    n_23 = ng.nodes.new('ShaderNodeInvert')
    n_23.name = 'Invert'
    n_23.label = ''
    n_23.location = (-512.9571533203125, -591.0155029296875)
    n_23.hide = False
    n_23.inputs[0].default_value = 0.20000000298023224

    n_24 = ng.nodes.new('ShaderNodeMapRange')
    n_24.name = 'Map Range'
    n_24.label = ''
    n_24.location = (-762.9571533203125, -251.0)
    n_24.hide = False
    n_24.inputs[1].default_value = 0.0
    n_24.inputs[2].default_value = 20.0
    n_24.inputs[3].default_value = 0.0
    n_24.inputs[4].default_value = 1.0
    n_24.inputs[5].default_value = 4.0
    n_24.inputs[6].default_value = (0.0, 0.0, 0.0)
    n_24.inputs[7].default_value = (0.0, 0.0, 0.0)
    n_24.inputs[8].default_value = (1.0, 1.0, 1.0)
    n_24.inputs[9].default_value = (0.0, 0.0, 0.0)
    n_24.inputs[10].default_value = (1.0, 1.0, 1.0)
    n_24.inputs[11].default_value = (4.0, 4.0, 4.0)

    # links:
    # Debug: リンク情報
    # Link 0: Group Input[line_texture] -> Mix.002[B]
    ng.links.new(n_17.outputs[0], n_16.inputs[7])
    # Link 1: Mix.002[Result] -> Mix.005[A]
    ng.links.new(n_16.outputs[2], n_19.inputs[6])
    # Link 2: Color Attribute.001[Color] -> AOV Output.001[Color]
    ng.links.new(n_0.outputs[0], n_1.inputs[0])
    # Link 3: Mix[Result] -> AOV Output.002[Color]
    ng.links.new(n_2.outputs[2], n_3.inputs[0])
    # Link 4: Texture Coordinate[Generated] -> Mix[A]
    ng.links.new(n_15.outputs[0], n_2.inputs[6])
    # Link 5: Mix.001[Result] -> Mix[B]
    ng.links.new(n_4.outputs[2], n_2.inputs[7])
    # Link 6: Texture Coordinate[Normal] -> Mix.001[A]
    ng.links.new(n_15.outputs[1], n_4.inputs[6])
    # Link 7: Color Attribute[Color] -> Mix.002[A]
    ng.links.new(n_9.outputs[0], n_16.inputs[6])
    # Link 8: Color Attribute.002[Color] -> Mix.004[A]
    ng.links.new(n_13.outputs[0], n_11.inputs[6])
    # Link 9: Color Attribute.003[Color] -> AOV Output.004[Color]
    ng.links.new(n_7.outputs[0], n_5.inputs[0])
    # Link 10: Object Info[Material Index] -> Map Range[Value]
    ng.links.new(n_12.outputs[4], n_24.inputs[0])
    # Link 11: ColorRamp[Color] -> AOV Output.003[Color]
    ng.links.new(n_10.outputs[0], n_8.inputs[0])
    # Link 12: Mix.003[Result] -> ColorRamp[Fac]
    ng.links.new(n_21.outputs[2], n_10.inputs[0])
    # Link 13: Map Range[Result] -> Mix.003[A]
    ng.links.new(n_24.outputs[0], n_21.inputs[6])
    # Link 14: Object Info[Random] -> Mix.003[Factor]
    ng.links.new(n_12.outputs[5], n_21.inputs[0])
    # Link 15: Mix.004[Result] -> AOV Output.005[Color]
    ng.links.new(n_11.outputs[2], n_6.inputs[0])
    # Link 16: Group Input[mask_texture] -> RGB to BW[Color]
    ng.links.new(n_17.outputs[1], n_14.inputs[0])
    # Link 17: RGB to BW[Val] -> Mix.004[B]
    ng.links.new(n_14.outputs[0], n_11.inputs[7])
    # Link 18: Mix.005[Result] -> AOV Output[Color]
    ng.links.new(n_19.outputs[2], n_18.inputs[0])
    # Link 19: Texture Coordinate[Generated] -> Separate XYZ[Vector]
    ng.links.new(n_15.outputs[0], n_20.inputs[0])
    # Link 20: Hue Saturation Value[Color] -> Invert[Color]
    ng.links.new(n_22.outputs[0], n_23.inputs[1])
    # Link 21: Mix.002[Result] -> Hue Saturation Value[Color]
    ng.links.new(n_16.outputs[2], n_22.inputs[4])
    # Link 22: Separate XYZ[X] -> Mix.005[Factor]
    ng.links.new(n_20.outputs[0], n_19.inputs[0])
    # Link 23: Invert[Color] -> Mix.005[B]
    ng.links.new(n_23.outputs[0], n_19.inputs[7])
    # Debug: ノード一覧
    # Color Attribute.001 (ShaderNodeVertexColor) -> n_0
    # AOV Output.001 (ShaderNodeOutputAOV) -> n_1
    # Mix (ShaderNodeMix) -> n_2
    # AOV Output.002 (ShaderNodeOutputAOV) -> n_3
    # Mix.001 (ShaderNodeMix) -> n_4
    # AOV Output.004 (ShaderNodeOutputAOV) -> n_5
    # AOV Output.005 (ShaderNodeOutputAOV) -> n_6
    # Color Attribute.003 (ShaderNodeVertexColor) -> n_7
    # AOV Output.003 (ShaderNodeOutputAOV) -> n_8
    # Color Attribute (ShaderNodeVertexColor) -> n_9
    # ColorRamp (ShaderNodeValToRGB) -> n_10
    # Mix.004 (ShaderNodeMix) -> n_11
    # Object Info (ShaderNodeObjectInfo) -> n_12
    # Color Attribute.002 (ShaderNodeVertexColor) -> n_13
    # RGB to BW (ShaderNodeRGBToBW) -> n_14
    # Texture Coordinate (ShaderNodeTexCoord) -> n_15
    # Mix.002 (ShaderNodeMix) -> n_16
    # Group Input (NodeGroupInput) -> n_17
    # AOV Output (ShaderNodeOutputAOV) -> n_18
    # Mix.005 (ShaderNodeMix) -> n_19
    # Separate XYZ (ShaderNodeSeparateXYZ) -> n_20
    # Mix.003 (ShaderNodeMix) -> n_21
    # Hue Saturation Value (ShaderNodeHueSaturation) -> n_22
    # Invert (ShaderNodeInvert) -> n_23
    # Map Range (ShaderNodeMapRange) -> n_24

    return ng

# usage: ng = create_node_tree_freepencil_aov_group_v1_1_0()

create_node_tree = create_node_tree_freepencil_aov_group_v1_1_0  # backward‑compat alias