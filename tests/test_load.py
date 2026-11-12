import pytest
from pydantic import ValidationError

from src.model.load import Load


class TestLoadPower:
    def test_nominal_voltage_returns_nominal_power(self, make_load):
        ld = make_load(z_p=0.3, i_p=0.3, p_p=0.4, z_q=0.2, i_q=0.5, p_q=0.3)
        assert ld.power_load(110.0) == pytest.approx(complex(20.0, 10.0))

    def test_constant_power_independent_of_voltage(self, make_load):
        ld = make_load()  # p_p = p_q = 1
        assert ld.power_load(80.0) == pytest.approx(complex(20, 10))
        assert ld.power_load(130.0) == pytest.approx(complex(20, 10))

    def test_constant_impedance_scales_quadratically(self, make_load):
        ld = make_load(z_p=1.0, p_p=0.0, z_q=1.0, p_q=0.0)
        assert ld.power_load(220.0) == pytest.approx(complex(80, 40))

    def test_constant_current_scales_linearly(self, make_load):
        ld = make_load(i_p=1.0, p_p=0.0, i_q=1.0, p_q=0.0)
        assert ld.power_load(55.0) == pytest.approx(complex(10, 5))

    def test_mixed_zip_at_overvoltage(self, make_load):
        ld = make_load(p_0=100.0, q_0=50.0, z_p=0.3, i_p=0.3, p_p=0.4,
                       z_q=0.2, i_q=0.5, p_q=0.3)
        k = 1.1
        p = 100.0 * (0.3 * k**2 + 0.3 * k + 0.4)
        q = 50.0 * (0.2 * k**2 + 0.5 * k + 0.3)
        assert ld.power_load(121.0) == pytest.approx(complex(p, q))

    def test_zero_nominal_power_gives_zero(self, make_load):
        ld = make_load(p_0=0.0, q_0=0.0)  # коэффициенты валидны: p_p = p_q = 1
        assert ld.power_load(110.0) == 0j

    def test_zip_coefficients_must_sum_to_one(self, make_load):
        with pytest.raises(ValidationError, match="z_p"):
            make_load(z_p=0.5, i_p=0.5, p_p=0.5)


class TestLoadValidation:
    def test_missing_fields_raise(self):
        with pytest.raises(ValidationError):
            Load(load_name="bad", p_0=1.0)

    def test_non_numeric_field_raises(self, make_load):
        with pytest.raises(ValidationError):
            make_load(p_0="не число")
