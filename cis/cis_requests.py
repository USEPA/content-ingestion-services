import requests
from .data_classes import *
import json 
import email
from flask import Response, current_app as app, send_file
import urllib 
import io
import re

def tika(file, config, extraction_type='text'):
  if extraction_type == 'html':
    accept = "text/html"
  else:
    accept = "text/plain"
  headers = {
            "X-Tika-PDFOcrStrategy": "ocr_only",
            "Cache-Control": "no-cache",
            "accept": accept
          }
  server = "http://" + config.tika_server + "/tika"
  r = requests.put(server, data=file, headers=headers)
  if r.status_code != 200:
    return False, None, Response('Tika failed with status ' + str(r.status_code), 500, mimetype='text/plain')
  else:
    return True, r.text, None

def get_eml_file(email_id, file_name, access_token, config):
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"filename":file_name, "emailid":email_id}
  r = requests.get("http://" + config.ezemail_server + "/ezemail/v1/getemlfile", data=json.dumps(body), headers=headers)
  if r.status_code == 200:
    return r.content
  else:
    app.logger.error('Get EML file request ended with status ' + str(r.status_code) + '. Response: ' + r.text)
    return None

def extract_attachments(eml_message):
  attachments = []
  for part in eml_message.walk():
    disposition = part.get_content_disposition()
    if disposition == 'attachment':
        attachments.append(part.get_filename())
  return attachments

def describe_email(req: DescribeEmailRequest, access_token, config):
  eml_file = get_eml_file(req.email_id, "default_file_name", access_token, config)
  if eml_file is None:
    return Response("Could not retrieve eml file.", status=400, mimetype='text/plain')
  try:
    success, body, response = tika(eml_file, config, 'html')
    if not success:
      return response
    e = email.message_from_bytes(eml_file)
    attachments = extract_attachments(e)
    eml_response = DescribeEmailResponse(
    email_id=req.email_id, 
    _from = e['From'],
    to = e['To'],
    cc = e['CC'],
    subject = e['Subject'],
    date = e['Date'],
    body = body,
    attachments = attachments
  )
  except:
    return Response("Error extracting data from eml file.", status=400, mimetype='text/plain')
  return Response(eml_response.to_json(), status=200, mimetype='application/json')
  

def list_email_metadata(req: GetEmailRequest, user_email, access_token, config):
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"mailbox": 'Regular&Archive', "count": req.count}
  if req.mailbox != user_email:
    body['shared_mailbox'] = req.mailbox
  p = requests.get(
    "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
    data=json.dumps(body), 
    headers=headers
  )
  if p.status_code != 200:
    app.logger.info("Request failed with status " + str(p.status_code) + ". " + p.text)
    return Response("Unable to retrieve records.", status=400, mimetype='text/plain')
  resp = p.json()
  total_count = sum([sum(x.values()) for x in resp["total_count"]])
  emails = [ EmailMetadata(
    unid=x['unid'], 
    subject=x['subject'], 
    email_id=x['emailid'], 
    received=x['received'], 
    _from=x['from'], 
    to=x['to'], 
    sent=x['sent']
   ) for x in resp["email_items"]
  ]
  return Response(GetEmailResponse(total_count=total_count, emails=emails).to_json(), status=200, mimetype="application/json")

def mark_saved(req: MarkSavedRequest, access_token, config):
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"emailid": req.email_id}
  if req.sensitivity.lower() == 'private':
    body['sensitivityid'] = 3
  p = requests.post(
    "http://" + config.ezemail_server + "/ezemail/v1/setcategory", 
    json=body, 
    headers=headers
  )
  if p.status_code != 204:
    return Response("Unable to mark as saved.", status=400, mimetype='text/plain')
  else:
    return Response(StatusResponse(status="OK", reason="Email with id " + req.email_id + " was marked saved.").to_json(), status=200, mimetype="application/json")

def untag(req: UntagRequest, access_token, config):
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"emailid": req.email_id}
  p = requests.post(
    "http://" + config.ezemail_server + "/ezemail/v1/removecategory", 
    json=body, 
    headers=headers
  )
  if p.status_code != 204:
    return Response("Unable to remove Record category.", status=400, mimetype='text/plain')
  else:
    return Response(StatusResponse(status="OK", reason="Email with id " + req.email_id + " is no longer categorized as a record.").to_json(), status=200, mimetype="application/json")

