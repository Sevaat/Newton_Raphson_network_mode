import pytest
from pydantic import ValidationError

from src.model.branch import Line, Transformer2, Transformer3


@pytest.fixture
def t3(make_node):
    return Transformer3(
        branch_name="T3",
        node_1=make_node("1", "slack"),
        node_2=make_node("2"),
        node_3=make_node("3"),
        r_1=1.0,
        x_1=20.0,
        r_2=0.5,
        x_2=10.0,
        r_3=0.3,
        x_3=5.0,
        g_shunt=0.0,
        b_shunt=0.0,
        u_1=110.0,
        u_2=35.0,
        u_3=10.0,
    )


class TestBranchProperties:
    def test_z_and_y_shunt(self, two_bus):
        line = two_bus[1][0]
        assert line.z_1 == complex(10, 40)
        assert line.y_shunt == 0j

    def test_zero_r_and_x_raise(self, make_node):
        line = Line(
            branch_name="bad", node_1=make_node("1"), node_2=make_node("2"), r_1=0.0, x_1=0.0, g_shunt=0.0, b_shunt=0.0
        )
        with pytest.raises(ValueError, match="нулями"):
            _ = line.z_1

    def test_pure_resistive_line_allowed(self, make_node):
        line = Line(
            branch_name="R", node_1=make_node("1"), node_2=make_node("2"), r_1=5.0, x_1=0.0, g_shunt=0.0, b_shunt=0.0
        )
        assert line.z_1 == complex(5, 0)

    def test_transformer2_ratio(self, make_node):
        t2 = Transformer2(
            branch_name="T2",
            node_1=make_node("1", "slack"),
            node_2=make_node("2"),
            r_1=1.0,
            x_1=20.0,
            g_shunt=0.0,
            b_shunt=0.0,
            u_1=110.0,
            u_2=35.0,
        )
        assert t2.k_12 == pytest.approx(110 / 35)

    def test_transformer3_impedances_and_ratios(self, t3):
        assert t3.z_2 == complex(0.5, 10)
        assert t3.z_3 == complex(0.3, 5)
        assert t3.k_12 == pytest.approx(110 / 35)
        assert t3.k_13 == pytest.approx(11.0)

    def test_transformer3_zero_winding_impedance_raises(self, t3):
        t3.r_2, t3.x_2 = 0.0, 0.0
        with pytest.raises(ValueError):
            _ = t3.z_2

    def test_branch_shares_node_objects(self, two_bus):
        """Ветки должны ссылаться на ТЕ ЖЕ объекты узлов (НР меняет их на месте)."""
        nodes, branches = two_bus
        assert branches[0].node_1 is nodes[0]
        assert branches[0].node_2 is nodes[1]


class TestBranchValidation:
    def test_same_node_objects_rejected(self, make_node):
        n = make_node("1")
        with pytest.raises(ValidationError, match="разными"):
            Line(branch_name="L", node_1=n, node_2=n, r_1=1, x_1=1, g_shunt=0, b_shunt=0)

    def test_same_node_names_rejected(self, make_node):
        with pytest.raises(ValidationError):
            Line(branch_name="L", node_1=make_node("1"), node_2=make_node("1"), r_1=1, x_1=1, g_shunt=0, b_shunt=0)

    def test_transformer3_duplicate_node_rejected(self, make_node):
        with pytest.raises(ValidationError):
            Transformer3(
                branch_name="T3",
                node_1=make_node("1"),
                node_2=make_node("2"),
                node_3=make_node("1"),
                r_1=1,
                x_1=1,
                r_2=1,
                x_2=1,
                r_3=1,
                x_3=1,
                g_shunt=0,
                b_shunt=0,
                u_1=110,
                u_2=35,
                u_3=10,
            )

    def test_negative_resistance_rejected(self, make_node):
        with pytest.raises(ValidationError):
            Line(branch_name="L", node_1=make_node("1"), node_2=make_node("2"), r_1=-1, x_1=1, g_shunt=0, b_shunt=0)

    def test_negative_reactance_allowed(self, make_node):
        line = Line(branch_name="C", node_1=make_node("1"), node_2=make_node("2"), r_1=1, x_1=-5, g_shunt=0, b_shunt=0)
        assert line.z_1 == complex(1, -5)
