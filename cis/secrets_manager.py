# Use this code snippet in your app.
# If you need more information about configurations or implementing the sample code, visit the AWS docs:   
# https://aws.amazon.com/developers/getting-started/python/
import boto3
import base64
import json
from botocore.exceptions import ClientError

def get_secret(secret_name, region_name):
     
    # Create a Secrets Manager client
    session = boto3.session.Session()
    
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    # In this sample we only handle the specific exceptions for the 'GetSecretValue' API.
    # See https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
    # We rethrow the exception by default.
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # We can't find the resource that you asked for.
            # Deal with the exception here, and/or rethrow at your discretion.
            raise e
    else:
        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            return secret
        else:
            decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
            return decoded_binary_secret
            
def load_all_secrets(c, region_name, logger):
    logger.info('Beginning to load secrets.')
    db_creds = json.loads(get_secret('cis-db-credentials', region_name))
    wam = json.loads(get_secret('wam-credentials', region_name))
    nuxeo = json.loads(get_secret('nuxeo-credentials', region_name))
    service_account = json.loads(get_secret('service-account-credentials', region_name))
    logger.info('Finished loading secrets.')
    c.nuxeo_dev_username = nuxeo['nuxeo_dev_username']
    c.nuxeo_dev_password = nuxeo['nuxeo_dev_password']
    c.wam_username = wam['wam_username']
    c.wam_password = wam['wam_password']
    c.wam_host = wam['wam_host']
    c.email_username = service_account['username']
    c.email_password = service_account['password']
    c.client_id = service_account['client_id']
    c.client_secret = service_account['client_secret']
    c.tenant_id = service_account['tenant_id']
    database_user = db_creds['username']
    database_password = db_creds['password']
    database_host = db_creds['host']
    database_port = db_creds['port']
    c.database_uri = f"mysql+pymysql://{database_user}:{database_password}@{database_host}:{database_port}/cis"