def dql_request(config, sql, items_per_page, page_number):
    url = "https://" + config.documentum_prod_url + "/dctm-rest/repositories/ecmsrmr65?items-per-page=" + str(items_per_page) + "&page=" + str(page_number) + "&dql=" + urllib.parse.quote(sql)
    headers = {'cache-control': 'no-cache'}
    r = requests.get(url, headers=headers, auth=(config.documentum_prod_username,config.documentum_prod_password))
    return r

def get_documentum_record_count(config, lan_id):
  count_sql = "select count(*) as total_count from (select distinct s.ERMA_DOC_ID from ECMSRMR65.ERMA_DOC_SV s where s.ERMA_DOC_CUSTODIAN = '" + lan_id + "');"
  r = dql_request(config, count_sql, 10, 1)
  if r.status_code != 200:
    app.logger.error(r.text)
    return Response('Documentum count request returned status ' + str(r.status_code), status=500, mimetype='text/plain')
  dql_response = r.json()
  if 'entries' not in dql_response:
    return Response(RecordCountResponse(0).to_json(), status=200, mimetype='application/json')
  try:
    count = r.json()['entries'][0]['content']['properties']['total_count']
    return Response(RecordCountResponse(count).to_json(), status=200, mimetype='application/json')
  except:
    return Response('Failed to extract information from Documentum count request.', status=400, mimetype='text/plain')

def get_documentum_records(config, lan_id, items_per_page, page_number):
  # TODO: Improve error handling
  doc_id_sql = "select erma_doc_id, creation_date from (select s.ERMA_DOC_ID as erma_doc_id, MAX(s.R_CREATION_DATE) as creation_date from ECMSRMR65.ERMA_DOC_SV s where s.ERMA_DOC_CUSTODIAN = '" + lan_id + "' GROUP BY s.ERMA_DOC_ID) ORDER BY creation_date DESC;"
  r = dql_request(config, doc_id_sql, items_per_page, page_number)
  if r.status_code != 200:
    app.logger.error(r.text)
    return Response('Documentum doc ID request returned status ' + str(r.status_code), status=500, mimetype='text/plain')
  doc_id_resp = r.json()
  if 'entries' not in doc_id_resp:
    return Response(DocumentumRecordList(has_next=False, records=[]).to_json(), status=200, mimetype='application/json')
  doc_ids = [x['content']['properties']['erma_doc_id'] for x in doc_id_resp['entries']]
  has_next = False
  for l in doc_id_resp['links']:
    if l['rel'] == 'next':
      has_next = True
  doc_where_clause = ' OR '.join(["erma_doc_id = '" + str(x) + "'" for x in doc_ids])
  doc_info_sql = "select s.erma_doc_sensitivity as erma_doc_sensitivity, s.R_OBJECT_TYPE as r_object_type, s.ERMA_DOC_DATE as erma_doc_date, s.ERMA_DOC_CUSTODIAN as erma_doc_custodian, s.ERMA_DOC_ID as erma_doc_id, s.R_FULL_CONTENT_SIZE as r_full_content_size, s.R_OBJECT_ID as r_object_id, s.ERMA_DOC_TITLE as erma_doc_title from ECMSRMR65.ERMA_DOC_SV s where " + doc_where_clause + ";"
  r = dql_request(config, doc_info_sql, 3*int(items_per_page), 1)
  if r.status_code != 200:
    app.logger.error(r.text)
    return Response('Documentum doc info request returned status ' + str(r.status_code), status=500, mimetype='text/plain')
  doc_info = {}
  for doc in r.json()['entries']:
    properties = doc['content']['properties']
    doc_id = properties['erma_doc_id']
    object_id = properties['r_object_id']
    size = properties['r_full_content_size']
    if properties['erma_doc_sensitivity'] == '3':
      sensitivity = 'private'
    else:
      sensitivity = 'shared'
    if properties['r_object_type'] == 'erma_mail':
      doc_type = 'email'
    else:
      doc_type = 'document'
    if doc_id in doc_info:
      data = doc_info[doc_id]
      if doc_type == 'erma_mail':
        data['doc_type'] = doc_type
      data['object_ids'].append(object_id)
      data['size'] += size
    else:
      doc_info[doc_id] = {
        "doc_id": doc_id,
        "size": size,
        "object_ids": [object_id],
        "title": properties['erma_doc_title'],
        "date": properties['erma_doc_date'],
        "sensitivity": sensitivity,
        "custodian": properties['erma_doc_custodian'],
        "doc_type": doc_type
      }
  doc_list = DocumentumRecordList(has_next=has_next, records=list(sorted([DocumentumDocInfo(**x) for x in doc_info.values()], key=lambda x: x.date, reverse=True)))
  return Response(doc_list.to_json(), status=200, mimetype='application/json')

