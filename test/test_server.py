import importlib
import sys
import types


def _load_server_module():
    package = types.ModuleType("process_model")
    package.__path__ = []
    sys.modules.setdefault("process_model", package)

    for module_name in (
        "process_model.transition_edges",
        "process_model.zscore_calculation",
        "process_model.clustering",
        "process_model.graphing",
    ):
        module = types.ModuleType(module_name)
        module.main = lambda: None
        sys.modules.setdefault(module_name, module)

    return importlib.import_module("server")


def test_detect_dataset_and_team_handles_communication():
    server = _load_server_module()

    dataset, team = server.detect_dataset_and_team(
        "data/outputs/communication/year-long-project-team-7/graph.png"
    )

    assert dataset == "communication"
    assert team == "year-long-project-team-7"


def test_detect_dataset_and_team_keeps_existing_cases():
    server = _load_server_module()

    dataset, team = server.detect_dataset_and_team(
        "data/outputs/branching/year-long-project-team-3/graph.png"
    )

    assert dataset == "branching"
    assert team == "year-long-project-team-3"