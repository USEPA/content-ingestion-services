import requests
from requests.auth import HTTPBasicAuth
from .data_classes import *
import json 
import email
from flask import Response, current_app as app, send_file
import urllib 
import io
import re
import uuid

TIKA_CUTOFF = 20

def tika(file, config, extraction_type='text'):
  if extraction_type == 'html':
    accept = "text/html"
  else:
    accept = "text/plain"
  headers = {
            "X-Tika-PDFOcrStrategy": "auto",
            "X-Tika-PDFextractInlineImages": "false",
            "Cache-Control": "no-cache",
            "accept": accept
          }
  server = "http://" + config.tika_server + "/tika"
  r = requests.put(server, data=file, headers=headers)
  if r.status_code != 200 or len(r.text) < TIKA_CUTOFF:
      headers = {
          "X-Tika-PDFOcrStrategy": "ocr_only",
          "X-Tika-PDFextractInlineImages": "true",
          "Cache-Control": "no-cache",
          "accept": accept
        }
      r = requests.put(server, data=file, headers=headers)
      if r.status_code != 200:
          return False, None, Response('Tika failed with status ' + str(r.status_code), 500, mimetype='text/plain')
      else:
          return True, r.text, None
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

def get_email_html(email_id, access_token, config):
  body = {"emailid": email_id,
       "filename": 'email'}
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  p = requests.get(
    "http://" + config.ezemail_server + "/ezemail/v1/gethtmlfile/", 
    data=json.dumps(body), 
    headers=headers
  )
  if p.status_code != 200:
    app.logger.info("Email HTML request failed with status " + str(p.status_code) + ". " + p.text)
    return False, None, Response("Unable to retrieve email HTML.", status=400, mimetype='text/plain')
  return True, p.text, None

def get_email_body(req: GetEmailBodyRequest, access_token, config):
  success, html, failure_response = get_email_html(req.email_id, access_token, config)
  if not success:
    return failure_response
  else:
    return Response(html, status=200, mimetype='text/html')
  

