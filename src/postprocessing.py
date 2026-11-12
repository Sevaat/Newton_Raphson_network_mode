import logging
from typing import Any

import numpy
from pydantic import BaseModel

from src.model.branch import Line, Transformer2, Transformer3
from src.model.conductivity_matrix import get_conductivity_matrix
from src.model.node import Node

logger = logging.getLogger(__name__)


class SlackPower(BaseModel):
    """
    Мощность генерации балансирующего узла: нагрузка узла + отдача в сеть

    Args:
        node_name (str): уникальное наименование узла
        p (float): активная мощность узла, МВт
        q (float): реактивная мощность узла, Мвар
    """

    node_name: str
    p: float
    q: float


class BranchFlow(BaseModel):
    """
    Потоки мощности в ветви (из узла в ветвь)

    Args:
        branch_name (str): уникальное наименование ветви
        p_1 (float): поток активной мощности из узла 1 в ветвь, МВт
        q_1 (float): поток реактивной мощности из узла 1 в ветвь, Мвар
        p_2 (float): поток реактивной мощности из узла 2 в ветвь, МВт
        q_2 (float): поток реактивной мощности из узла 2 в ветвь, Мвар
        p_3 (float | None): поток активной мощности из узла 3 в ветвь, МВт
                    (только для трехобмоточного трансформатора)
        q_3 (float | None): поток реактивной мощности из узла 3 в ветвь, Мвар
                    (только для трехобмоточного трансформатора)
        dp (float): суммарные активные потери, МВт
        dq (float): суммарные реактивные потери, Мвар
    """

    branch_name: str
    p_1: float
    q_1: float
    p_2: float
    q_2: float
    p_3: float | None = None
    q_3: float | None = None
    dp: float
    dq: float


def calc_slack_powers(nodes: list[Node], conductivity_matrix: numpy.ndarray) -> list[SlackPower]:
    """
    Мощность балансирующих узлов по результатам расчета

    Args:
        nodes (list[Node]): список узлов
        conductivity_matrix (np.ndarray): матрица собственных и взаимных проводимостей

    Returns:
        list[SlackPower]: мощности генерации балансирующего узла: нагрузка узла + отдача в сеть
    """
    u = numpy.array([node.u for node in nodes])
    s_net = u * numpy.conj(conductivity_matrix @ u)
    result: list[SlackPower] = []
    for i, node in enumerate(nodes):
        if node.type_node != "slack":
            continue
        s = node.power_load + s_net[i]
        result.append(SlackPower(node_name=node.node_name, p=float(s.real), q=float(s.imag)))
    return result


def calc_branch_flows(branches: list[Any]) -> list[BranchFlow]:
    """
    Потоки и потери в ветвях; согласованы с моделями get_conductivity_matrix

    Args:
        branches (list[Any]): список ветвей

    Returns:
        list[BranchFlow]: мощности генерации балансирующего узла: нагрузка узла + отдача в сеть
    """
    flows: list[BranchFlow] = []
    for br in branches:
        u1, u2 = br.node_1.u, br.node_2.u
        s3 = complex(0, 0)
        p3: float | None = None
        q3: float | None = None
        if isinstance(br, Transformer3):
            u3 = br.node_3.u
            z_h, z_m, z_l = br.z_1, br.z_2, br.z_3
            k_hm, k_hl = br.k_12, br.k_13
            # напряжение нейтрали звезды (все величины приведены к стороне ВН)
            u_n = (u1 / z_h + k_hm * u2 / z_m + k_hl * u3 / z_l) / (1 / z_h + 1 / z_m + 1 / z_l)
            i1 = (u1 - u_n) / z_h + u1 * br.y_shunt
            i2 = k_hm * (k_hm * u2 - u_n) / z_m
            i3 = k_hl * (k_hl * u3 - u_n) / z_l
            s1, s2, s3 = u1 * i1.conjugate(), u2 * i2.conjugate(), u3 * i3.conjugate()
            p3, q3 = s3.real, s3.imag
        elif isinstance(br, Transformer2):
            y, k = 1 / br.z_1, br.k_12
            i1 = (u1 - k * u2) * y + u1 * br.y_shunt
            i2 = k * (k * u2 - u1) * y
            s1, s2 = u1 * i1.conjugate(), u2 * i2.conjugate()
        elif isinstance(br, Line):
            y, y0 = 1 / br.z_1, br.y_shunt
            i1 = (u1 - u2) * y + u1 * y0 / 2
            i2 = (u2 - u1) * y + u2 * y0 / 2
            s1, s2 = u1 * i1.conjugate(), u2 * i2.conjugate()
        else:
            raise TypeError(f"Неизвестный тип ветви: {type(br).__name__}")
        ds = s1 + s2 + s3
        flows.append(
            BranchFlow(
                branch_name=br.branch_name,
                p_1=s1.real,
                q_1=s1.imag,
                p_2=s2.real,
                q_2=s2.imag,
                p_3=p3,
                q_3=q3,
                dp=ds.real,
                dq=ds.imag,
            )
        )
    return flows


def calc_results(nodes: list[Node], branches: list[Any]) -> tuple[list[SlackPower], list[BranchFlow]]:
    """
    Постобработка сошедшегося режима: мощности slack-узлов и потоки в ветвях

    Args:
        nodes (list[Node]): список узлов
        branches (list[Any]): список ветвей

    Returns:
        tuple[list[SlackPower], list[BranchFlow]]: мощности slack-узлов и потоки в ветвях
    """
    conductivity_matrix = get_conductivity_matrix(nodes, branches)
    return calc_slack_powers(nodes, conductivity_matrix), calc_branch_flows(branches)
