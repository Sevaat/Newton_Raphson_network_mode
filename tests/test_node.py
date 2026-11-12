import math

import pytest
from pydantic import ValidationError


class TestNodeProperties:
    def test_u_complex_from_polar(self, make_node):
        node = make_node(u_magnitude=110.0, u_angle=math.pi / 6)
        assert node.u == pytest.approx(complex(110 * math.cos(math.pi / 6), 55.0))

    def test_u_at_zero_angle_is_real(self, make_node):
        assert make_node().u == pytest.approx(complex(110, 0))

    def test_y_shunt(self, make_node):
        assert make_node(g_shunt=1e-6, b_shunt=-5e-6).y_shunt == complex(1e-6, -5e-6)

    def test_power_load_sums_loads(self, make_node, make_load):
        node = make_node(loads=[make_load("a", p_0=10, q_0=5), make_load("b")])
        assert node.power_load == pytest.approx(complex(30, 15))

    def test_power_load_empty_by_default(self, make_node):
        assert make_node().power_load == 0j

    def test_power_gen_has_negative_sign(self, make_node):
        assert make_node(p_gen=30.0, q_gen=15.0).power_gen == complex(-30.0, -15.0)

    def test_default_loads_not_shared(self, make_node, make_load):
        n1, n2 = make_node("1"), make_node("2")
        n1.loads.append(make_load())
        assert n2.loads == []


class TestNodeValidation:
    @pytest.mark.parametrize("u_base", [6, 10, 20, 35, 110, 220])
    def test_allowed_base_voltages(self, make_node, u_base):
        assert make_node(u_base=u_base).u_base == u_base

    def test_non_standard_base_voltage_now_allowed(self, make_node):
        assert make_node(u_base=15).u_base == 15

    def test_negative_q_limits_allowed(self, make_node):
        node = make_node(q_min=-50.0, q_gen=-10.0)  # недовозбуждение генератора
        assert (node.q_min, node.q_gen) == (-50.0, -10.0)

    def test_wrong_type_node(self, make_node):
        with pytest.raises(ValidationError):
            make_node(type_node="pv")

    @pytest.mark.parametrize("field,value", [
        ("u_magnitude", 0.0), ("u_magnitude", -1.0),
        ("u_angle", -0.1), ("u_angle", 2 * math.pi),
        ("p_gen", -1.0), ("g_shunt", -1.0),
    ])
    def test_field_constraints(self, make_node, field, value):
        with pytest.raises(ValidationError):
            make_node(**{field: value})
