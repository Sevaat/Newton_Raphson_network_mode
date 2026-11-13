import math
from unittest.mock import patch
from src.nr_method import ConvergenceError, NewtonRaphsonMethod as NR

import numpy as np
import pytest

from src.model.conductivity_matrix import get_conductivity_matrix
from src.model.parameters import Parameters
from src.nr_method import NewtonRaphsonMethod as NR

# Аналитическое решение классической двухузловой задачи (slack 110 кВ, линия 10+j40 Ом, нагрузка 20+j10):
# U1^2*|U2|^2 = (|U2|^2 + PR + QX)^2 + (PX - QR)^2 — квадратное уравнение относительно |U2|^2.
P, Q, R, X, U1 = 20.0, 10.0, 10.0, 40.0, 110.0
A, B = P * R + Q * X, P * X - Q * R
V2_SQ = (U1**2 - 2 * A + math.sqrt((U1**2 - 2 * A) ** 2 - 4 * (A**2 + B**2))) / 2
U2_ANALYTIC = math.sqrt(V2_SQ)  # ~104.026 кВ (рабочий корень)
DELTA2_ANALYTIC = math.atan2(-B / U1, (V2_SQ + A) / U1)  # ~ -0.06121 рад


class TestPowerImbalance:
    def test_hand_computed_values(self, two_bus):
        nodes, branches = two_bus
        nodes[1].u_magnitude = 105.0
        y = get_conductivity_matrix(nodes, branches)
        w = NR._get_power_imbalance(nodes, y)
        yc = 1 / complex(10, 40)
        assert w[1] == pytest.approx(complex(20, 10) - 525 * yc.conjugate())
        assert w[0] == pytest.approx(550 * yc.conjugate())

    def test_zero_at_analytic_solution(self, two_bus):
        nodes, branches = two_bus
        nodes[1].u_magnitude = U2_ANALYTIC
        nodes[1].u_angle = DELTA2_ANALYTIC % (2 * math.pi)
        y = get_conductivity_matrix(nodes, branches)
        w = NR._get_power_imbalance(nodes, y)
        assert w[1] == pytest.approx(0j, abs=1e-8)

    def test_generation_reduces_imbalance(self, two_bus):
        nodes, branches = two_bus
        y = get_conductivity_matrix(nodes, branches)
        w0 = NR._get_power_imbalance(nodes, y)[1]
        nodes[1].p_gen, nodes[1].q_gen = 5.0, 2.0
        w1 = NR._get_power_imbalance(nodes, y)[1]
        assert w0 - w1 == pytest.approx(complex(5, 2))

    def test_slack_row_is_network_power(self, two_bus):
        nodes, branches = two_bus
        y = get_conductivity_matrix(nodes, branches)
        w = NR._get_power_imbalance(nodes, y)
        u = np.array([n.u for n in nodes])
        assert w[0] == pytest.approx(u[0] * np.conj(y[0] @ u))


class TestUnbalanceCondition:
    def test_all_below_accuracy(self, two_bus, params):
        nodes, _ = two_bus
        assert NR._unbalance_condition(nodes, params, [complex(1e-9, 1e-9), complex(1e-9, 1e-9)]) is True

    def test_active_above_accuracy(self, two_bus, params):
        nodes, _ = two_bus
        assert NR._unbalance_condition(nodes, params, [0j, complex(1.0, 0)]) is False

    def test_reactive_above_accuracy(self, two_bus, params):
        nodes, _ = two_bus
        assert NR._unbalance_condition(nodes, params, [0j, complex(0, 1.0)]) is False

    def test_slack_is_ignored(self, two_bus, params):
        nodes, _ = two_bus
        assert NR._unbalance_condition(nodes, params, [complex(50, 60), 0j]) is True


