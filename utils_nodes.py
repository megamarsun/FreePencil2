import bpy

from . import compat


def remove_auto_viewer_reroute(node_tree: bpy.types.NodeTree) -> None:
    """Remove auto-inserted Viewer or Reroute nodes in the given node tree."""
    for node in list(node_tree.nodes):
        if node.type in {"VIEWER", "REROUTE"}:
            links_to_remove = [
                link for link in list(node_tree.links)
                if link.from_node == node or link.to_node == node
            ]
            for link in links_to_remove:
                node_tree.links.remove(link)
            node_tree.nodes.remove(node)


def add_node_clean(node_tree: bpy.types.NodeTree, bl_idname: str, **kwargs):
    """Add a node using bpy.ops.node.add_node and clean up unwanted nodes."""
    existing_nodes = set(node_tree.nodes)
    bpy.ops.node.add_node(type=bl_idname, **kwargs)
    new_nodes = set(node_tree.nodes) - existing_nodes
    for node in list(new_nodes):
        if node.type in {"VIEWER", "REROUTE"}:
            links_to_remove = [
                link for link in list(node_tree.links)
                if link.from_node == node or link.to_node == node
            ]
            for link in links_to_remove:
                node_tree.links.remove(link)
            node_tree.nodes.remove(node)
            new_nodes.discard(node)
    return list(new_nodes)


def clear_node_tree(node_tree: bpy.types.NodeTree) -> None:
    """Clear all nodes from a node tree."""
    node_tree.nodes.clear()


def insert_antialiasing_if_needed(
    ntree: bpy.types.NodeTree,
    input_socket: bpy.types.NodeSocket,
    output_socket: bpy.types.NodeSocket,
    include_aa: bool,
    threshold: float = 0.1,
    contrast_limit: float = 0.2,
) -> bpy.types.Node | None:
    """Insert an Anti-Aliasing node between sockets if enabled.

    When ``include_aa`` is ``False`` the function ensures a direct link
    between ``input_socket`` and ``output_socket`` and returns ``None``.
    Otherwise an Anti-Aliasing node is created, initialised and linked in
    between the sockets and returned.
    """

    # Ensure no existing link when inserting AA.
    existing_links = [
        lnk
        for lnk in list(ntree.links)
        if lnk.from_socket == input_socket and lnk.to_socket == output_socket
    ]

    for lnk in existing_links:
        ntree.links.remove(lnk)

    if not include_aa:
        ntree.links.new(input_socket, output_socket)
        return None

    aa_node = ntree.nodes.new("CompositorNodeAntiAliasing")
    compat.set_node_value(aa_node, 'threshold', threshold)
    compat.set_node_value(aa_node, 'contrast_limit', contrast_limit)
    ntree.links.new(input_socket, aa_node.inputs[0])
    ntree.links.new(aa_node.outputs[0], output_socket)
    return aa_node
