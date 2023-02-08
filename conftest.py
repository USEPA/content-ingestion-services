import pytest
from cis import HuggingFaceModel

def pytest_addoption(parser):
    parser.addoption("--model_path", action="store", default=None)
    parser.addoption("--label_mapping_path", action="store", default=None)
    parser.addoption("--office_info_mapping_path", action="store", default=None)

@pytest.fixture(scope='session')
def hf_model(pytestconfig):
    model_path = pytestconfig.getoption("--model_path")
    label_mapping_path = pytestconfig.getoption("--label_mapping_path")
    office_info_mapping_path = pytestconfig.getoption("--office_info_mapping_path")
    return HuggingFaceModel(model_path, label_mapping_path, office_info_mapping_path)
