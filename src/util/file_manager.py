import json
import logging
from abc import ABC
from datetime import datetime
from pathlib import Path
from typing import Any

from src.model.branch import Line, Transformer2, Transformer3
from src.model.load import Load
from src.model.node import Node
from src.model.parameters import Parameters

logger = logging.getLogger(__name__)


class FileManager(ABC):
    """
    Класс работы с файлами
    """

    @staticmethod
    def _load_data(filename: str) -> dict[str, Any]:
        """
        Загрузить данные из JSON

        Args:
            filename (str): имя файла JSON в папке 'data'

        Returns:
            Dict[str, Any]: словарь данных, загруженных из JSON файла

        Raises:
            FileNotFoundError: файл данных не найден
            ValueError: некорректный JSON или корень не является объектом
        """

        filepath = Path(__file__).resolve().parent.parent.parent / "data" / filename
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Файл данных не найден: {filepath}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Ошибка формата JSON в файле {filepath}: {e}") from e
        if not isinstance(data, dict):
            raise TypeError(f"Корень JSON в файле {filepath} должен быть словарем, получено {type(data).__name__}")
        logger.info("Файл данных загружен: %s", filepath)
        return data

    @staticmethod
    def _load_loads(data: dict[str, Any]) -> list[Load]:
        """Загрузить данные нагрузок

        Args:
            data (dict[str, Any]): словарь данных, загруженных из JSON файла

        Returns:
            list[Load]: данные о нагрузках
        """
        if "LOADS" not in data:
            raise KeyError("Ключ 'LOADS' не найден в данных")
        loads_data = data.get("LOADS")
        if not isinstance(loads_data, list):
            raise TypeError(f"""Поле 'LOADS' в словаре данных, загруженных из JSON файла,
                должно быть списком, получено {type(loads_data).__name__}""")

        loads = []
        for load_data in loads_data:
            loads.append(Load.model_validate(load_data))

        # проверка на повторения имен
        load_names = [ld.load_name for ld in loads]
        if len(load_names) != len(set(load_names)):
            raise ValueError("Имеются повторения имен нагрузок")

        return loads

    @staticmethod
    def _load_nodes(data: dict[str, Any], loads: list[Load]) -> list[Node]:
        """Загрузить данные узлов

        Args:
            data (dict[str, Any]): словарь данных, загруженных из JSON файла
            loads (list[Load]): список нагрузок

        Returns:
            list[Node]: данные об узлах
        """
        if "NODES" not in data:
            raise KeyError("Ключ 'NODES' не найден в данных")
        nodes_data = data.get("NODES")
        if not isinstance(nodes_data, list):
            raise TypeError(f"""Поле 'NODES' в словаре данных, загруженных из JSON файла,
                должно быть списком, получено {type(nodes_data).__name__}""")

        nodes = []
        loads_by_name = {ld.load_name: ld for ld in loads}

        for node_data in nodes_data:
            node_payload = dict(node_data)

            load_names = node_payload.get("loads")
            if not isinstance(load_names, list):
                raise TypeError(f"""Поле 'loads' у узла {node_payload.get('node_name')}
                    должно быть списком имён, получено {type(load_names).__name__}""")

            resolved: list[Load] = []
            for name in load_names:
                if name not in loads_by_name:
                    raise ValueError(f"""Нагрузка '{name}' (узел {node_payload.get('node_name')}) не найдена.
                        Доступные: {list(loads_by_name)}""")
                resolved.append(loads_by_name[name])

            node_payload["loads"] = resolved
            nodes.append(Node.model_validate(node_payload))

        # проверка на повторения имен
        node_names = [nd.node_name for nd in nodes]
        if len(node_names) != len(set(node_names)):
            raise ValueError("Имеются повторения имен узлов")

        return nodes

    @staticmethod
    def _load_branches(data: dict[str, Any], nodes: list[Node]) -> list[Line | Transformer2 | Transformer3]:
        """Загрузить данные ветвей

        Args:
            data (dict[str, Any]): словарь данных, загруженных из JSON файла
            nodes (list[Node]): список узлов

        Returns:
            list[Branch]: данные о ветвях
        """
        if "BRANCHES" not in data:
            raise KeyError("Ключ 'BRANCHES' не найден в данных")
        branches_data = data.get("BRANCHES")
        if not isinstance(branches_data, dict):
            raise TypeError(f"""Поле 'BRANCHES' в словаре данных, загруженных из JSON файла,
                должно быть словарем, получено {type(branches_data).__name__}""")

        # получение списка линий
        lines_data = branches_data.get("LINES")
        lines = []
        if lines_data is None:
            pass
        elif not isinstance(lines_data, list):
            raise TypeError(f"""Поле 'LINES' в словаре 'BRANCHES' должно быть списком,
                получено {type(lines_data).__name__}""")
        else:
            lines = get_lines_or_transformers2(lines_data, nodes, "line")

        # получение списка трансформаторов 2
        transformers2_data = branches_data.get("TRANSFORMERS2")
        transformers2 = []
        if transformers2_data is None:
            pass
        elif not isinstance(transformers2_data, list):
            raise TypeError(f"""Поле 'TRANSFORMERS2' в словаре 'BRANCHES' должно быть списком,
                получено {type(transformers2_data).__name__}""")
        else:
            transformers2 = get_lines_or_transformers2(transformers2_data, nodes, "t2")

        # получение списка трансформаторов 3
        transformers3_data = branches_data.get("TRANSFORMERS3")
        transformers3 = []
        if transformers3_data is None:
            pass
        elif not isinstance(transformers3_data, list):
            raise TypeError(f"""Поле 'TRANSFORMERS3' в словаре 'BRANCHES' должно быть списком,
                получено {type(transformers3_data).__name__}""")
        else:
            transformers3 = get_transformers3(transformers3_data, nodes)

        return lines + transformers2 + transformers3

    @staticmethod
    def _load_parameter(data: dict[str, Any]) -> Parameters:
        """Загрузить данные параметров расчета

        Args:
            data (dict[str, Any]): словарь данных, загруженных из JSON файла

        Returns:
            Parameters: данные параметров расчета
        """
        if "CALCULATION PARAMETERS" not in data:
            raise KeyError("Ключ 'CALCULATION PARAMETERS' не найден в данных")
        parameters_data = data.get("CALCULATION PARAMETERS")
        if not isinstance(parameters_data, dict):
            raise TypeError(f"""Поле 'CALCULATION PARAMETERS' в словаре данных, загруженных из JSON файла,
                должно быть словарем, получено {type(parameters_data).__name__}""")

        return Parameters.model_validate(parameters_data)

    @staticmethod
    def load(filename: str) -> tuple[list[Load], list[Node], list[Any], Parameters]:
        """Загрузить данные из JSON

        Args:
            filename (str, optional): название файла JSON в папке 'data'

        Returns:
            tuple[list[Load], list[Node], list[Branch], Parameters]: данные о сети и расчете
        """
        data = FileManager._load_data(filename)
        loads = FileManager._load_loads(data)
        nodes = FileManager._load_nodes(data, loads)
        branches = FileManager._load_branches(data, nodes)
        parameters = FileManager._load_parameter(data)

        return loads, nodes, branches, parameters

    @staticmethod
    def _save_data(data: dict[str, Any], filename: str):
        """
        Сохранить данные в JSON в папке 'result' (корень проекта, рядом с 'data')

        Args:
            data (dict[str, Any]): данные для сохранения
            filename (str): имя файла JSON

        Raises:
            ValueError: данные не сериализуются в JSON
            OSError: не удалось создать папку или записать файл
        """
        directory = Path(__file__).resolve().parent.parent.parent / "result"
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / filename
        try:
            with open(filepath, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Данные не сериализуются в JSON: {e}") from e
        except OSError as e:
            raise OSError(f"Не удалось сохранить файл результатов: {filepath}") from e
        logger.info("Результаты сохранены: %s", filepath)

    @staticmethod
    def save(
        loads: list[Load],
        nodes: list[Node],
        branches: list[Any],
        parameters: Parameters,
        slack_powers: list[Any] | None = None,
        flows: list[Any] | None = None,
    ):
        """
        Сохранить результаты расчета установившегося режима в JSON (папка 'result')

        Args:
            nodes (list[Node]): узлы после расчета
            branches (list[Any]): ветви сети
            parameters (Parameters): параметры расчета
            slack_powers (list[Any] | None): мощности балансирующих узлов (SlackPower), опционально
            flows (list[Any] | None): потоки в ветвях (BranchFlow), опционально
        """
        filename = f"result_{datetime.now()}.json"

        branch_line_results = []
        branch_t2_results = []
        branch_t3_results = []
        for branch in branches:
            branch_dict = branch.model_dump()
            branch_dict["node_1"] = branch.node_1.node_name
            branch_dict["node_2"] = branch.node_2.node_name
            if isinstance(branch, Transformer3):
                branch_dict["node_3"] = branch.node_3.node_name
                branch_t3_results.append(branch_dict)
                continue
            elif isinstance(branch, Transformer2):
                branch_t2_results.append(branch_dict)
                continue
            branch_line_results.append(branch_dict)

        dict_branches = {}
        if len(branch_line_results):
            dict_branches["LINES"] = branch_line_results
        if len(branch_t2_results):
            dict_branches["TRANSFORMERS2"] = branch_t2_results
        if len(branch_t3_results):
            dict_branches["TRANSFORMERS3"] = branch_t3_results

        node_results = []
        for node in nodes:
            node_dict = node.model_dump()
            if len(node_dict["loads"]):
                node_dict["loads"] = [load["load_name"] for load in node_dict["loads"]]
            node_results.append(node_dict)

        data: dict[str, Any] = {
            "CALCULATION PARAMETERS": parameters.model_dump(),
            "LOADS": [load.model_dump() for load in loads],
            "NODES": node_results,
            "BRANCHES": dict_branches,
        }
        if slack_powers is not None:
            data["SLACK POWERS"] = [item.model_dump() for item in slack_powers]
        if flows is not None:
            data["BRANCH FLOWS"] = [item.model_dump() for item in flows]
            data["TOTAL LOSSES"] = {
                "dp": sum(item.dp for item in flows),
                "dq": sum(item.dq for item in flows),
            }
        FileManager._save_data(data, filename)


def get_lines_or_transformers2(branches_data: list[dict[str, Any]], nodes: list[Node], type_branch: str) -> list[Any]:
    """
    Получить список линий или двухобмоточных трансформаторов с указанием на экземпляры узлов

    Args:
        branches_data (list[dict[str, Any]]): список данных линий или двухобмоточных трансформаторов
        nodes (list[Node]): список узлов
        type_branch (str): тип ветви (line, t2)

    Returns:
        list[Any]: список линий или двухобмоточных трансформаторов
    """
    branches: list[Any] = []
    nodes_by_name = {nd.node_name: nd for nd in nodes}

    for branch_data in branches_data:
        branch_payload = dict(branch_data)

        node_1 = branch_payload.get("node_1")
        node_2 = branch_payload.get("node_2")
        if not isinstance(node_1, str) or not isinstance(node_2, str):
            raise TypeError(f"""Поля 'node_1' и 'node_2' у ветви {branch_payload.get('branch_name')}
                должны быть имёнами, получены {type(node_1).__name__} и {type(node_2).__name__}""")

        if node_1 not in nodes_by_name:
            raise ValueError(f"""Узел '{node_1}' (ветвь {branch_payload.get('branch_name')}) не найден.
                Доступные: {list(nodes_by_name)}""")
        if node_2 not in nodes_by_name:
            raise ValueError(f"""Узел '{node_2}' (ветвь {branch_payload.get('branch_name')}) не найден.
                Доступные: {list(nodes_by_name)}""")

        branch_payload["node_1"] = nodes_by_name[node_1]
        branch_payload["node_2"] = nodes_by_name[node_2]
        if type_branch == "line":
            branches.append(Line.model_validate(branch_payload))
        elif type_branch == "t2":
            branches.append(Transformer2.model_validate(branch_payload))
        else:
            raise ValueError(f"Неверный тип ветви {type_branch}. Доступные варианты: 'line', 't2'")

    return branches


def get_transformers3(branches_data: list[dict[str, Any]], nodes: list[Node]) -> list[Transformer3]:
    """
    Получить список трехобмоточных трансформаторов с указанием на экземпляры узлов

    Args:
        branches_data (list[dict[str, Any]]): список данных трехобмоточных трансформаторов
        nodes (list[Node]): список узлов

    Returns:
        list[Transformer3]: список трехобмоточных трансформаторов
    """
    branches = []
    nodes_by_name = {nd.node_name: nd for nd in nodes}

    for branch_data in branches_data:
        branch_payload = dict(branch_data)

        node_1 = branch_payload.get("node_1")
        node_2 = branch_payload.get("node_2")
        node_3 = branch_payload.get("node_3")
        if not isinstance(node_1, str) or not isinstance(node_2, str) or not isinstance(node_3, str):
            raise TypeError(f"""Поля 'node_1', 'node_2' и 'node_3' у ветви {branch_payload.get('branch_name')}
                должны быть имёнами, получены:
                    {type(node_1).__name__},
                    {type(node_2).__name__},
                    {type(node_3).__name__}""")

        if node_1 not in nodes_by_name:
            raise ValueError(f"""Узел '{node_1}' (ветвь {branch_payload.get('branch_name')}) не найден.
                Доступные: {list(nodes_by_name)}""")
        if node_2 not in nodes_by_name:
            raise ValueError(f"""Узел '{node_2}' (ветвь {branch_payload.get('branch_name')}) не найден.
                Доступные: {list(nodes_by_name)}""")
        if node_3 not in nodes_by_name:
            raise ValueError(f"""Узел '{node_3}' (ветвь {branch_payload.get('branch_name')}) не найден.
                Доступные: {list(nodes_by_name)}""")

        branch_payload["node_1"] = nodes_by_name[node_1]
        branch_payload["node_2"] = nodes_by_name[node_2]
        branch_payload["node_3"] = nodes_by_name[node_3]
        branches.append(Transformer3.model_validate(branch_payload))

    return branches
