import math
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.model.load import Load


class Node(BaseModel):
    """
    Класс узла электрической сети

    Args:
        node_name (str): уникальное наименование узла
        type_node ("pq", "pu", "slack"): вид узла PQ, PU или SLACK
        type_node_current ("pq", "pu", "slack"): текущий вид узла PQ, PU или SLACK
        u_base (int | float): базисное напряжение (номинальное), кВ
        g_shunt (int | float): активная проводимость шунта, См
        b_shunt (int | float): реактивная проводимость шунта, См
        u_magnitude (int | float): модуль заданного напряжения, кВ (для PU/SLACK)
        u_angle (int | float): угол заданного напряжения, рад
        p_gen (int | float): активная мощность генерации, МВА
        q_gen (int | float): реактивная мощность генерации, МВА
        q_min (int | float): минимальный предел реактивной мощности генерации, Мвар
        q_max (int | float): максимальный предел реактивной мощности генерации, Мвар
        loads (list[Load]): список подключенных нагрузок
        u_setpoint (int | float): уставка (заданное неизменяемое) напряжения PU/SLACK узла, кВ
    """

    node_name: str
    type_node: Literal["pq", "pu", "slack"]
    type_node_current: Literal["pq", "pu", "slack"]
    u_base: Literal[6, 10, 20, 35, 110, 220]
    g_shunt: int | float = Field(ge=0, le=1e10)
    b_shunt: int | float = Field(ge=-1e10, le=1e10)
    u_magnitude: int | float = Field(gt=0, le=1e10)
    u_angle: int | float = Field(ge=0, lt=2 * math.pi)
    p_gen: int | float = Field(ge=0, le=1e10)
    q_gen: int | float = Field(ge=0, le=1e10)
    q_min: int | float = Field(ge=0, le=1e10)
    q_max: int | float = Field(ge=0, le=1e10)
    loads: list[Load] = Field(default_factory=list)
    u_setpoint: int | float = Field(gt=0, le=1e10)

    @property
    def y_shunt(self) -> complex:
        """Проводимость шунта в комплексном виде"""
        return complex(self.g_shunt, self.b_shunt)

    @property
    def u(self) -> complex:
        """Напряжение в узле в комплексном виде"""
        return complex(self.u_magnitude * math.cos(self.u_angle), self.u_magnitude * math.sin(self.u_angle))

    @property
    def power_load(self) -> complex:
        """Получить фактическую мощность узла (нагрузку)"""
        power = complex(0, 0)
        if isinstance(self.loads, list):
            for pl in self.loads:
                power += pl.power_load(self.u_magnitude)
        return power

    @property
    def power_gen(self) -> complex:
        """Получить фактическую мощность узла, учитывая генерацию и нагрузку"""
        return complex(-self.p_gen, -self.q_gen)

    @model_validator(mode="before")
    @classmethod
    def _init_u_setpoint(cls, data: Any) -> Any:
        """Если уставка не задана явно, принять за нее начальное u_magnitude"""
        if isinstance(data, dict) and data.get("u_setpoint") is None:
            return {**data, "u_setpoint": data.get("u_magnitude")}
        return data
