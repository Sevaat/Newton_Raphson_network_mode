from django.db import transaction

from src.model.branch import Transformer2, Transformer3
from src.nr_method import ConvergenceError, NewtonRaphsonMethod
from src.postprocessing import BranchFlow, SlackPower, calc_results
from src.util.file_manager import FileManager

from . import models

KIND_SECTION = {"line": "LINES", "t2": "TRANSFORMERS2", "t3": "TRANSFORMERS3"}
LOAD_FIELDS = ("load_name", "p_0", "q_0", "z_p", "i_p", "p_p", "z_q", "i_q", "p_q", "u_0")
NODE_FIELDS = ("node_name", "type_node", "type_node_current", "u_base", "g_shunt", "b_shunt",
               "u_magnitude", "u_angle", "p_gen", "q_gen", "q_min", "q_max")
BRANCH_BASE = ("branch_name", "r_1", "x_1", "g_shunt", "b_shunt")
PARAM_FIELDS = ("accuracy", "max_iterations", "damping")


def _dump(obj, fields):
    return {f: getattr(obj, f) for f in fields}


def unique_name(base: str) -> str:
    name, i = base, 2
    while models.NetworkCase.objects.filter(name=name).exists():
        name, i = f"{base} ({i})", i + 1
    return name


def case_to_data(case: models.NetworkCase) -> dict:
    """Собрать канонический словарь (формат data/*.json) из БД."""
    nodes = []
    for n in case.nodes.all():
        item = _dump(n, NODE_FIELDS)
        if n.u_setpoint is not None:
            item["u_setpoint"] = n.u_setpoint
        item["loads"] = [l.load_name for l in n.loads.all()]
        nodes.append(item)
    sections = {}
    for b in case.branches.all():
        item = _dump(b, BRANCH_BASE)
        item["node_1"], item["node_2"] = b.node_1.node_name, b.node_2.node_name
        if b.kind in ("t2", "t3"):
            item.update(_dump(b, ("u_1", "u_2")))
        if b.kind == "t3":
            item.update(_dump(b, ("r_2", "x_2", "r_3", "x_3", "u_3")))
            item["node_3"] = b.node_3.node_name
        sections.setdefault(KIND_SECTION[b.kind], []).append(item)
    return {
        "CALCULATION PARAMETERS": _dump(case.parameters, PARAM_FIELDS),
        "LOADS": [_dump(l, LOAD_FIELDS) for l in case.loads.all()],
        "NODES": nodes,
        "BRANCHES": sections,
    }


@transaction.atomic
def save_data(case: models.NetworkCase, data: dict) -> None:
    """Провалидировать pydantic-моделями ядра и полностью заменить данные схемы."""
    loads, nodes, branches, parameters = FileManager.from_dict(data)
    case.branches.all().delete()
    case.nodes.all().delete()
    case.loads.all().delete()
    models.CalculationParameters.objects.update_or_create(case=case, defaults=_dump(parameters, PARAM_FIELDS))
    load_objs = {l.load_name: models.Load.objects.create(case=case, **l.model_dump()) for l in loads}
    node_objs = {}
    for n in nodes:
        node = models.Node.objects.create(case=case, **n.model_dump(exclude={"loads"}))
        node.loads.set([load_objs[l.load_name] for l in n.loads])
        node_objs[n.node_name] = node
    for b in branches:
        kind = "t3" if isinstance(b, Transformer3) else "t2" if isinstance(b, Transformer2) else "line"
        models.Branch.objects.create(
            case=case, kind=kind,
            node_1=node_objs[b.node_1.node_name], node_2=node_objs[b.node_2.node_name],
            node_3=node_objs[b.node_3.node_name] if kind == "t3" else None,
            **b.model_dump(exclude={"node_1", "node_2", "node_3"}),
        )


@transaction.atomic
def import_case(name: str, data: dict) -> models.NetworkCase:
    case = models.NetworkCase.objects.create(name=unique_name(name))
    save_data(case, data)
    return case


def run_calculation(case: models.NetworkCase) -> models.CalculationRun:
    loads, nodes, branches, parameters = FileManager.from_dict(case_to_data(case))
    try:
        nodes, branches, parameters = NewtonRaphsonMethod.run(nodes, branches, parameters)
        slack, flows = calc_results(nodes, branches)
    except (ConvergenceError, ValueError, ZeroDivisionError) as e:
        return models.CalculationRun.objects.create(case=case, converged=False, error=str(e))
    with transaction.atomic():
        run = models.CalculationRun.objects.create(
            case=case, converged=True,
            total_dp=sum(f.dp for f in flows), total_dq=sum(f.dq for f in flows),
        )
        models.NodeResult.objects.bulk_create([
            models.NodeResult(run=run, node_name=n.node_name, type_node_current=n.type_node_current,
                              u_magnitude=n.u_magnitude, u_angle=n.u_angle, q_gen=n.q_gen)
            for n in nodes
        ])
        models.SlackPowerResult.objects.bulk_create([
            models.SlackPowerResult(run=run, node_name=s.node_name, p=s.p, q=s.q) for s in slack
        ])
        models.BranchFlowResult.objects.bulk_create([
            models.BranchFlowResult(run=run, **f.model_dump()) for f in flows
        ])
    return run


def case_detail(case: models.NetworkCase) -> dict:
    return {
        "id": case.id, "name": case.name, "data": case_to_data(case),
        "runs": [{"id": r.id, "created_at": r.created_at, "converged": r.converged} for r in case.runs.all()],
    }


def run_detail(run: models.CalculationRun) -> dict:
    return {
        "id": run.id, "case_id": run.case_id, "created_at": run.created_at,
        "converged": run.converged, "error": run.error,
        "total_losses": {"dp": run.total_dp, "dq": run.total_dq} if run.converged else None,
        "nodes": [_dump(n, ("node_name", "type_node_current", "u_magnitude", "u_angle", "q_gen"))
                  for n in run.node_results.all()],
        "slack_powers": [_dump(s, ("node_name", "p", "q")) for s in run.slack_powers.all()],
        "branch_flows": [_dump(f, ("branch_name", "p_1", "q_1", "p_2", "q_2", "p_3", "q_3", "dp", "dq"))
                         for f in run.branch_flows.all()],
    }


def export_data(case: models.NetworkCase, run: models.CalculationRun | None = None) -> dict:
    """Экспорт: без run — входной формат; с run — формат result_*.json."""
    loads, nodes, branches, parameters = FileManager.from_dict(case_to_data(case))
    if run is None:
        return FileManager.to_dict(loads, nodes, branches, parameters)
    by_name = {n.node_name: n for n in nodes}
    for nr in run.node_results.all():
        n = by_name[nr.node_name]
        n.u_magnitude, n.u_angle = nr.u_magnitude, nr.u_angle
        n.type_node_current, n.q_gen = nr.type_node_current, nr.q_gen
    slack = [SlackPower(**_dump(s, ("node_name", "p", "q"))) for s in run.slack_powers.all()]
    flows = [BranchFlow(**_dump(f, ("branch_name", "p_1", "q_1", "p_2", "q_2", "p_3", "q_3", "dp", "dq")))
             for f in run.branch_flows.all()]
    return FileManager.to_dict(loads, nodes, branches, parameters, slack, flows)
