from pydantic import BaseModel, Field


class Parameters(BaseModel):
    """
    Класс представляющий параметры расчета

    Args:
        accuracy (int | float): точность расчета (допустимый максимальный небаланс мощности), МВА
        max_iterations (int): максимальное число итераций
        damping (int | float): коэффициент демпфирования поправок напряжений (0 < damping ≤ 1);
            1.0 — чистый метод Ньютона-Рафсона; 0.3–0.7 — для тяжелых режимов при расходимости
    """

    accuracy: int | float = Field(gt=0, le=1000000)
    max_iterations: int = Field(gt=0, le=1000000)
    damping: int | float = Field(default=1.0, gt=0, le=1)