class TestLoadDerivative:
    @pytest.fixture
    def zip_node(self, make_node, make_load):
        ld = make_load(p_0=100.0, q_0=50.0, z_p=0.3, i_p=0.3, p_p=0.4, z_q=0.2, i_q=0.5, p_q=0.3)
        return make_node(loads=[ld])

    def test_p_derivative_value(self, zip_node):
        # 100 * (0.3/110^2 * 2*110 + 0.3/110) = 100 * 0.9/110
        assert NR._get_p_q_load_derivative(zip_node, "P") == pytest.approx(90.0 / 110.0)

    def test_q_derivative_value(self, zip_node):
        # 50 * (0.2*2/110 + 0.5/110) = 50 * 0.9/110
        assert NR._get_p_q_load_derivative(zip_node, "Q") == pytest.approx(45.0 / 110.0)

    @pytest.mark.parametrize("p_q,part", [("P", "real"), ("Q", "imag")])
    def test_matches_numerical_derivative_of_load_model(self, zip_node, p_q, part):
        h, u0 = 1e-5, zip_node.u_magnitude
        num = (
            getattr(zip_node.loads[0].power_load(u0 + h), part) - getattr(zip_node.loads[0].power_load(u0 - h), part)
        ) / (2 * h)
        assert NR._get_p_q_load_derivative(zip_node, p_q) == pytest.approx(num, rel=1e-6)

    def test_sums_over_loads(self, make_node, make_load):
        node = make_node(
            loads=[
                make_load("a", p_0=100, z_p=0.5, i_p=0.5, p_p=0.0),
                make_load("b", p_0=100, z_p=0.5, i_p=0.5, p_p=0.0),
            ]
        )
        assert NR._get_p_q_load_derivative(node, "P") == pytest.approx(300.0 / 110.0)

    def test_empty_loads_gives_zero(self, make_node):
        assert NR._get_p_q_load_derivative(make_node(), "P") == 0.0

    def test_none_loads_raises(self, make_node):
        node = make_node()
        node.loads = None  # присваивание без валидации (validate_assignment выключен)
        with pytest.raises(ValueError):
            NR._get_p_q_load_derivative(node, "P")

    def test_non_load_element_raises(self, make_node):
        node = make_node()
        node.loads = ["не нагрузка"]
        with pytest.raises(TypeError):
            NR._get_p_q_load_derivative(node, "Q")

    def test_wrong_power_type_raises(self, make_node):
        with pytest.raises(ValueError, match="'P'"):
            NR._get_p_q_load_derivative(make_node(), "S")


