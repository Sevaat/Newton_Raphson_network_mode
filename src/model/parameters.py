from pydantic import BaseModel, Field


class Parameters(BaseModel):
    """
    Класс представляющий параметры расчета

    Args:
        accuracy (int | float): точность расчета
        iterations (int): количество итераций
    """

    accuracy: int | float = Field(gt=0, le=1000000)
    max_iterations: int = Field(gt=0, le=1000000)
