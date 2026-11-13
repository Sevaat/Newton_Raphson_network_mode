import pytest

from src.model.branch import Line
from src.model.load import Load
from src.model.node import Node
from src.model.parameters import Parameters


@pytest.fixture
def make_load():
    """Фабрика ZIP-нагрузки (по умолчанию постоянная мощность 20 + j10 при 110 кВ)."""

    def _make(name: str = "L1", **kw) -> Load:
        data = dict(
            load_name=name, p_0=20.0, q_0=10.0, z_p=0.0, i_p=0.0, p_p=1.0, z_q=0.0, i_q=0.0, p_q=1.0, u_0=110.0
        )
        data.update(kw)
        return Load(**data)

    return _make


@pytest.fixture
def make_node():
    """Фабрика узла 110 кВ (по умолчанию PQ, 110 кВ, угол 0, без шунтов и генерации)."""

    def _make(name: str = "1", type_node: str = "pq", **kw) -> Node:
        data = dict(
            node_name=name,
            type_node=type_node,
            type_node_current=type_node,
            u_base=110,
            g_shunt=0.0,
            b_shunt=0.0,
            u_magnitude=110.0,
            u_angle=0.0,
            p_gen=0.0,
            q_gen=0.0,
            q_min=0.0,
            q_max=0.0,
            loads=[],
        )
        data.update(kw)
        return Node(**data)

    return _make


@pytest.fixture
def two_bus(make_node, make_load):
    """Slack 110 кВ — линия 10+j40 Ом — PQ-нагрузка 20+j10 МВА (без шунтов).

    Режим имеет аналитическое решение: |U2| ~ 104.026 кВ, delta2 ~ -0.06121 рад.
    """
    slack = make_node("1", "slack")
    pq = make_node("2", "pq", loads=[make_load()])
    line = Line(branch_name="L-1-2", node_1=slack, node_2=pq, r_1=10.0, x_1=40.0, g_shunt=0.0, b_shunt=0.0)
    return [slack, pq], [line]


@pytest.fixture
def params():
    return Parameters(accuracy=1e-6, max_iterations=100)
