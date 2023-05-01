import argparse
import boto3
import base64
import json
from botocore.exceptions import ClientError
import requests
import datetime

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
            
def load_all_secrets(region_name):
    service_account_creds = json.loads(get_secret('service-account-credentials', region_name))
    wam = json.loads(get_secret('wam-credentials', region_name))
    username = service_account_creds['username']
    password = service_account_creds['password']
    client_id = service_account_creds['client_id']
    client_secret = service_account_creds['client_secret']
    tenant_id = service_account_creds['tenant_id']
    wam_username = wam['wam_username']
    wam_password = wam['wam_password']
    wam_host = wam['wam_host']
    return username, password, client_id, client_secret, wam_username, wam_password, wam_host, tenant_id

def list_wam_users(start_index, count, wam_username, wam_password, wam_host):
    try:
        url = "https://" + wam_host + "/iam/governance/scim/v1/Users?filter=Active eq active&attributes=active&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Upn&startIndex=" + str(start_index) + "&count=" + str(count)
        wam = requests.get(url, auth=(wam_username, wam_password), timeout=60)
        if wam.status_code != 200 or 'Resources' not in wam.json():
            return []
        return [x.get('urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User', {}).get('Upn', None) for x in wam.json()['Resources']]
    except:
        return []

def get_service_token(client_id, client_secret, tenant_id):
    try:
        params = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        r = requests.get("https://login.microsoftonline.com/" + tenant_id + "/oauth2/v2.0/token", data=params)
        return r.json()['access_token']
    except:
        raise Exception('Failed to get service token.')

def get_chat_token(username, password, client_id, client_secret, tenant_id):
    try:
        params = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "ChatMessage.Send",
            "grant_type": "password",
            "username": username,
            "password": password
        }
        r = requests.get("https://login.microsoftonline.com/" + tenant_id + "/oauth2/v2.0/token", data=params)
        return r.json()['access_token']
    except:
        raise Exception('Failed to get chat token.')

def refresh_tokens(username, password, client_id, client_secret, tenant_id):
    service_token = get_service_token(client_id, client_secret, tenant_id)
    chat_token = get_chat_token(username, password, client_id, client_secret, tenant_id)
    return service_token, chat_token

def get_chat_account_user_id(chat_token):
    headers = {'Authorization': 'Bearer ' + chat_token}
    r = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
    return r.json()['id']

def send_email_chat(user, chat_token, chat_account_user_id):
    headers = {'Authorization': 'Bearer ' + chat_token}
    chat_data = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": [
                    "owner"
                ],
                "user@odata.bind": "https://graph.microsoft.com/v1.0/users('" + chat_account_user_id + "')"
            },
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": [
                    "owner"
                ],
                "user@odata.bind": "https://graph.microsoft.com/v1.0/users('" + user + "')"
            }
        ]
    }

    chat_req = requests.post('https://graph.microsoft.com/v1.0/chats/', headers=headers, json=chat_data)
    chat_id = chat_req.json()['id']
    chat_message = {
        "body": {
            "contentType": "html",
            "content": "Hi! This is a reminder from ARMS (Agency Records Management System). You have categorized emails as records. These records have not yet been submitted to ARMS. Please visit the <a href=\"https://arms-uploader-ui.cis-dev.aws.epa.gov/\">ARMS Uploader</a> to complete the submission."
        }
    }
    chat_req = requests.post('https://graph.microsoft.com/v1.0/chats/' + chat_id + '/messages', json=chat_message, headers=headers)

def send_sharepoint_chat(user, chat_token, chat_account_user_id):
    headers = {'Authorization': 'Bearer ' + chat_token}
    chat_data = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": [
                    "owner"
                ],
                "user@odata.bind": "https://graph.microsoft.com/v1.0/users('" + chat_account_user_id + "')"
            },
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": [
                    "owner"
                ],
                "user@odata.bind": "https://graph.microsoft.com/v1.0/users('" + user + "')"
            }
        ]
    }

    chat_req = requests.post('https://graph.microsoft.com/v1.0/chats/', headers=headers, json=chat_data)
    chat_id = chat_req.json()['id']
    chat_message = {
        "body": {
            "contentType": "html",
            "content": "Hi! This is a reminder from ARMS (Agency Records Management System). You have added records to your EZ Records folder. These records have not yet been submitted to ARMS. Please visit the <a href=\"https://arms-uploader-ui.cis-dev.aws.epa.gov/\">ARMS Uploader</a> to complete the submission."
        }
    }
    chat_req = requests.post('https://graph.microsoft.com/v1.0/chats/' + chat_id + '/messages', json=chat_message, headers=headers)

