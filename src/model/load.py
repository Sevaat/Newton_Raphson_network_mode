import math
from typing import Self

from pydantic import BaseModel, Field, model_validator


class Load(BaseModel):
    """
    Класс нагрузки узла электрической нагрузки

    Args:
        load_name (str): уникальный идентификатор нагрузки
        p_0 (int | float): номинальная активная мощность, МВА
        q_0 (int | float): номинальная реактивная мощность, Мвар (<0 — компенсирующее устройство)
        z_p (int | float): коэффициент z для активной мощности (z_p+i_p+p_p=1)
        i_p (int | float): коэффициент i для активной мощности (z_p+i_p+p_p=1)
        p_p (int | float): коэффициент p для активной мощности (z_p+i_p+p_p=1)
        z_q (int | float): коэффициент z для реактивной мощности (z_q+i_q+p_q=1)
        i_q (int | float): коэффициент i для реактивной мощности (z_q+i_q+p_q=1)
        p_q (int | float): коэффициент p для реактивной мощности (z_q+i_q+p_q=1)
        u_0 (int | float): модуль номинального напряжения нагрузки, кВ
    """

    load_name: str
    p_0: int | float
    q_0: int | float
    z_p: int | float = Field(ge=0, le=1)
    i_p: int | float = Field(ge=0, le=1)
    p_p: int | float = Field(ge=0, le=1)
    z_q: int | float = Field(ge=0, le=1)
    i_q: int | float = Field(ge=0, le=1)
    p_q: int | float = Field(ge=0, le=1)
    u_0: int | float = Field(gt=0, le=1e10)

    def power_load(self, u_node: float) -> complex:
        """Получить фактическую нагрузку при заданном напряжении

        Args:
            u_node (float): заданное напряжение в узле, кВ

        Returns:
            complex: фактическая нагрузка в комплексном виде
        """
        p = self.p_0 * (self.z_p * (u_node / self.u_0) ** 2 + self.i_p * (u_node / self.u_0) + self.p_p)
        q = self.q_0 * (self.z_q * (u_node / self.u_0) ** 2 + self.i_q * (u_node / self.u_0) + self.p_q)
        return complex(p, q)

    @model_validator(mode="after")
    def check_zip_coefficients(self) -> Self:
        """Проверка нормировки ZIP-коэффициентов отдельно для P и Q"""
        if not math.isclose(self.z_p + self.i_p + self.p_p, 1.0, abs_tol=1e-6):
            raise ValueError(f"Нагрузка '{self.load_name}': z_p + i_p + p_p != 1")
        if not math.isclose(self.z_q + self.i_q + self.p_q, 1.0, abs_tol=1e-6):
            raise ValueError(f"Нагрузка '{self.load_name}': z_q + i_q + p_q != 1")
        return self