def describe_email(req: DescribeEmailRequest, access_token, config):
  eml_file = get_eml_file(req.email_id, "default_file_name", access_token, config)
  if eml_file is None:
    return Response("Could not retrieve eml file.", status=400, mimetype='text/plain')
  try:
    success, body, response = get_email_html(req.email_id, access_token, config)
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
  # First get total
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"mailbox": 'Regular&Archive', "count": 1, 'pageSize': 1, "offset": 0}
  if req.mailbox != user_email:
    body['shared_mailbox'] = req.mailbox
  p = requests.get(
    "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
    data=json.dumps(body), 
    headers=headers
  )
  if p.status_code != 200:
    app.logger.info("getrecords request failed with status " + str(p.status_code) + ". " + p.text)
    return Response("Unable to retrieve records.", status=400, mimetype='text/plain')
  resp = p.json()
  archive_count = 0
  regular_count = 0
  for count in resp["total_count"]:
    if 'regular' in count:
      regular_count = int(count['regular'])
    if 'archive' in count:
      archive_count = int(count['archive'])
  total_count = regular_count + archive_count

  # Find total offset needed and determine what parameters are needed
  total_offset = req.items_per_page * (req.page_number - 1)
  body['count'] = req.items_per_page
  body['pageSize'] = req.items_per_page
  # If Regular has enough emails, jut pull from there
  if total_offset + req.items_per_page < regular_count:
    body['mailbox'] = 'Regular'
    body['offset'] = total_offset
    p = requests.get(
      "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
      data=json.dumps(body), 
      headers=headers
    )
    if p.status_code != 200:
      app.logger.info("getrecords request failed with status " + str(p.status_code) + ". " + p.text)
      return Response("Unable to retrieve records.", status=400, mimetype='text/plain')
    resp = p.json() 
    emails = [ EmailMetadata(
      unid=x['unid'], 
      subject=x['subject'], 
      email_id=x['emailid'], 
      received=x['received'], 
      _from=x['from'], 
      to=x['to'], 
      sent=x['sent'],
      attachments=extract_attachments_from_response(x),
      mailbox_source='regular'
    ) for x in resp['email_items']
    ]

  # If offset is larger than the number of regular items, just tak from archive
  elif total_offset > regular_count:
    body['mailbox'] = 'Archive'
    body['offset'] = total_offset - regular_count
    p = requests.get(
      "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
      data=json.dumps(body), 
      headers=headers
    )
    if p.status_code != 200:
      app.logger.info("getrecords request failed with status " + str(p.status_code) + ". " + p.text)
      return Response("Unable to retrieve records.", status=400, mimetype='text/plain')
    resp = p.json()
    emails = [ EmailMetadata(
      unid=x['unid'], 
      subject=x['subject'], 
      email_id=x['emailid'], 
      received=x['received'], 
      _from=x['from'], 
      to=x['to'], 
      sent=x['sent'],
      attachments=extract_attachments_from_response(x),
      mailbox_source='archive'
    ) for x in resp['email_items']
    ]
  # Otherwise we need some emails from both Regular and Archive
  else:
    body['mailbox'] = 'Regular'
    body['offset'] = total_offset
    p = requests.get(
      "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
      data=json.dumps(body), 
      headers=headers
    )
    if p.status_code != 200:
      app.logger.info("getrecords request failed with status " + str(p.status_code) + ". " + p.text)
      return Response("Unable to retrieve records.", status=400, mimetype='text/plain')
    resp = p.json()
    regular_emails = [ EmailMetadata(
      unid=x['unid'], 
      subject=x['subject'], 
      email_id=x['emailid'], 
      received=x['received'], 
      _from=x['from'], 
      to=x['to'], 
      sent=x['sent'],
      attachments=extract_attachments_from_response(x),
      mailbox_source='regular'
    ) for x in resp['email_items']
    ]

    # Determine how many to pull from Archive
    remaining_archive_count = req.items_per_page - len(regular_emails)
    body['mailbox'] = 'Archive'
    body['offset'] = 0
    body['count'] = remaining_archive_count
    p = requests.get(
      "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
      data=json.dumps(body), 
      headers=headers
    )
    if p.status_code != 200:
      app.logger.info("getrecords request failed with status " + str(p.status_code) + ". " + p.text)
      return Response("Unable to retrieve records.", status=400, mimetype='text/plain')
    resp = p.json()
    archive_emails = [ EmailMetadata(
      unid=x['unid'], 
      subject=x['subject'], 
      email_id=x['emailid'], 
      received=x['received'], 
      _from=x['from'], 
      to=x['to'], 
      sent=x['sent'],
      attachments=extract_attachments_from_response(x),
      mailbox_source='archive'
    ) for x in resp['email_items']
    ]
    emails = regular_emails + archive_emails

  return Response(GetEmailResponse(total_count=total_count, items_per_page=req.items_per_page, page_number=req.page_number, emails=emails).to_json(), status=200, mimetype="application/json")

def extract_attachments_from_response(ezemail_response):
  if 'attachments' not in ezemail_response:
    return []
  else:
    return [EmailAttachment(name=attachment['name'], attachment_id=attachment['attachment_id']) for attachment in ezemail_response['attachments']]

def download_attachment(req: DownloadAttachmentRequest, access_token, config):
  body = {"attachmentid": req.attachment_id, "filename": req.file_name}
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  p = requests.get(
    "http://" + config.ezemail_server + "/ezemail/v1/getattachment/", 
    data=json.dumps(body), 
    headers=headers
  )
  if p.status_code != 200:
    app.logger.info("Attachment download request failed with status " + str(p.status_code) + ". " + p.text)
    return Response("Unable to retrieve attachment.", status=400, mimetype='text/plain')
  response_headers = {'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment; filename=' + req.file_name}
  return Response(p.content, headers=response_headers, status=200)

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