def user_has_pending_email(user, service_token):
    headers = {'Authorization': 'Bearer ' + service_token}
    r = requests.get("https://graph.microsoft.com/v1.0/users/" + user + "/messages?$filter=categories/any(a:a+eq+'Record')&$top=1", headers=headers)
    if r.status_code != 200:
        print('Email check failed for user ' + user)
        return False
    return 'value' in r.json() and len(r.json()['value']) > 0

# Note: Depth increases when passing to a subfolder, or to a next page of results
def read_sharepoint_folder(drive_id, relative_path, access_token, filter_status, depth, link = None, max_depth=5):
  if depth > max_depth:
    return False
  headers = {'Authorization': 'Bearer ' + access_token}
  if link:
    shared = requests.get(link, headers=headers, timeout=10)
  else: 
    shared = requests.get("https://graph.microsoft.com/v1.0/drives/" + drive_id + "/root:/" + relative_path + ":/children/?$expand=listItem&$top=1000", headers=headers, timeout=10)
  shared_items = shared.json()['value']
  for x in shared_items:
    if x['listItem']['fields'].get('Records_x0020_Status', None) == filter_status:
        return True
  # Process subfolders
  folders = list(filter(lambda x: "folder" in x, shared_items))
  for folder in folders:
    found_record = read_sharepoint_folder(relative_path + "/" + folder["name"], access_token, filter_status, depth + 1, link=None, max_depth=max_depth)
    if found_record:
        return True
  # If number of items in this folder is too large, process the rest of the items in the folder
  if "@odata.nextLink" in shared.json():
    next_link = shared.json()['@odata.nextLink']
    found_record = read_sharepoint_folder(relative_path, access_token, filter_status, depth + 1, link=next_link, max_depth=max_depth)
    if found_record:
        return True
  return False

def get_user_drive_id(user, token):
    headers = {'Authorization': 'Bearer ' + token}
    r = requests.get("https://graph.microsoft.com/v1.0/users/" + user + "/drive", headers=headers)
    return r.json()['id']   

def user_has_pending_onedrive_file(user, service_token):
    drive_id = get_user_drive_id(user, service_token)
    return read_sharepoint_folder(drive_id, 'ARMS File Sync', service_token, 'Pending', 0)

def send_notifications(username, password, client_id, client_secret, wam_username, wam_password, wam_host, tenant_id, user_batch_size, full_run):
    test_users = set(['Kreisel.Michael@epa.gov', 'Yuen.Andrew@epa.gov', 'Schouw.Stephanie@epa.gov'])
    
    print('Getting list of users.')
    index = 1
    wam_users = []
    while True:
        if index % 10000 == 1:
            print('At user index ' + str(index))
        new_users = list_wam_users(index, user_batch_size, wam_username, wam_password, wam_host)
        if len(new_users) == 0:
            break
        wam_users = wam_users + new_users
        index += user_batch_size
    users_with_upn = list(filter(lambda x: x!= None, wam_users))
    print('Total active users with UPN: ' + str(len(users_with_upn)))

    token_time = datetime.datetime.now()
    print('Getting tokens')
    service_token, chat_token = refresh_tokens(username, password, client_id, client_secret, tenant_id)
    chat_account_id = get_chat_account_user_id(chat_token)
    for user in users_with_upn:
        #if full_run or user in test_users:
        if user in test_users:
            time_diff = datetime.datetime.now() - token_time
            if time_diff.total_seconds() > 15 * 60:
                service_token, chat_token = refresh_tokens(username, password, client_id, client_secret, tenant_id)
            if user_has_pending_email(user, service_token):
                send_email_chat(user, chat_token, chat_account_id)
                continue
            if user_has_pending_onedrive_file(user, service_token):
                send_sharepoint_chat(user, chat_token, chat_account_id)
                continue

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Sends notifications about records pending submission.')
    parser.add_argument('--region_name', help='AWS region.')
    parser.add_argument('--user_batch_size', type=int, default=1000, help='Number of users to query at one time.')
    parser.add_argument('--full_run', action="store_true", default=False, help='Whether to run for all users or just test users.')
    args = vars(parser.parse_args())
    username, password, client_id, client_secret, wam_username, wam_password, wam_host, tenant_id = load_all_secrets(args['region_name'])
    send_notifications(username, password, client_id, client_secret, wam_username, wam_password, wam_host, tenant_id, args['user_batch_size'], args['full_run'])

