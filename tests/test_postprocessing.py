from types import SimpleNamespace

import numpy as np
import pytest

from src.model.branch import Line, Transformer2, Transformer3
from src.model.conductivity_matrix import get_conductivity_matrix
from src.postprocessing import BranchFlow, SlackPower, calc_branch_flows, calc_results, calc_slack_powers


class TestSlackPowers:
    def test_hand_computed(self, two_bus):
        nodes, branches = two_bus
        nodes[1].u_magnitude, nodes[1].u_angle = 105.0, 0.0
        y = get_conductivity_matrix(nodes, branches)
        res = calc_slack_powers(nodes, y)
        assert len(res) == 1 and isinstance(res[0], SlackPower)
        yc = 1 / complex(10, 40)
        assert res[0].node_name == "1"
        assert res[0].p == pytest.approx((550 * yc.conjugate()).real)
        assert res[0].q == pytest.approx((550 * yc.conjugate()).imag)

    def test_slack_load_is_included(self, two_bus, make_load):
        nodes, branches = two_bus
        nodes[1].u_magnitude = 105.0
        nodes[0].loads = [make_load("SL", p_0=3.0, q_0=1.0)]
        y = get_conductivity_matrix(nodes, branches)
        res = calc_slack_powers(nodes, y)[0]
        assert res.p == pytest.approx(3.0 + (550 * (1 / complex(10, 40)).conjugate()).real)

    def test_no_slack_gives_empty_list(self, make_node):
        nodes = [make_node("1"), make_node("2")]
        assert calc_slack_powers(nodes, np.zeros((2, 2), dtype=complex)) == []


class TestLineFlows:
    def test_losses_match_i2z(self, two_bus):
        nodes, branches = two_bus
        nodes[1].u_magnitude, nodes[1].u_angle = 105.0, 0.05
        flow = calc_branch_flows(branches)[0]
        du2 = abs(nodes[0].u - nodes[1].u) ** 2
        g = 10 / (10**2 + 40**2)
        b = -40 / (10**2 + 40**2)
        assert flow.dp == pytest.approx(du2 * g)
        assert flow.dq == pytest.approx(-du2 * b)
        assert flow.p_2 == pytest.approx(flow.dp - flow.p_1)
        assert flow.q_2 == pytest.approx(flow.dq - flow.q_1)
        assert flow.p_3 is None and flow.q_3 is None

    def test_with_shunt_hand_computed(self, two_bus):
        nodes, branches = two_bus
        line = branches[0]
        line.g_shunt, line.b_shunt = 1e-6, 4e-5
        nodes[1].u_magnitude = 104.0
        u1, u2 = nodes[0].u, nodes[1].u
        y, y0 = 1 / line.z_1, line.y_shunt
        s1 = u1 * ((u1 - u2) * y + u1 * y0 / 2).conjugate()
        flow = calc_branch_flows(branches)[0]
        assert flow.p_1 == pytest.approx(s1.real)
        assert flow.q_1 == pytest.approx(s1.imag)

    def test_equal_voltages_no_series_flow(self, two_bus):
        nodes, branches = two_bus  # обе шины 110∠0, шунтов нет
        flow = calc_branch_flows(branches)[0]
        assert (flow.p_1, flow.q_1, flow.dp, flow.dq) == pytest.approx((0, 0, 0, 0))


