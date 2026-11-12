import json

import pytest
from pydantic import ValidationError

import src.util.file_manager as fm
from src.model.branch import Line, Transformer3
from src.model.load import Load
from src.model.node import Node
from src.model.parameters import Parameters
from src.util.file_manager import FileManager, get_lines_or_transformers2, get_transformers3

LOAD_DICT = dict(load_name="L1", p_0=20.0, q_0=10.0, z_p=0.0, i_p=0.0, p_p=1.0,
                 z_q=0.0, i_q=0.0, p_q=1.0, u_0=110.0)
NODE_DICT = dict(node_name="1", type_node="slack", type_node_current="slack", u_base=110,
                 g_shunt=0.0, b_shunt=0.0, u_magnitude=110.0, u_angle=0.0,
                 p_gen=0.0, q_gen=0.0, q_min=0.0, q_max=0.0, loads=[])
NODE2_DICT = dict(NODE_DICT, node_name="2", type_node="pq", type_node_current="pq", loads=["L1"])
LINE_DICT = dict(branch_name="L-1-2", node_1="1", node_2="2", r_1=10.0, x_1=40.0, g_shunt=0.0, b_shunt=0.0)
BRANCHES_DICT = {"LINES": [LINE_DICT], "TRANSFORMERS2": [], "TRANSFORMERS3": []}
PARAMS_DICT = {"accuracy": 1e-6, "max_iterations": 100}
FULL_DATA = {"LOADS": [LOAD_DICT], "NODES": [NODE_DICT, NODE2_DICT],
             "BRANCHES": BRANCHES_DICT, "CALCULATION PARAMETERS": PARAMS_DICT}


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Подменяет корень так, чтобы FileManager искал JSON в tmp_path/data."""
    class FakePath:
        def __init__(self, *args): pass
        def resolve(self): return self
        @property
        def parent(self): return self
        def __truediv__(self, other): return tmp_path / other
    monkeypatch.setattr(fm, "Path", FakePath)
    return tmp_path


@pytest.fixture
def nodes(make_node):
    return [make_node("1", "slack"), make_node("2", "pq")]


class TestLoadData:
    def test_valid_json(self, data_dir):
        (data_dir / "data").mkdir()
        (data_dir / "data" / "net.json").write_text(json.dumps(FULL_DATA), encoding="utf-8")
        assert FileManager._load_data("net.json") == FULL_DATA

    def test_missing_file_raises(self, data_dir):
        with pytest.raises(FileNotFoundError, match="не найден"):
            FileManager._load_data("нет.json")

    def test_broken_json_raises(self, data_dir):
        (data_dir / "data").mkdir()
        (data_dir / "data" / "bad.json").write_text("{не json", encoding="utf-8")
        with pytest.raises(ValueError, match="Ошибка формата JSON"):
            FileManager._load_data("bad.json")

    def test_non_object_root_raises(self, data_dir):
        (data_dir / "data").mkdir()
        (data_dir / "data" / "list.json").write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(TypeError, match="словарем"):
            FileManager._load_data("list.json")


class TestLoadLoads:
    def test_ok(self):
        loads = FileManager._load_loads({"LOADS": [LOAD_DICT]})
        assert isinstance(loads[0], Load) and loads[0].load_name == "L1"

    def test_missing_key(self):
        with pytest.raises(KeyError, match="LOADS"):
            FileManager._load_loads({})

    def test_not_a_list(self):
        with pytest.raises(TypeError):
            FileManager._load_loads({"LOADS": {"a": 1}})

    def test_duplicate_names(self):
        with pytest.raises(ValueError, match="повторения"):
            FileManager._load_loads({"LOADS": [LOAD_DICT, LOAD_DICT]})

    def test_invalid_payload(self):
        with pytest.raises(ValidationError):
            FileManager._load_loads({"LOADS": [{"load_name": "bad"}]})


class TestLoadNodes:
    def test_ok_and_load_identity(self):
        loads = FileManager._load_loads({"LOADS": [LOAD_DICT]})
        nodes = FileManager._load_nodes({"NODES": [NODE_DICT, NODE2_DICT]}, loads)
        assert isinstance(nodes[1], Node)
        assert nodes[1].loads[0] is loads[0]

    def test_missing_key(self):
        with pytest.raises(KeyError, match="NODES"):
            FileManager._load_nodes({}, [])

    def test_not_a_list(self):
        with pytest.raises(TypeError):
            FileManager._load_nodes({"NODES": 42}, [])

    def test_loads_field_not_a_list(self):
        with pytest.raises(TypeError, match="loads"):
            FileManager._load_nodes({"NODES": [dict(NODE2_DICT, loads="L1")]}, [])

    def test_unknown_load(self):
        with pytest.raises(ValueError, match="не найдена"):
            FileManager._load_nodes({"NODES": [NODE2_DICT]}, [])

    def test_duplicate_node_names(self):
        with pytest.raises(ValueError, match="повторения"):
            FileManager._load_nodes({"NODES": [NODE_DICT, NODE_DICT]}, [])


class TestLoadBranches:
    def test_missing_key(self, nodes):
        with pytest.raises(KeyError, match="BRANCHES"):
            FileManager._load_branches({}, nodes)

    def test_not_a_dict(self, nodes):
        with pytest.raises(TypeError):
            FileManager._load_branches({"BRANCHES": []}, nodes)

    @pytest.mark.parametrize("missing", ["LINES", "TRANSFORMERS2", "TRANSFORMERS3"])
    def test_missing_branch_lists(self, nodes, missing):
        # пустые списки, чтобы не задеть баг с литералом 'node_1' до проверяемого места
        base = {"LINES": [], "TRANSFORMERS2": [], "TRANSFORMERS3": []}
        data = {"BRANCHES": {k: v for k, v in base.items() if k != missing}}
        with pytest.raises(TypeError, match=missing):
            FileManager._load_branches(data, nodes)

    def test_happy_path(self, nodes):
        branches = FileManager._load_branches({"BRANCHES": BRANCHES_DICT}, nodes)
        assert isinstance(branches[0], Line)
        assert branches[0].node_1 is nodes[0] and branches[0].node_2 is nodes[1]


class TestBranchHelpers:
    def test_unknown_node_name(self, nodes):
        with pytest.raises(ValueError, match="не найден"):
            get_lines_or_transformers2([dict(LINE_DICT, node_2="999")], nodes, "line")

    def test_non_string_node_field(self, nodes):
        with pytest.raises(TypeError):
            get_lines_or_transformers2([dict(LINE_DICT, node_1=1)], nodes, "line")

    def test_t3_unknown_node(self, nodes):
        t3 = dict(LINE_DICT, node_3="999", r_2=1, x_2=1, r_3=1, x_3=1, u_1=110, u_2=35, u_3=10)
        with pytest.raises(ValueError, match="не найден"):
            get_transformers3([t3], nodes)

    def test_line_happy_path(self, nodes):
        lines = get_lines_or_transformers2([LINE_DICT], nodes, "line")
        assert lines[0].node_1 is nodes[0]

    def test_t3_happy_path(self, make_node):
        nodes = [make_node("1", "slack"), make_node("2"), make_node("3")]
        t3 = dict(LINE_DICT, node_3="3", r_2=1, x_2=1, r_3=1, x_3=1, u_1=110, u_2=35, u_3=10)
        res = get_transformers3([t3], nodes)
        assert isinstance(res[0], Transformer3) and res[0].node_3 is nodes[2]


class TestLoadParameter:
    def test_ok(self):
        p = FileManager._load_parameter({"CALCULATION PARAMETERS": PARAMS_DICT})
        assert isinstance(p, Parameters) and p.max_iterations == 100

    def test_missing_key(self):
        with pytest.raises(KeyError, match="CALCULATION PARAMETERS"):
            FileManager._load_parameter({})

    def test_not_a_dict(self):
        with pytest.raises(TypeError):
            FileManager._load_parameter({"CALCULATION PARAMETERS": []})


def test_load_full_scenario(data_dir):
    (data_dir / "data").mkdir()
    (data_dir / "data" / "data.json").write_text(json.dumps(FULL_DATA), encoding="utf-8")
    loads, nodes, branches, parameters = FileManager.load()
    assert len(loads) == 1 and len(nodes) == 2 and len(branches) == 1
    assert branches[0].node_1 is nodes[0]
    assert parameters.accuracy == 1e-6
