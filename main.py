from src.nr_method import NewtonRaphsonMethod
from src.postprocessing import calc_results
from src.util.file_manager import FileManager


def main(filepath: str):
    loads, nodes, branches, parameters = FileManager.load_from_file(filepath)
    nodes, branches, parameters = NewtonRaphsonMethod.run(nodes, branches, parameters)
    slack_powers, flows = calc_results(nodes, branches)
    FileManager.save_to_file(loads, nodes, branches, parameters, slack_powers, flows)


if __name__ == "__main__":
    main("test_data_1.json")
    main("test_data_2.json")
