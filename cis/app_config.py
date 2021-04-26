import json

def config_from_file(file, overrides={}):
    with open(file, 'r') as f:
        conf = json.loads(f.read())
    conf.update(overrides)
    return CISConfig(**conf)

class CISConfig:
    def __init__(
        self, 
        cis_server, 
        tika_server, 
        ezemail_server, 
        client_id, 
        database_uri, 
        record_schedules_server, 
        documentum_prod_url, 
        documentum_prod_username, 
        documentum_prod_password,
        wam_host, 
        wam_username, 
        wam_password,
        records_repository_id
        ):
        self.cis_server = cis_server
        self.tika_server = tika_server
        self.ezemail_server = ezemail_server
        self.client_id = client_id
        self.database_uri = database_uri
        self.record_schedules_server = record_schedules_server
        self.documentum_prod_url = documentum_prod_url
        self.documentum_prod_password = documentum_prod_password
        self.documentum_prod_username = documentum_prod_username
        self.wam_host = wam_host
        self.wam_username = wam_username
        self.wam_password = wam_password
        self.records_repository_id = records_repository_id