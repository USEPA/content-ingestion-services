import json

def config_from_file(file):
    with open(file, 'r') as f:
        conf = json.loads(f.read())
    return CISConfig(**conf)

class CISConfig:
    def __init__(self, deep_detect_api_server, nlp_buddy_server, tika_server):
        self.deep_detect_api_server = deep_detect_api_server
        self.nlp_buddy_server = nlp_buddy_server
        self.tika_server = tika_server