class TestTransformer2Flows:
    @pytest.fixture
    def t2_case(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2", u_magnitude=36.0, u_angle=0.03)]
        t2 = Transformer2(
            branch_name="T2",
            node_1=nodes[0],
            node_2=nodes[1],
            r_1=2.0,
            x_1=30.0,
            g_shunt=0.0,
            b_shunt=0.0,
            u_1=110.0,
            u_2=35.0,
        )
        return nodes, t2

    def test_losses_match_referred_voltage_drop(self, t2_case):
        nodes, t2 = t2_case
        flow = calc_branch_flows([t2])[0]
        du2 = abs(nodes[0].u - t2.k_12 * nodes[1].u) ** 2
        g = 2 / (2**2 + 30**2)
        assert flow.dp == pytest.approx(du2 * g)
        assert flow.dp >= 0

    def test_unit_ratio_equals_line(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2", u_magnitude=105.0, u_angle=0.05)]
        common = dict(node_1=nodes[0], node_2=nodes[1], r_1=2.0, x_1=30.0, g_shunt=0.0, b_shunt=0.0)
        fl_line = calc_branch_flows([Line(branch_name="L", **common)])[0]
        fl_t2 = calc_branch_flows([Transformer2(branch_name="T2", u_1=110, u_2=110, **common)])[0]
        assert (fl_t2.p_1, fl_t2.q_1, fl_t2.p_2, fl_t2.q_2) == pytest.approx(
            (fl_line.p_1, fl_line.q_1, fl_line.p_2, fl_line.q_2)
        )


class TestTransformer3Flows:
    @pytest.fixture
    def t3_case(self, make_node):
        nodes = [
            make_node("1", "slack"),
            make_node("2", u_magnitude=36.0, u_angle=0.03),
            make_node("3", u_magnitude=10.5, u_angle=0.06),
        ]
        t3 = Transformer3(
            branch_name="T3",
            node_1=nodes[0],
            node_2=nodes[1],
            node_3=nodes[2],
            r_1=1.0,
            x_1=20.0,
            r_2=0.5,
            x_2=12.0,
            r_3=0.3,
            x_3=6.0,
            g_shunt=0.0,
            b_shunt=0.0,
            u_1=110.0,
            u_2=35.0,
            u_3=10.0,
        )
        return nodes, t3

    def test_kcl_at_neutral_and_winding_losses(self, t3_case):
        nodes, t3 = t3_case
        u1, u2, u3 = (n.u for n in nodes)
        yh, ym, yl = 1 / t3.z_1, 1 / t3.z_2, 1 / t3.z_3
        k1, k2 = t3.k_12, t3.k_13
        u_n = (u1 * yh + k1 * u2 * ym + k2 * u3 * yl) / (yh + ym + yl)
        # независимая проверка: 1-й закон Кирхгофа в нейтрали
        assert (u1 - u_n) * yh + (k1 * u2 - u_n) * ym + (k2 * u3 - u_n) * yl == pytest.approx(0j, abs=1e-9)
        dp = abs(u1 - u_n) ** 2 * yh.real + abs(k1 * u2 - u_n) ** 2 * ym.real + abs(k2 * u3 - u_n) ** 2 * yl.real
        dq = -abs(u1 - u_n) ** 2 * yh.imag - abs(k1 * u2 - u_n) ** 2 * ym.imag - abs(k2 * u3 - u_n) ** 2 * yl.imag
        flow = calc_branch_flows([t3])[0]
        assert flow.dp == pytest.approx(dp)
        assert flow.dq == pytest.approx(dq)
        assert flow.p_3 is not None and flow.q_3 is not None
        assert flow.dp == pytest.approx(flow.p_1 + flow.p_2 + flow.p_3)


def test_unknown_branch_type_raises():
    stub = SimpleNamespace(branch_name="X", node_1=SimpleNamespace(u=110 + 0j), node_2=SimpleNamespace(u=105 + 0j))
    with pytest.raises(TypeError, match="Неизвестный тип ветви"):
        calc_branch_flows([stub])


class TestCalcResults:
    def test_types_and_names(self, two_bus):
        nodes, branches = two_bus
        slacks, flows = calc_results(nodes, branches)
        assert [s.node_name for s in slacks] == ["1"]
        assert [f.branch_name for f in flows] == ["L-1-2"]
        assert isinstance(flows[0], BranchFlow)

    def test_power_balance_tellegen(self, two_bus):
        """Баланс (теорема Теллегена): S_slack + S_pq (в сеть) = потери в линии при любых U."""
        nodes, branches = two_bus
        nodes[1].u_magnitude, nodes[1].u_angle = 103.0, 0.07
        y = get_conductivity_matrix(nodes, branches)
        slacks, flows = calc_results(nodes, branches)
        u = np.array([n.u for n in nodes])
        s_net_pq = u[1] * np.conj(y[1] @ u)
        assert slacks[0].p + s_net_pq.real == pytest.approx(flows[0].dp)
        assert slacks[0].q + s_net_pq.imag == pytest.approx(flows[0].dq)
