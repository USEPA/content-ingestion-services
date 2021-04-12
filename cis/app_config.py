import json

def config_from_file(file, overrides={}):
    with open(file, 'r') as f:
        conf = json.loads(f.read())
    conf.update(overrides)
    return CISConfig(**conf)

class CISConfig:
    def __init__(self, cis_server, tika_server, ezemail_server, client_id, database_uri, record_schedules_server):
        self.cis_server = cis_server
        self.tika_server = tika_server
        self.ezemail_server = ezemail_server
        self.client_id = client_id
        self.database_uri = database_uri
        self.record_schedules_server = record_schedules_server