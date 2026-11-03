"""Transactional reference-search actions, independent of a learned policy."""
import copy
import math
from typed_cell import CellType, VerticalScope
from shared_modules import infer


def apply_action(graph, action, require_access=False):
    """Apply one move or joint role change; rollback incompatible assignments.

    Adding a node requires an existing construction anchor. This is the public
    growth interface; BuildingGraph.add_node remains a low-level fixture helper.
    """
    old=copy.deepcopy(graph.__dict__)
    try:
        kind=action['kind']
        if kind=='attach':
            anchor=graph.nodes[action['anchor']]
            if action['id'] in graph.nodes: raise ValueError('duplicate occurrence id')
            x,y=float(action['x']),float(action['y'])
            if not math.isfinite(x) or not math.isfinite(y): raise ValueError('nonfinite pose')
            graph.add_node(action['id'],x,y,floor_index=anchor.floor_index,
                scope=VerticalScope(action.get('scope','independent')),
                cell_type=CellType(action.get('function','room')))
            graph.add_edge(action['id'],anchor.node_id,properties={'relation':'construction','validated':False})
        elif kind=='reassign':
            graph.reassign_functions(action['functions'],require_access=require_access)
        elif kind=='pose':
            node=graph.nodes[action['id']]; root=node.metadata.get('root_id',node.node_id)
            x,y=float(action['x']),float(action['y'])
            if not math.isfinite(x) or not math.isfinite(y): raise ValueError('nonfinite pose')
            for n in graph.nodes.values():
                if n.node_id==root or n.metadata.get('root_id')==root:
                    n.x=x;n.y=y
        else: raise ValueError('unknown graph action')
        solution=infer(graph)
        if solution.unresolved: raise ValueError(str(solution.unresolved))
        if require_access and not graph.validate_circulation_connectivity():
            raise ValueError('same-floor access disconnected')
        return solution
    except Exception:
        graph.__dict__.clear();graph.__dict__.update(old)
        raise
