import requests
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
import jwt
import threading

class PublicKeyCache:
    def __init__(self):
        self.keys = get_public_keys()
        self.lock = threading.Lock()

    def refresh_public_keys(self):
        with self.lock:
            try:
                self.keys = get_public_keys()
            except:
                # TODO improve logging
                print('Unable to retrieve public keys.')
    
    def get_key(self, kid):
        with self.lock:
            if kid in self.keys:
                return self.keys[kid]
            else:
                self.refresh_public_keys()
                if kid in self.keys:
                    return self.keys[kid]
                else:
                    return None

    def validate_request(self, req, config):
        headers = req.headers
        if "Authorization" not in headers:
            return False, "Must provide authorization header.", None
        id_token = headers["Authorization"]
        try:
            kid = jwt.get_unverified_header(id_token)['kid']
        except:
            return False, "Could not retrieve kid from ID token.", None
        try:
            public_key = self.get_key(kid)
        except:
            return False, "Failed to retrieve public key.", None
        if public_key is None:
            return False, "Unable to find matching public key.", None
        try:
            token_data = jwt.decode(
                id_token,
                public_key,
                algorithms='RS256',
                audience=config.client_id,
            )
        except:
            return False, "ID Token is invalid.", None
        return True, None, token_data

def create_public_key(x5c):
    cert = ''.join([
        '-----BEGIN CERTIFICATE-----\n',
        x5c,
        '\n-----END CERTIFICATE-----\n',
    ])
    return load_pem_x509_certificate(cert.encode(), default_backend()).public_key()

def get_public_keys():
    jwk_uri = "https://login.microsoftonline.com/epa.gov/discovery/v2.0/keys"
    res = requests.get(jwk_uri)
    jwk_keys = res.json()
    # Iterate JWK keys and extract matching x5c chain
    public_keys = {}
    for key in jwk_keys['keys']:
        public_keys[key['kid']] = create_public_key(key['x5c'][0])
    return public_keys