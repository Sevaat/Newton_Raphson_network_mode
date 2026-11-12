import numpy as np
import pytest

from src.model.branch import Line, Transformer2, Transformer3
from src.model.conductivity_matrix import get_conductivity_matrix


class TestBasic:
    def test_shape_and_dtype(self, two_bus):
        nodes, branches = two_bus
        y = get_conductivity_matrix(nodes, branches)
        assert y.shape == (2, 2)
        assert y.dtype == complex

    def test_no_branches_only_node_shunts(self, make_node):
        nodes = [make_node("1", g_shunt=1e-6, b_shunt=5e-6), make_node("2")]
        y = get_conductivity_matrix(nodes, [])
        assert y[0, 0] == complex(1e-6, 5e-6)
        assert y[1, 1] == 0j
        assert y[0, 1] == y[1, 0] == 0j

    def test_two_bus_line_exact(self, two_bus):
        nodes, branches = two_bus
        y = 1 / complex(10, 40)
        expected = np.array([[y, -y], [-y, y]])
        assert get_conductivity_matrix(nodes, branches) == pytest.approx(expected)

    def test_line_shunt_halved(self, two_bus):
        nodes, branches = two_bus
        branches[0].g_shunt, branches[0].b_shunt = 1e-6, 4e-5
        y = get_conductivity_matrix(nodes, branches)
        ys = 1 / complex(10, 40)
        y0_half = complex(1e-6, 4e-5) / 2
        assert y[0, 0] == pytest.approx(ys + y0_half)
        assert y[1, 1] == pytest.approx(ys + y0_half)
        assert y[0, 1] == pytest.approx(-ys)

    def test_parallel_lines_add_up(self, two_bus):
        nodes, branches = two_bus
        line2 = Line(branch_name="L2", node_1=nodes[0], node_2=nodes[1],
                     r_1=10.0, x_1=40.0, g_shunt=0.0, b_shunt=0.0)
        y_single = get_conductivity_matrix(nodes, branches)
        y_double = get_conductivity_matrix(nodes, branches + [line2])
        assert y_double == pytest.approx(2 * y_single)

    def test_symmetry(self, two_bus):
        nodes, branches = two_bus
        y = get_conductivity_matrix(nodes, branches)
        assert y == pytest.approx(y.T)

    def test_node_order_respected(self, two_bus):
        nodes, branches = two_bus
        y = get_conductivity_matrix(nodes, branches)
        y_rev = get_conductivity_matrix(nodes[::-1], branches)
        assert y_rev == pytest.approx(y[::-1, ::-1])


class TestTransformer2:
    @pytest.fixture
    def t2_case(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2")]
        t2 = Transformer2(branch_name="T2", node_1=nodes[0], node_2=nodes[1],
                          r_1=2.0, x_1=30.0, g_shunt=1e-6, b_shunt=-2e-5,
                          u_1=110.0, u_2=35.0)
        return nodes, t2

    def test_entries(self, t2_case):
        nodes, t2 = t2_case
        y = get_conductivity_matrix(nodes, [t2])
        ys, k, y0 = 1 / complex(2, 30), 110 / 35, complex(1e-6, -2e-5)
        assert y[0, 0] == pytest.approx(ys + y0)
        assert y[1, 1] == pytest.approx(k**2 * ys)
        assert y[0, 1] == pytest.approx(-ys * k)
        assert y[1, 0] == pytest.approx(-ys * k)

    def test_unit_ratio_equals_line(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2")]
        common = dict(node_1=nodes[0], node_2=nodes[1], r_1=2.0, x_1=30.0, g_shunt=0.0, b_shunt=0.0)
        line = Line(branch_name="L", **common)
        t2 = Transformer2(branch_name="T2", u_1=110.0, u_2=110.0, **common)
        assert get_conductivity_matrix(nodes, [t2]) == pytest.approx(get_conductivity_matrix(nodes, [line]))


class TestTransformer3:
    def test_matches_kron_reduction(self, make_node):
        """Независимая проверка: исключение нейтрали звезды (редукция Крона) из 4x4-матрицы."""
        nodes = [make_node("1", "slack"), make_node("2"), make_node("3")]
        t3 = Transformer3(branch_name="T3", node_1=nodes[0], node_2=nodes[1], node_3=nodes[2],
                          r_1=1.0, x_1=20.0, r_2=0.5, x_2=12.0, r_3=0.3, x_3=6.0,
                          g_shunt=0.0, b_shunt=0.0, u_1=110.0, u_2=35.0, u_3=10.0)
        yh, ym, yl = 1 / t3.z_1, 1 / t3.z_2, 1 / t3.z_3
        k1, k2 = t3.k_12, t3.k_13
        y4 = np.zeros((4, 4), dtype=complex)  # узлы 1, 2, 3 + нейтраль n
        y4[0, 0] = yh; y4[0, 3] = y4[3, 0] = -yh
        y4[1, 1] = k1**2 * ym; y4[1, 3] = y4[3, 1] = -k1 * ym
        y4[2, 2] = k2**2 * yl; y4[2, 3] = y4[3, 2] = -k2 * yl
        y4[3, 3] = yh + ym + yl
        y_kron = y4[:3, :3] - np.outer(y4[:3, 3], y4[3, :3]) / y4[3, 3]
        assert get_conductivity_matrix(nodes, [t3]) == pytest.approx(y_kron)