def get_documentum_records(config, lan_id, items_per_page, page_number, query):
  # TODO: Improve error handling
  if query is None or len(query.strip()) == 0:
    where_clause = "where s.ERMA_DOC_CUSTODIAN = '" + lan_id + "'"
  else:
    where_clause = "where s.ERMA_DOC_CUSTODIAN = '" + lan_id + "' and s.erma_doc_title LIKE \'%" + query + '%\''
  count_sql = "select count(*) as total from (select s.ERMA_DOC_ID as erma_doc_id, MAX(s.R_CREATION_DATE) as creation_date from ECMSRMR65.ERMA_DOC_SV s " + where_clause + " group by erma_doc_id);"
  count_request = dql_request(config, count_sql, items_per_page, page_number)
  if count_request.status_code != 200:
    return Response('Documentum count request returned status ' + str(count_request.status_code) + ' and error ' + str(count_request.text), status=500, mimetype='text/plain')
  if 'entries' not in count_request.json():
    return Response(DocumentumRecordList(total=0, records=[]).to_json(), status=200, mimetype='application/json')
  total = count_request.json()['entries'][0]['content']['properties']['total']
  if total == 0:
    return Response(DocumentumRecordList(total=0, records=[]).to_json(), status=200, mimetype='application/json')
  doc_id_sql = "select erma_doc_id, creation_date from (select s.ERMA_DOC_ID as erma_doc_id, MAX(s.R_CREATION_DATE) as creation_date from ECMSRMR65.ERMA_DOC_SV s " + where_clause + " group by erma_doc_id) ORDER BY creation_date DESC;"
  r = dql_request(config, doc_id_sql, items_per_page, page_number)
  if r.status_code != 200:
    return Response('Documentum doc ID request returned status ' + str(r.status_code) + ' and error ' + str(r.text), status=500, mimetype='text/plain')
  doc_id_resp = r.json()
  if 'entries' not in doc_id_resp:
    return Response(DocumentumRecordList(total=0, records=[]).to_json(), status=200, mimetype='application/json')
  doc_ids = [x['content']['properties']['erma_doc_id'] for x in doc_id_resp['entries']]
  doc_where_clause = ' OR '.join(["erma_doc_id = '" + str(x) + "'" for x in doc_ids])
  doc_info_sql = "select s.erma_doc_sensitivity as erma_doc_sensitivity, s.R_OBJECT_TYPE as r_object_type, s.ERMA_DOC_DATE as erma_doc_date, s.ERMA_DOC_CUSTODIAN as erma_doc_custodian, s.ERMA_DOC_ID as erma_doc_id, s.R_FULL_CONTENT_SIZE as r_full_content_size, s.R_OBJECT_ID as r_object_id, s.ERMA_DOC_TITLE as erma_doc_title from ECMSRMR65.ERMA_DOC_SV s where " + doc_where_clause + ";"
  r = dql_request(config, doc_info_sql, 3*int(items_per_page), 1)
  if r.status_code != 200:
    app.logger.error(r.text)
    return Response('Documentum doc info request returned status ' + str(r.status_code) + ' and error ' + str(r.text), status=500, mimetype='text/plain')
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
  doc_list = DocumentumRecordList(total=total, records=list(sorted([DocumentumDocInfo(**x) for x in doc_info.values()], key=lambda x: x.date, reverse=True)))
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

def get_user_info(config, token_data):
  url = 'https://' + config.wam_host + '/iam/governance/scim/v1/Users?attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Department&attributes=userName&attributes=Active&attributes=displayName&filter=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Upn eq "' + token_data['email'] + '"'
  try:
    wam = requests.get(url, auth=(config.wam_username, config.wam_password))
    if wam.status_code != 200:
      return False, 'WAM request failed with status ' + str(wam.status_code) + ' and error ' + str(wam.text), None
    user_data = wam.json()['Resources'][0]
    lan_id = user_data['userName'].lower()
    display_name = user_data['displayName']
    department = user_data['urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User']['Department']
    active = user_data['active']
    if not active:
      return False, 'User is not active.', None
    return True, None, UserInfo(token_data['email'], display_name, lan_id, department)
  except:
    return False, 'WAM request failed.', None

