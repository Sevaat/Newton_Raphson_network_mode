import logging
import math
from abc import ABC
from typing import Any

import numpy

from src.model.conductivity_matrix import get_conductivity_matrix
from src.model.load import Load
from src.model.node import Node
from src.model.parameters import Parameters

logger = logging.getLogger(__name__)


class ConvergenceError(RuntimeError):
    """Расчет установившегося режима не сошелся или разошелся."""


class NewtonRaphsonMethod(ABC):
    """Класс для реализации метода Ньютона-Рафсона для итерационного расчета электрической сети"""

    @staticmethod
    def _get_power_imbalance(nodes: list[Node], conductivity_matrix: numpy.ndarray) -> list[complex]:
        """Получить величины небалансов мощности в узлах

        Args:
            nodes (list[Node]): список узлов электрической сети
            conductivity_matrix (numpy.ndarray): матрица собственных и взаимных проводимостей сети

        Returns:
            list[complex]: список небалансов мощности в узлах
        """

        d_power: list[complex] = []
        for i in range(len(nodes)):
            s_i = None
            if nodes[i].type_node == "slack":
                s_i = complex(0, 0)
            else:
                s_i = nodes[i].power_load + nodes[i].power_gen
            ds = complex(0, 0)
            for j in range(len(nodes)):
                ds += conductivity_matrix[i, j].conjugate() * nodes[j].u.conjugate()
            ds = s_i + nodes[i].u * ds
            d_power.append(ds)

        return d_power

    @staticmethod
    def _mismatch_norm(nodes: list[Node], d_power: list[complex]) -> float:
        """
        Максимальный небаланс по проверяемым уравнениям: P — кроме slack, Q — кроме slack и текущих PU

        Args:
            nodes (list[Node]): список узлов электрической сети
            d_power (list[complex]): список небалансов мощности в узлах

        Returns:
            float: максимальный небаланс по проверяемым уравнениям
        """
        values = [abs(d_power[i].real) for i in NewtonRaphsonMethod._angle_indices(nodes)]
        values += [abs(d_power[i].imag) for i in NewtonRaphsonMethod._magnitude_indices(nodes)]
        return max(values, default=0.0)

    @staticmethod
    def _unbalance_condition(nodes: list[Node], parameters: Parameters, d_power: list[complex]) -> bool:
        """Проверить достигнута ли заданная точность расчета

        Args:
            nodes (list[Node]): список узлов электрической сети
            parameters (Parameters): параметры расчета электрической сети
            d_power (list[complex]): список небалансов мощности в узлах

        Returns:
            bool: True, если точность достигнута, False в противном случае
        """
        return NewtonRaphsonMethod._mismatch_norm(nodes, d_power) <= parameters.accuracy

    @staticmethod
    def _get_h_matrix(nodes: list[Node], conductivity_matrix: numpy.ndarray) -> numpy.ndarray:
        """Формирование блока H = ∂P/∂δ матрицы Якоби в полярных координатах

        Args:
            nodes (list[Node]): список узлов электрической сети
            conductivity_matrix (numpy.ndarray): матрица собственных и взаимных проводимостей сети

        Returns:
            numpy.ndarray: блок H = ∂P/∂δ матрицы Якоби в полярных координатах
        """
        # индексы узлов, для которых δ является неизвестной (все, кроме Slack)
        unknown_indices = [i for i, node in enumerate(nodes) if node.type_node != "slack"]

        u_magnitude = numpy.array([node.u_magnitude for node in nodes])
        u_angle = numpy.array([node.u_angle for node in nodes])
        g_nic = numpy.real(conductivity_matrix)
        b_nic = numpy.imag(conductivity_matrix)

        h = numpy.zeros((len(unknown_indices), len(unknown_indices)), dtype=float)

        for n_i, i in enumerate(unknown_indices):
            for n_j, j in enumerate(unknown_indices):
                value = 0
                if i == j:
                    for k in range(len(nodes)):
                        value_under_the_sum = 0
                        if k != i:
                            value_under_the_sum += g_nic[i, k] * math.sin(u_angle[k] - u_angle[i])
                            value_under_the_sum += b_nic[i, k] * math.cos(u_angle[i] - u_angle[k])
                            value_under_the_sum *= u_magnitude[k]
                            value += value_under_the_sum
                    value *= u_magnitude[i]
                else:
                    value = g_nic[i, j] * math.sin(u_angle[i] - u_angle[j])
                    value -= b_nic[i, j] * math.cos(u_angle[i] - u_angle[j])
                    value *= u_magnitude[i] * u_magnitude[j]
                h[n_i, n_j] = value

        return h

    @staticmethod
    def _get_p_q_load_derivative(node: Node, p_q: str) -> float:
        """Получить производную по напряжению активной или реактивной мощности нагрузки в узле

        Args:
            node (Node): узел электрической сети
            p_q (str): тип мощности ("P" для активной, "Q" для реактивной)

        Returns:
            float: производная по напряжению активной или реактивной мощности нагрузки в узле
        """
        if p_q == "P":
            p_load_derivative = 0.0
            if node.loads is None:
                raise ValueError(
                    "Узел не содержит нагрузок, для которых можно было бы посчитать производную по напряжению."
                )
            for load in node.loads:
                if not isinstance(load, Load):
                    raise TypeError("Элементы списка нагрузок должны быть экземплярами класса Load.")
                if (
                    not isinstance(load.p_0, (int, float))
                    or not isinstance(load.u_0, (int, float))
                    or not isinstance(load.z_p, (int, float))
                    or not isinstance(load.i_p, (int, float))
                    or not isinstance(node.u_magnitude, (int, float))
                ):
                    raise TypeError("Параметры модели ZIP должны быть числовыми значениями.")
                p_load_derivative += load.p_0 * (load.z_p / load.u_0**2 * 2 * node.u_magnitude + load.i_p / load.u_0)

            return p_load_derivative

        elif p_q == "Q":
            q_load_derivative = 0.0
            if node.loads is None:
                raise ValueError(
                    "Узел не содержит нагрузок, для которых можно было бы посчитать производную по напряжению."
                )
            for load in node.loads:
                if not isinstance(load, Load):
                    raise TypeError("Элементы списка нагрузок должны быть экземплярами класса Load.")
                if (
                    not isinstance(load.q_0, (int, float))
                    or not isinstance(load.u_0, (int, float))
                    or not isinstance(load.z_q, (int, float))
                    or not isinstance(load.i_q, (int, float))
                    or not isinstance(node.u_magnitude, (int, float))
                ):
                    raise TypeError("Параметры модели ZIP должны быть числовыми значениями.")
                q_load_derivative += load.q_0 * (load.z_q / load.u_0**2 * 2 * node.u_magnitude + load.i_q / load.u_0)

            return q_load_derivative
        else:
            raise ValueError("Тип мощности должен быть 'P' для активной или 'Q' для реактивной.")

    @staticmethod
    def _get_n_matrix(nodes: list[Node], conductivity_matrix: numpy.ndarray) -> numpy.ndarray:
        """Формирование блока N = ∂P/∂V матрицы Якоби в полярных координатах

        Args:
            nodes (list[Node]): список узлов электрической сети
            conductivity_matrix (numpy.ndarray): матрица собственных и взаимных проводимостей сети

        Returns:
            numpy.ndarray: блок N = ∂P/∂V матрицы Якоби в полярных координатах
        """
        # индексы узлов, для которых V является неизвестной (все, кроме SLACK и PU)
        unknown_indices_1 = [i for i, node in enumerate(nodes) if node.type_node != "slack"]
        unknown_indices_2 = [
            i for i, node in enumerate(nodes) if node.type_node != "slack" and node.type_node_current != "pu"
        ]

        u_magnitude = numpy.array([node.u_magnitude for node in nodes])
        u_angle = numpy.array([node.u_angle for node in nodes])
        g_nic = numpy.real(conductivity_matrix)
        b_nic = numpy.imag(conductivity_matrix)

        n_matrix = numpy.zeros((len(unknown_indices_1), len(unknown_indices_2)), dtype=float)

        for n_i, i in enumerate(unknown_indices_1):
            for n_j, j in enumerate(unknown_indices_2):
                value = 0.0
                if i == j:
                    for k in range(len(nodes)):
                        value_under_the_sum = 0.0
                        if k != i:
                            value_under_the_sum += g_nic[i, k] * math.cos(u_angle[i] - u_angle[k])
                            value_under_the_sum += b_nic[i, k] * math.sin(u_angle[i] - u_angle[k])
                            value_under_the_sum *= u_magnitude[k]
                            value += value_under_the_sum
                    value += 2 * g_nic[i, i] * u_magnitude[i]
                    value += NewtonRaphsonMethod._get_p_q_load_derivative(nodes[i], "P")
                else:
                    value = g_nic[i, j] * math.cos(u_angle[i] - u_angle[j])
                    value += b_nic[i, j] * math.sin(u_angle[i] - u_angle[j])
                    value *= u_magnitude[i]
                n_matrix[n_i, n_j] = value

        return n_matrix

    @staticmethod
    def _get_m_matrix(nodes: list[Node], conductivity_matrix: numpy.ndarray) -> numpy.ndarray:
        """Формирование блока M = ∂Q/∂δ матрицы Якоби в полярных координатах

        Args:
            nodes (list[Node]): список узлов электрической сети
            conductivity_matrix (numpy.ndarray): матрица собственных и взаимных проводимостей сети

        Returns:
            numpy.ndarray: блок M = ∂Q/∂δ матрицы Якоби в полярных координатах
        """
        # индексы узлов, для которых δ является неизвестной (все, кроме SLACK)
        unknown_indices_1 = [
            i for i, node in enumerate(nodes) if node.type_node != "slack" and node.type_node_current != "pu"
        ]
        unknown_indices_2 = [i for i, node in enumerate(nodes) if node.type_node != "slack"]

        u_magnitude = numpy.array([node.u_magnitude for node in nodes])
        u_angle = numpy.array([node.u_angle for node in nodes])
        g_nic = numpy.real(conductivity_matrix)
        b_nic = numpy.imag(conductivity_matrix)

        m_matrix = numpy.zeros((len(unknown_indices_1), len(unknown_indices_2)), dtype=float)

        for n_i, i in enumerate(unknown_indices_1):
            for n_j, j in enumerate(unknown_indices_2):
                value = 0.0
                if i == j:
                    for k in range(len(nodes)):
                        value_under_the_sum = 0.0
                        if k != i:
                            value_under_the_sum += g_nic[i, k] * math.cos(u_angle[i] - u_angle[k])
                            value_under_the_sum -= b_nic[i, k] * math.sin(u_angle[k] - u_angle[i])
                            value_under_the_sum *= u_magnitude[k]
                            value += value_under_the_sum
                    value *= u_magnitude[i]
                else:
                    value = -g_nic[i, j] * math.cos(u_angle[i] - u_angle[j])
                    value -= b_nic[i, j] * math.sin(u_angle[i] - u_angle[j])
                    value *= u_magnitude[i] * u_magnitude[j]
                m_matrix[n_i, n_j] = value

        return m_matrix

    @staticmethod
    def _get_l_matrix(nodes: list[Node], conductivity_matrix: numpy.ndarray) -> numpy.ndarray:
        """Формирование блока L = ∂Q/∂V матрицы Якоби в полярных координатах

        Args:
            nodes (list[Node]): список узлов электрической сети
            conductivity_matrix (numpy.ndarray): матрица собственных и взаимных проводимостей сети

        Returns:
            numpy.ndarray: блок L = ∂Q/∂V матрицы Якоби в полярных координатах
        """
        # индексы узлов, для которых V является неизвестной (все, кроме SLACK и PU)
        unknown_indices = [
            i for i, node in enumerate(nodes) if node.type_node != "slack" and node.type_node_current != "pu"
        ]

        u_magnitude = numpy.array([node.u_magnitude for node in nodes])
        u_angle = numpy.array([node.u_angle for node in nodes])
        g_nic = numpy.real(conductivity_matrix)
        b_nic = numpy.imag(conductivity_matrix)

        l_matrix = numpy.zeros((len(unknown_indices), len(unknown_indices)), dtype=float)

        for n_i, i in enumerate(unknown_indices):
            for n_j, j in enumerate(unknown_indices):
                value = 0.0
                if i == j:
                    for k in range(len(nodes)):
                        value_under_the_sum = 0.0
                        if k != i:
                            value_under_the_sum += g_nic[i, k] * math.sin(u_angle[i] - u_angle[k])
                            value_under_the_sum -= b_nic[i, k] * math.cos(u_angle[i] - u_angle[k])
                            value_under_the_sum *= u_magnitude[k]
                            value += value_under_the_sum
                    value -= 2 * b_nic[i, i] * u_magnitude[i]
                    value += NewtonRaphsonMethod._get_p_q_load_derivative(nodes[i], "Q")
                else:
                    value = g_nic[i, j] * math.sin(u_angle[i] - u_angle[j])
                    value -= b_nic[i, j] * math.cos(u_angle[i] - u_angle[j])
                    value *= u_magnitude[i]
                l_matrix[n_i, n_j] = value

        return l_matrix

    @staticmethod
    def _get_jacobian_matrix(nodes: list[Node], conductivity_matrix: numpy.ndarray) -> numpy.ndarray:
        """Формирование полной матрицы Якоби в полярных координатах

        Args:
            nodes (list[Node]): список узлов электрической сети
            conductivity_matrix (numpy.ndarray): матрица собственных и взаимных проводимостей сети

        Returns:
            numpy.ndarray: полная матрица Якоби в полярных координатах
        """
        h_matrix = NewtonRaphsonMethod._get_h_matrix(nodes, conductivity_matrix)
        n_matrix = NewtonRaphsonMethod._get_n_matrix(nodes, conductivity_matrix)
        m_matrix = NewtonRaphsonMethod._get_m_matrix(nodes, conductivity_matrix)
        l_matrix = NewtonRaphsonMethod._get_l_matrix(nodes, conductivity_matrix)

        jacobian = numpy.block([[h_matrix, n_matrix], [m_matrix, l_matrix]])

        return jacobian

    @staticmethod
    def _angle_indices(nodes: list[Node]) -> list[int]:
        """
        Индексы узлов с неизвестным углом (все, кроме slack)

        Args:
            nodes (list[Node]): список узлов электрической сети

        Returns:
            list[int]: номера узлов, не являющиеся slack
        """
        return [i for i, node in enumerate(nodes) if node.type_node != "slack"]

    @staticmethod
    def _magnitude_indices(nodes: list[Node]) -> list[int]:
        """
        Индексы узлов с неизвестным модулем (кроме slack и текущих PU)

        Args:
            nodes (list[Node]): список узлов электрической сети

        Returns:
            list[int]: номера узлов, не являющиеся slack и pu
        """
        return [i for i, node in enumerate(nodes) if node.type_node != "slack" and node.type_node_current != "pu"]

    @staticmethod
    def _get_adjustments(nodes: list[Node], d_power: list[complex], jacobian: numpy.ndarray) -> numpy.ndarray:
        """
        Получить поправки в блочном порядке [Δδ…, ΔV…], соответствующем якобиану [[H,N],[M,L]]

        Args:
            nodes (list[Node]): список узлов электрической сети
            d_power (list[complex]): список небалансов мощности в узлах
            jacobian (numpy.ndarray): полная матрица Якоби в полярных координатах

        Returns:
            numpy.ndarray: массив корректировок по углу и модулю напряжения в узлах
        """
        idx_angle = NewtonRaphsonMethod._angle_indices(nodes)
        idx_mag = NewtonRaphsonMethod._magnitude_indices(nodes)
        rhs = numpy.array([-d_power[i].real for i in idx_angle] + [-d_power[i].imag for i in idx_mag])
        try:
            return numpy.linalg.solve(jacobian, rhs)
        except numpy.linalg.LinAlgError as e:
            raise ArithmeticError("Якобиан вырожден: проверьте исходные данные сети.") from e

    @staticmethod
    def _adjust_nodes(nodes: list[Node], adjustments: numpy.ndarray) -> list[Node]:
        """
        Скорректировать узлы; порядок поправок совпадает с _get_adjustments

        Args:
            nodes (list[Node]): список узлов электрической сети
            adjustments (numpy.ndarray): массив корректировок по углу и модулю напряжения в узлах

        Returns:
            list[Node]: список скорректированных узлов
        """
        idx_angle = NewtonRaphsonMethod._angle_indices(nodes)
        idx_mag = NewtonRaphsonMethod._magnitude_indices(nodes)
        for k, i in enumerate(idx_angle):
            nodes[i].u_angle = (nodes[i].u_angle + adjustments[k]) % (2 * math.pi)  # держим диапазон [0, 2π)
        offset = len(idx_angle)
        for k, i in enumerate(idx_mag):
            nodes[i].u_magnitude += adjustments[offset + k]
        return nodes

    @staticmethod
    def check_q_limits(nodes: list[Node], conductivity_matrix: numpy.ndarray) -> list[Node]:
        """Контроль лимитов Q PU-узлов; возврат в PU по критерию напряжения с восстановлением уставки

        Args:
            nodes (list[Node]): список узлов электрической сети
            conductivity_matrix (numpy.ndarray): матрица собственных и взаимных проводимостей сети

        Returns:
            list[Node]: список узлов с корректированным состоянием
        """
        u = numpy.array([node.u for node in nodes])
        for i, node in enumerate(nodes):
            if node.type_node != "pu":
                continue
            if node.type_node_current == "pu":
                s_net = node.u * numpy.conj(conductivity_matrix[i, :] @ u)
                q_req = float((node.power_load + s_net).imag)
                if q_req < node.q_min:
                    node.q_gen, node.type_node_current = node.q_min, "pq"
                elif q_req > node.q_max:
                    node.q_gen, node.type_node_current = node.q_max, "pq"
                else:
                    node.q_gen = q_req
            else:
                # возврат, только если уставка напряжения «разгружает» лимит
                if (node.q_gen >= node.q_max and node.u_magnitude >= node.u_setpoint) or (
                    node.q_gen <= node.q_min and node.u_magnitude <= node.u_setpoint
                ):
                    node.u_magnitude = node.u_setpoint
                    node.type_node_current = "pu"
        return nodes

    @staticmethod
    def run(
        nodes: list[Node], branches: list[Any], parameters: Parameters
    ) -> tuple[list[Node], list[Any], Parameters]:
        """Проводить расчет установившегося режима электрической сети методом Ньютона-Рафсона

        Args:
            nodes (list[Node]): список узлов электрической сети
            branches (list[Any]): список ветвей электрической сети
            parameters (dict[str, Any]): параметры расчета электрической сети

        Returns:
            tuple[list[Node], list[Any], Parameters]: скорректированные узлы, ветви и параметры расчета
        """
        conductivity_matrix = get_conductivity_matrix(nodes, branches)
        initial_norm: float | None = None
        norm = math.inf  # на случай пустого цикла; в else-ветке уйдет в сообщение ConvergenceError
        for iteration in range(parameters.max_iterations):
            nodes = NewtonRaphsonMethod.check_q_limits(nodes, conductivity_matrix)
            d_power = NewtonRaphsonMethod._get_power_imbalance(nodes, conductivity_matrix)
            norm = NewtonRaphsonMethod._mismatch_norm(nodes, d_power)
            if norm <= parameters.accuracy:
                logger.info("Точность достигнута на итерации №%d (|ΔS|max=%.3g)", iteration, norm)
                break
            if initial_norm is None:
                initial_norm = norm
            if not math.isfinite(norm) or norm > 1e6 * initial_norm:
                raise ConvergenceError(f"Расходимость на итерации №{iteration}: |ΔS|max={norm:.3g}")
            jacobian = NewtonRaphsonMethod._get_jacobian_matrix(nodes, conductivity_matrix)
            adjustments = NewtonRaphsonMethod._get_adjustments(nodes, d_power, jacobian)
            nodes = NewtonRaphsonMethod._adjust_nodes(nodes, parameters.damping * adjustments)
            for node in nodes:
                if not math.isfinite(node.u_magnitude) or node.u_magnitude <= 0:
                    raise ConvergenceError(
                        f"Недопустимое напряжение узла '{node.node_name}': {node.u_magnitude:.3g} кВ"
                    )
        else:
            raise ConvergenceError(f"""Точность {parameters.accuracy} не достигнута
                за {parameters.max_iterations} итераций (|ΔS|max={norm:.3g})""")
        for node in nodes:
            if node.type_node != "slack" and node.u_magnitude < 0.7 * node.u_setpoint:
                logger.warning("Подозрительно низкое напряжение узла '%s': %.3g кВ", node.node_name, node.u_magnitude)
        return nodes, branches, parameters
