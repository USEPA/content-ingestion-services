from context import cis
from cis import cis_requests, app_config

def test_object_id_validation():
    config = app_config.config_from_file('dev_config.json')
    assert not cis_requests.object_id_is_valid(config, '12345') 
