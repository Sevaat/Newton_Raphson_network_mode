from typing import Self

from pydantic import BaseModel, Field, model_validator

from src.model.node import Node


class Branch(BaseModel):
    """
    Класс ветви

    Args:
        branch_name (str): уникальное наименование ветви
        node_1 (Node): узел начала ветви
        node_2 (Node): узел конца ветви
        r_1 (float): акт. сопр. продольной части ветви, Ом
        x_1 (float): реакт. сопр. продольной части ветви, Ом
        g_shunt (float): активная проводимость поперечной части ветви, См
        b_shunt (float): реактивная проводимость поперечной части ветви, См
    """

    branch_name: str
    node_1: Node
    node_2: Node
    r_1: float = Field(ge=0, le=1e10)
    x_1: float = Field(ge=-1e10, le=1e10)
    g_shunt: float = Field(ge=0, le=1e10)
    b_shunt: float = Field(ge=-1e10, le=1e10)

    def _z(self, r: float, x: float) -> complex:
        if r == 0 and x == 0:
            raise ValueError("r и x не могут быть нулями одновременно")
        return complex(r, x)

    @property
    def z_1(self) -> complex:
        """Сопротивление ветви в комплексном виде"""
        return self._z(self.r_1, self.x_1)

    @property
    def y_shunt(self) -> complex:
        """Проводимость шунта в комплексном виде"""
        return complex(self.g_shunt, self.b_shunt)

    @model_validator(mode="after")
    def check_nodes(self) -> Self:
        """Проверка, что узлы начала и конца разные"""
        if self.node_1.node_name == self.node_2.node_name:
            raise ValueError(
                f"Узлы начала и конца должны быть разными: {self.node_1.node_name}, {self.node_2.node_name}"
            )
        return self


class Line(Branch):
    """
    Класс ветви - линии электропередачи
    """

    pass


class Transformer2(Branch):
    """
    Класс ветви - двухобмоточный трансформатор

    Args:
        u_1 (float): номинальное напряжение на узле 1, кВ
        u_2 (float): номинальное напряжение на узле 2, кВ
    """

    u_1: float = Field(gt=0, le=1e10)
    u_2: float = Field(gt=0, le=1e10)

    @property
    def k_12(self) -> float:
        """Коэффициент трансформации между узлами 1 и 2 для трансформатора"""
        return self.u_1 / self.u_2


class Transformer3(Transformer2):
    """
    Класс ветви - трехобмоточный трансформатор (автотрансформатор)

    Args:
        node_3 (Node): узел низшей обмотки t3
        r_2 (float): активное сопротивление средней обмотки t3, Ом
        x_2 (float): реактивное сопротивление средней обмотки t3, Ом
        r_3 (float): активное сопротивление низшей обмотки t3, Ом
        x_3 (float): реактивное сопротивление низшей обмотки t3, Ом
        u_3 (float): номинальное напряжение на узле 3, кВ
    """

    node_3: Node
    r_2: float = Field(ge=0, le=1e10)
    x_2: float = Field(ge=-1e10, le=1e10)
    r_3: float = Field(ge=0, le=1e10)
    x_3: float = Field(ge=-1e10, le=1e10)
    u_3: float = Field(gt=0, le=1e10, default=1)

    @model_validator(mode="after")
    def check_nodes(self) -> Self:
        """Проверка, что узлы 1, 2, 3 разные"""
        if (
            self.node_1.node_name == self.node_2.node_name
            or self.node_1.node_name == self.node_3.node_name
            or self.node_2.node_name == self.node_3.node_name
        ):
            raise ValueError(
                f"Узлы должны быть разными: {self.node_1.node_name}, {self.node_2.node_name}, {self.node_3.node_name}"
            )
        return self

    @property
    def z_2(self) -> complex:
        """Сопротивление ветви среднего напряжения трансформатора в комплексном виде"""
        return self._z(self.r_2, self.x_2)

    @property
    def z_3(self) -> complex:
        """Сопротивление ветви низшего напряжения трансформатора в комплексном виде"""
        return self._z(self.r_3, self.x_3)

    @property
    def k_13(self) -> float:
        """Коэффициент трансформации между узлами 1 и 3 для трансформатора"""
        return self.u_1 / self.u_3
