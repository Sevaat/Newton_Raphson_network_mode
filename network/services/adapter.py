from django.db import transaction

from src.model.branch import Transformer2, Transformer3
from src.util.file_manager import FileManager

from network.models import Branch, Load, Node, Project

LOAD_FIELDS = ("load_name", "p_0", "q_0", "z_p", "i_p", "p_p", "z_q", "i_q", "p_q", "u_0")


def project_to_dict(project: Project) -> dict:
    loads = [{f: getattr(l, f) for f in LOAD_FIELDS} for l in project.loads.all()]
    nodes = []
    for n in project.nodes.prefetch_related("loads"):
        nodes.append({
            "node_name": n.node_name, "type_node": n.type_node, "type_node_current": n.type_node,
            "u_base": n.u_base, "g_shunt": n.g_shunt, "b_shunt": n.b_shunt,
            "u_magnitude": n.u_magnitude, "u_angle": n.u_angle,
            "p_gen": n.p_gen, "q_gen": n.q_gen, "q_min": n.q_min, "q_max": n.q_max,
            "u_setpoint": n.u_setpoint,
            "loads": [l.load_name for l in n.loads.all()],
        })
    branches = {"LINES": [], "TRANSFORMERS2": [], "TRANSFORMERS3": []}
    for b in project.branches.select_related("node_1", "node_2", "node_3"):
        payload = {
            "branch_name": b.branch_name,
            "node_1": b.node_1.node_name, "node_2": b.node_2.node_name,
            "r_1": b.r_1, "x_1": b.x_1, "g_shunt": b.g_shunt, "b_shunt": b.b_shunt,
        }
        if b.kind == "line":
            branches["LINES"].append(payload)
        elif b.kind == "t2":
            payload.update(u_1=b.u_1, u_2=b.u_2)
            branches["TRANSFORMERS2"].append(payload)
        else:
            payload.update(node_3=b.node_3.node_name, u_1=b.u_1, u_2=b.u_2, u_3=b.u_3,
                           r_2=b.r_2, x_2=b.x_2, r_3=b.r_3, x_3=b.x_3)
            branches["TRANSFORMERS3"].append(payload)
    return {
        "CALCULATION PARAMETERS": {
            "accuracy": project.accuracy,
            "max_iterations": project.max_iterations,
            "damping": project.damping,
        },
        "LOADS": loads, "NODES": nodes, "BRANCHES": branches,
    }


@transaction.atomic
def project_from_dict(data: dict, name: str, description: str = "", owner=None) -> Project:
    loads, nodes, branches, params = FileManager.load_from_dict(data)
    project = Project.objects.create(
        name=name, description=description, owner=owner,
        accuracy=params.accuracy, max_iterations=params.max_iterations, damping=params.damping,
    )
    load_map = {l.load_name: Load.objects.create(project=project, **l.model_dump()) for l in loads}
    node_map = {}
    for nd in nodes:
        node = Node.objects.create(project=project, **nd.model_dump(exclude={"loads", "type_node_current"}))
        node.loads.set([load_map[l.load_name] for l in nd.loads])
        node_map[nd.node_name] = node
    for br in branches:
        payload = br.model_dump(exclude={"node_1", "node_2", "node_3"})
        if isinstance(br, Transformer3):      # важно: Transformer3 — наследник Transformer2
            kind = "t3"
        elif isinstance(br, Transformer2):
            kind = "t2"
        else:
            kind = "line"
        Branch.objects.create(
            project=project, kind=kind,
            node_1=node_map[br.node_1.node_name],
            node_2=node_map[br.node_2.node_name],
            node_3=node_map[br.node_3.node_name] if kind == "t3" else None,
            **payload,
        )
    return project