def get_sems_special_processing(config, region):
  special_processing = requests.get('http://' + config.sems_host + '/sems-ws/outlook/getSpecialProcessing/' + region)
  if special_processing.status_code == 200:
    response_object = GetSpecialProcessingResponse([SemsSpecialProcessing(**obj) for obj in special_processing.json()])
    return Response(response_object.to_json(), status=200, mimetype='application/json')
  else:
    return Response(special_processing.text, status=special_processing.status_code, mimetype='text/plain')

def upload_documentum_record(content, documentum_metadata, config, env):
  if env == 'prod':
    ecms_host = config.documentum_prod_url
    ecms_user = config.documentum_prod_username
    ecms_password = config.documentum_prod_password
    api_key = config.documentum_prod_api_key
  else:
    ecms_host = config.documentum_dev_url
    ecms_user = config.documentum_dev_username
    ecms_password = config.documentum_dev_password
    api_key = config.documentum_dev_api_key
  
  url = "https://" + ecms_host + "/ecms/save/1.2?apiKey=" + api_key
  #app.logger.info(str({'metadata': {'properties': documentum_metadata.to_json()}}))
  files = {'metadata': json.dumps({'properties': documentum_metadata.to_json()}), 'contents': content}
  r = requests.post(url, files=files, auth=HTTPBasicAuth(ecms_user, ecms_password))
  if r.status_code == 200 and 'r_object_id' in r.json()['properties']:
    return Response(r.json(), status=200, mimetype='text/plain')
  else:
    return Response(r.text, r.status_code, mimetype='text/plain')

# Converts ECMS metadata to metadata compatible with Documentum
def convert_metadata(ecms_metadata, unid=None):
  if unid is None:
    unid = str(uuid.uuid1())
  if ecms_metadata.sensitivity.lower() == 'private':
    sensitivity = "3"
  else:
    sensitivity = ""
  schedule = ecms_metadata.record_schedule
  documentum_schedule = '_'.join([schedule.function_number, schedule.schedule_number, schedule.disposition_number])
  return DocumentumMetadata(
    r_object_type='erma_content', 
    object_name=ecms_metadata.title,
    a_application_type="Ezdesktop",
    erma_content_title=ecms_metadata.title,
    erma_content_unid="Ezdesktop_" + unid,
    # TODO: Creation date is optional, so need a different content date in this case
    erma_content_date=ecms_metadata.creation_date,
    erma_content_schedule=documentum_schedule,
    # TODO: Close date is optional, leave empty in this case
    erma_content_eventdate=ecms_metadata.close_date,
    erma_sensitivity_id=sensitivity,
    erma_custodian=ecms_metadata.custodian,
    erma_folder_path=ecms_metadata.file_path,
    erma_content_description=ecms_metadata.description,
    erma_content_creator=ecms_metadata.creator,
    erma_content_creation_date=ecms_metadata.creation_date,
    erma_content_close_date=ecms_metadata.close_date,
    erma_content_rights=ecms_metadata.rights,
    erma_content_coverage=ecms_metadata.coverage,
    erma_content_relation=ecms_metadata.relationships,
    erma_content_tags=ecms_metadata.tags
  )

def upload_documentum_email(upload_email_request, access_token, config):
  ecms_metadata = upload_email_request.metadata
  content = get_eml_file(upload_email_request.email_id, ecms_metadata.title, access_token, config)
  if content is None:
    return Response('Unable to retrieve email.', status=400, mimetype='text/plain')
  documentum_metadata = convert_metadata(ecms_metadata, upload_email_request.email_unid)
  return upload_documentum_record(content, documentum_metadata, config, upload_email_request.documentum_env)
