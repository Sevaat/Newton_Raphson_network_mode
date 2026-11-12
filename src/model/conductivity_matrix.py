from typing import Any

import numpy as np

from src.model.branch import Line, Transformer2, Transformer3
from src.model.node import Node


def get_conductivity_matrix(nodes: list[Node], branches: list[Any]) -> np.ndarray:
    """Получить матрицу собственных и взаимных проводимостей с учетом вида линии

    Args:
        nodes (list[Node]): список узлов
        branches (list[Any]): список ветвей (ЛЭП, двух- и трехобмоточные трансформаторы)

    Returns:
        conductivity_matrix (np.ndarray): матрица собственных и взаимных проводимостей
    """
    lines = []
    transformers_2 = []
    transformers_3 = []

    for branch in branches:
        if isinstance(branch, Line):
            lines.append(branch)
        if isinstance(branch, Transformer2) and not isinstance(branch, Transformer3):
            transformers_2.append(branch)
        if isinstance(branch, Transformer3):
            transformers_3.append(branch)

    conductivity_matrix: np.ndarray = np.zeros((len(nodes), len(nodes)), dtype=complex)

    for i, node in enumerate(nodes):
        conductivity_matrix[i, i] += node.y_shunt

    for line in lines:
        i = nodes.index(line.node_1)
        j = nodes.index(line.node_2)
        # проводимость линии электропередачи (поперечная ветвь), обычно B>0
        y0 = line.y_shunt
        y = 1 / line.z_1
        conductivity_matrix[i, j] += -y
        conductivity_matrix[j, i] += -y
        conductivity_matrix[i, i] += y + y0 / 2
        conductivity_matrix[j, j] += y + y0 / 2

    for tr_2 in transformers_2:
        i = nodes.index(tr_2.node_1)
        j = nodes.index(tr_2.node_2)
        # проводимость трансформатора с двумя обмотками (поперечная ветвь), обычно B<0
        y0 = tr_2.y_shunt
        y = 1 / tr_2.z_1
        k = tr_2.k_12
        conductivity_matrix[i, j] += -y * k
        conductivity_matrix[j, i] += -y * k
        conductivity_matrix[i, i] += y + y0
        conductivity_matrix[j, j] += k**2 * y

    for tr_3 in transformers_3:
        # избавление от нулевого узла (среднего узла) трансформатора происходит путем преобразования Y -> Δ
        # проводимость трансформатора с тремя обмотками (поперечная ветвь), обычно B<0
        y0 = tr_3.y_shunt

        z_h = tr_3.z_1
        z_m = tr_3.z_2
        z_l = tr_3.z_3

        z = z_h * z_m + z_h * z_l + z_m * z_l

        k_hm = tr_3.k_12
        k_hl = tr_3.k_13

        y_ii = 1 / z_h - z_m * z_l / (z * z_h)
        y_jj = k_hm**2 / z_m - z_h * z_l * k_hm**2 / (z * z_m)
        y_kk = k_hl**2 / z_l - z_h * z_m * k_hl**2 / (z * z_l)

        y_ij_ji = -z_l * k_hm / z
        y_ik_ki = -z_m * k_hl / z
        y_jk_kj = -z_h * k_hm * k_hl / z

        i = nodes.index(tr_3.node_1)
        j = nodes.index(tr_3.node_2)
        k = nodes.index(tr_3.node_3)

        conductivity_matrix[i, i] += y_ii + y0
        conductivity_matrix[j, j] += y_jj
        conductivity_matrix[k, k] += y_kk

        conductivity_matrix[i, j] += y_ij_ji
        conductivity_matrix[j, i] += y_ij_ji
        conductivity_matrix[i, k] += y_ik_ki
        conductivity_matrix[k, i] += y_ik_ki
        conductivity_matrix[j, k] += y_jk_kj
        conductivity_matrix[k, j] += y_jk_kj

    return conductivity_matrix