class TestJacobian:
    def test_shape_single_pq(self, two_bus):
        nodes, branches = two_bus
        y = get_conductivity_matrix(nodes, branches)
        assert NR._get_jacobian_matrix(nodes, y).shape == (2, 2)

    def test_shape_pu_only_angle_unknown(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2", "pu", q_min=0, q_max=50)]
        y = get_conductivity_matrix(nodes, [])
        assert NR._get_jacobian_matrix(nodes, y).shape == (1, 1)

    def test_block_assembly(self, two_bus):
        nodes, branches = two_bus
        y = get_conductivity_matrix(nodes, branches)
        expected = np.block(
            [
                [NR._get_h_matrix(nodes, y), NR._get_n_matrix(nodes, y)],
                [NR._get_m_matrix(nodes, y), NR._get_l_matrix(nodes, y)],
            ]
        )
        assert NR._get_jacobian_matrix(nodes, y) == pytest.approx(expected)

    def test_matches_numerical_jacobian(self, two_bus):
        nodes, branches = two_bus
        nodes[1].u_magnitude, nodes[1].u_angle = 104.0, 6.22
        y = get_conductivity_matrix(nodes, branches)
        j_an = NR._get_jacobian_matrix(nodes, y)

        def w_vec():
            w = NR._get_power_imbalance(nodes, y)[1]
            return np.array([w.real, w.imag])

        j_num = np.zeros((2, 2))
        h = 1e-6
        for col, attr in enumerate(("u_angle", "u_magnitude")):
            old = getattr(nodes[1], attr)
            setattr(nodes[1], attr, old + h)
            fp = w_vec()
            setattr(nodes[1], attr, old - h)
            fm = w_vec()
            setattr(nodes[1], attr, old)
            j_num[:, col] = (fp - fm) / (2 * h)
        assert j_an == pytest.approx(j_num, rel=1e-4, abs=1e-4)


class TestAdjustments:
    def test_single_pq_identity_jacobian(self, two_bus):
        nodes, _ = two_bus
        adj = NR._get_adjustments(nodes, [0j, complex(3, 4)], np.eye(2))
        assert adj == pytest.approx([-3.0, -4.0])

    def test_block_order_two_pq(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2"), make_node("3")]
        w = [0j, complex(1, 2), complex(3, 4)]
        adj = NR._get_adjustments(nodes, w, np.eye(4))
        assert adj == pytest.approx([-1.0, -3.0, -2.0, -4.0])

    def test_pu_dimension(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2", "pu", q_min=0, q_max=50)]
        adj = NR._get_adjustments(nodes, [0j, complex(3, 4)], np.eye(1))
        assert adj == pytest.approx([-3.0])


class TestAdjustNodes:
    def test_pq_gets_angle_and_magnitude(self, two_bus):
        nodes, _ = two_bus
        NR._adjust_nodes(nodes, np.array([0.01, -2.0]))
        assert nodes[1].u_angle == pytest.approx(0.01)
        assert nodes[1].u_magnitude == pytest.approx(108.0)

    def test_slack_untouched(self, two_bus):
        nodes, _ = two_bus
        NR._adjust_nodes(nodes, np.array([0.01, -2.0]))
        assert (nodes[0].u_angle, nodes[0].u_magnitude) == (0.0, 110.0)

    def test_pu_gets_angle_only(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2", "pu", q_min=0, q_max=50)]
        NR._adjust_nodes(nodes, np.array([0.02]))
        assert nodes[1].u_angle == pytest.approx(0.02)
        assert nodes[1].u_magnitude == 110.0


class TestCheckQLimits:
    @pytest.fixture
    def pu_node(self, make_node, make_load):
        def _make(q_load, q_min, q_max):
            ld = make_load(p_0=0.0, q_0=q_load)
            return make_node("G", "pu", loads=[ld], q_min=q_min, q_max=q_max, q_gen=20.0)

        return _make

    def test_within_limits_stays_pu(self, pu_node):
        node = pu_node(30.0, 10.0, 50.0)
        NR.check_q_limits([node], np.zeros((1, 1), dtype=complex))
        assert node.q_gen == pytest.approx(30.0)
        assert node.type_node_current == "pu"

    def test_above_max_clamped_to_pq(self, pu_node):
        node = pu_node(30.0, 10.0, 25.0)
        NR.check_q_limits([node], np.zeros((1, 1), dtype=complex))
        assert node.q_gen == 25.0
        assert node.type_node_current == "pq"

    def test_below_min_clamped_to_pq(self, pu_node):
        node = pu_node(5.0, 10.0, 50.0)
        NR.check_q_limits([node], np.zeros((1, 1), dtype=complex))
        assert node.q_gen == 10.0
        assert node.type_node_current == "pq"

    def test_pq_node_untouched(self, make_node):
        node = make_node("2", "pq", q_gen=7.0)
        NR.check_q_limits([node], np.zeros((1, 1), dtype=complex))
        assert node.q_gen == 7.0
        assert node.type_node_current == "pq"


class TestRun:
    def test_returns_inputs_and_keeps_slack(self, two_bus, params):
        nodes, branches = two_bus
        nodes[1].u_magnitude = 105.0  # неплоский старт, чтобы избежать вырожденного якобиана
        params.max_iterations = 10
        res_nodes, res_branches, res_params = NR.run(nodes, branches, params)
        assert res_nodes is nodes
        assert res_branches is branches
        assert res_params is params
        assert (nodes[0].u_magnitude, nodes[0].u_angle) == (110.0, 0.0)

    def test_max_iterations_one_makes_single_step(self, two_bus):
        nodes, branches = two_bus
        nodes[1].u_magnitude = 105.0
        p = Parameters(accuracy=1e-6, max_iterations=1)
        with patch.object(NR, "_adjust_nodes", wraps=NR._adjust_nodes) as spy:
            with pytest.raises(ConvergenceError):
                NR.run(nodes, branches, p)
        assert spy.call_count == 1

    def test_flat_start_converges(self, two_bus, params):
        nodes, branches = two_bus
        NR.run(nodes, branches, params)
        y = get_conductivity_matrix(nodes, branches)
        assert NR._get_power_imbalance(nodes, y)[1] == pytest.approx(0j, abs=1e-4)

    def test_converges_to_operating_root(self, two_bus, params):
        nodes, branches = two_bus
        nodes[1].u_magnitude = 105.0
        NR.run(nodes, branches, params)
        assert nodes[1].u_magnitude == pytest.approx(U2_ANALYTIC, abs=0.01)
        assert nodes[1].u_angle % (2 * math.pi) == pytest.approx(DELTA2_ANALYTIC % (2 * math.pi), abs=1e-3)