def object_id_is_valid(config, object_id):
  return re.fullmatch('[a-z0-9]{16}', object_id) is not None and object_id[2:8] == config.records_repository_id

def download_documentum_record(config, lan_id, object_ids):
  # Validate object_ids
  for object_id in object_ids:
    valid = object_id_is_valid(config, object_id)
    if not valid:
      return Response('Object ID invalid: ' + object_id, status=400, mimetype='text/plain')
  doc_where_clause = ' OR '.join(["s.r_object_id = '" + str(x) + "'" for x in object_ids])
  doc_info_sql = "select s.ERMA_DOC_CUSTODIAN as erma_doc_custodian, r_object_id from ECMSRMR65.ERMA_DOC_SV s where " + doc_where_clause + ";"
  # This gives some buffer, even though there should be exactly len(object_ids) items to recover
  r = dql_request(config, doc_info_sql, 2*len(object_ids), 1)
  if r.status_code != 200:
    app.logger.error(r.text)
    return Response('Documentum doc info request returned status ' + str(r.status_code), status=500, mimetype='text/plain')
  missing_ids = set(object_ids) - set([doc['content']['properties']['r_object_id'] for doc in r.json()['entries']])
  if len(missing_ids) != 0:
    return Response('The following object_ids could not be found: ' + ', '.join(list(missing_ids)), status=400, mimetype='text/plain')
  for doc in r.json()['entries']:
    if doc['content']['properties']['erma_doc_custodian'] != lan_id:
      return Response('User ' + lan_id + ' is not the custodian of all files requested.', status=401, mimetype='text/plain')
  
  hrefs = ['https://' + config.documentum_prod_url + '/dctm-rest/repositories/ecmsrmr65/objects/' + obj for obj in object_ids]
  data = {'hrefs': list(set(hrefs))}
  archive_url = 'https://' + config.documentum_prod_url + '/dctm-rest/repositories/ecmsrmr65/archived-contents'
  post_headers = {
    'cache-control': 'no-cache',
    'Content-Type': 'application/vnd.emc.documentum+json'
  }
  archive_req = requests.post(archive_url, headers=post_headers, json=data, auth=(config.documentum_prod_username,config.documentum_prod_password))
  if archive_req.status_code != 200:
    app.logger.error(r.text)
    return Response('Documentum archive request returned status ' + str(r.status_code), status=500, mimetype='text/plain')
  b = io.BytesIO(archive_req.content)
  return send_file(b, mimetype='application/zip', as_attachment=True, attachment_filename='ecms_download.zip')

def get_lan_id(config, token_data):
  url = 'https://' + config.wam_host + '/iam/governance/scim/v1/Users?attributes=userName&attributes=Active&filter=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Upn eq "' + token_data['email'] + '"'
  try:
    wam = requests.get(url, auth=(config.wam_username, config.wam_password))
    if wam.status_code != 200:
      app.logger.error('WAM request failed with status ' + str(wam.status_code) + '. ' + wam.text)
      return False, 'WAM request failed with status ' + str(wam.status_code) + '.', None
    user_data = wam.json()['Resources'][0]
    lan_id = user_data['userName'].lower()
    active = user_data['active']
    if not active:
      return False, 'User is not active.', None
    return True, None, lan_id
  except:
    return False, 'WAM request failed.', None