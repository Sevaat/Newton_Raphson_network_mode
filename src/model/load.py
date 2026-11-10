from pydantic import BaseModel


class Load(BaseModel):
    """
    Класс нагрузки узла электрической нагрузки

    Args:
        load_name (str): уникальный идентификатор нагрузки
        p_0 (int | float): номинальная активная мощность, МВА
        q_0 (int | float): номинальная реактивная мощность, Мвар
        z_p (int | float): коэффициент z для активной мощности (для p и q справедливо z+i+p=1)
        i_p (int | float): коэффициент i для активной мощности (для p и q справедливо z+i+p=1)
        p_p (int | float): коэффициент p для активной мощности (для p и q справедливо z+i+p=1)
        z_q (int | float): коэффициент z для реактивной мощности (для p и q справедливо z+i+p=1)
        i_q (int | float): коэффициент i для реактивной мощности (для p и q справедливо z+i+p=1)
        p_q (int | float): коэффициент p для реактивной мощности (для p и q справедливо z+i+p=1)
        u_0 (int | float): модуль номинального напряжения нагрузки, кВ
    """

    load_name: str
    p_0: int | float
    q_0: int | float
    z_p: int | float
    i_p: int | float
    p_p: int | float
    z_q: int | float
    i_q: int | float
    p_q: int | float
    u_0: int | float

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
