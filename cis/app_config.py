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
        client_id, 
        database_uri, 
        record_schedules_server, 
        wam_host, 
        wam_username, 
        wam_password,
        sems_host,
        patt_host,
        patt_api_key,
        bucket_name,
        nuxeo_dev_url,
        nuxeo_dev_username, 
        nuxeo_dev_password,
        nuxeo_prod_url,
        nuxeo_prod_username, 
        nuxeo_prod_password,
        arms_upload_bucket,
        arms_upload_prefix
        ):
        self.cis_server = cis_server
        self.tika_server = tika_server
        self.client_id = client_id
        self.database_uri = database_uri
        self.record_schedules_server = record_schedules_server
        self.wam_host = wam_host
        self.wam_username = wam_username
        self.wam_password = wam_password
        self.sems_host = sems_host
        self.patt_host = patt_host
        self.patt_api_key = patt_api_key
        self.bucket_name = bucket_name
        self.nuxeo_dev_url = nuxeo_dev_url
        self.nuxeo_dev_username = nuxeo_dev_username
        self.nuxeo_dev_password = nuxeo_dev_password
        self.nuxeo_prod_url = nuxeo_prod_url
        self.nuxeo_prod_username = nuxeo_prod_username
        self.nuxeo_prod_password = nuxeo_prod_password
        self.arms_upload_bucket = arms_upload_bucket
        self.arms_upload_prefix = arms_upload_prefix
        
