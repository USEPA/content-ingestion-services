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
from .models import User, RecordSubmission, db
from sqlalchemy import null
from . import model, help_item_cache, schedule_cache
import boto3

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
  r = requests.put(server, data=file, headers=headers, timeout=30)
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
  r = requests.get("http://" + config.ezemail_server + "/ezemail/v1/getemlfile", data=json.dumps(body), headers=headers, timeout=30)
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
    headers=headers,
    timeout=30
  )
  if p.status_code != 200:
    app.logger.info("Email HTML request failed with status " + str(p.status_code) + ". " + p.text)
    return False, None, Response("Unable to retrieve email HTML.", status=400, mimetype='text/plain')
  return True, p.text, None
  

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
  # First get regular total
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"mailbox": 'Regular', "count": 1, 'pageSize': 1, "offset": 0}
  if req.mailbox != user_email:
    body['shared_mailbox'] = req.mailbox
  p = requests.get(
    "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
    data=json.dumps(body), 
    headers=headers,
    timeout=60
  )
  if p.status_code != 200:
    app.logger.info("Regular getrecords count request failed for mailbox " + req.mailbox + " with status " + str(p.status_code) + ". " + p.text)
    return Response("Unable to retrieve records.", status=400, mimetype='text/plain')
  resp = p.json()
  regular_count = 0
  for count in resp["total_count"]:
    if 'regular' in count:
      regular_count = int(count['regular'])
  
  # Then get archive total and check if archive request failed
  archive_count = 0
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"mailbox": 'Archive', "count": 1, 'pageSize': 1, "offset": 0}
  if req.mailbox != user_email:
    body['shared_mailbox'] = req.mailbox
  p = requests.get(
    "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
    data=json.dumps(body), 
    headers=headers,
    timeout=60
  )
  if p.status_code != 200:
    app.logger.info("Archive getrecords count request failed for mailbox " + req.mailbox + " with status " + str(p.status_code) + ". " + p.text)
  else:
    resp = p.json()
  
    for count in resp["total_count"]:
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
      headers=headers,
      timeout=60
    )
    if p.status_code != 200:
      app.logger.info("Regular getrecords request failed for mailbox " + req.mailbox + " with status " + str(p.status_code) + ". " + p.text)
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

  # If offset is larger than the number of regular items, just take from archive
  elif total_offset > regular_count:
    if archive_count == 0:
      emails = [] 
    else:
      body['mailbox'] = 'Archive'
      body['offset'] = total_offset - regular_count
      p = requests.get(
        "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
        data=json.dumps(body), 
        headers=headers,
        timeout=60
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
      headers=headers,
      timeout=60
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
    if archive_count == 0:
      archive_emails = [] 
    else:
      remaining_archive_count = req.items_per_page - len(regular_emails)
      body['mailbox'] = 'Archive'
      body['offset'] = 0
      body['count'] = remaining_archive_count
      p = requests.get(
        "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
        data=json.dumps(body), 
        headers=headers,
        timeout=60
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

def mark_saved(req: MarkSavedRequest, access_token, config):
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"emailid": req.email_id}
  if req.sensitivity.lower() == 'private':
    body['sensitivityid'] = 3
  p = requests.post(
    "http://" + config.ezemail_server + "/ezemail/v1/setcategory", 
    json=body, 
    headers=headers,
    timeout=30
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
    headers=headers,
    timeout=30
  )
  if p.status_code != 204:
    return Response("Unable to remove Record category.", status=400, mimetype='text/plain')
  else:
    return Response(StatusResponse(status="OK", reason="Email with id " + req.email_id + " is no longer categorized as a record.").to_json(), status=200, mimetype="application/json")

def dql_request(config, sql, items_per_page, page_number, env):
  if env == 'prod':
    ecms_host = config.documentum_prod_url
    ecms_user = config.documentum_prod_username
    ecms_password = config.documentum_prod_password
  else:
    ecms_host = config.documentum_dev_url
    ecms_user = config.documentum_dev_username
    ecms_password = config.documentum_dev_password
  url = "https://" + ecms_host + "/dctm-rest/repositories/ecmsrmr65?items-per-page=" + str(items_per_page) + "&page=" + str(page_number) + "&dql=" + urllib.parse.quote(sql)
  headers = {'cache-control': 'no-cache'}
  r = requests.get(url, headers=headers, auth=(ecms_user,ecms_password), timeout=30)
  return r

def get_where_clause(lan_id, query, request_type='doc'):
  filter_var = 'erma_doc_custodian'
  if query is not None:
    query = query.lower()
  if request_type == 'content':
      filter_var = 'erma_custodian'
  if query is None or len(query.strip()) == 0:
      where = "where s." + filter_var + " = '" + lan_id + "'"
  elif request_type == 'content':
      where = "where s." + filter_var + " = '" + lan_id + "' and (LOWER(s.erma_doc_title) LIKE \'%" + query + '%\'' + " or LOWER(s.erma_content_title) LIKE \'%" + query + '%\')'
  else:
      where = "where s." + filter_var + " = '" + lan_id + "' and LOWER(s.erma_doc_title) LIKE \'%" + query + '%\''
  if request_type == 'doc':
      where = where + " and s.r_object_type != 'erma_content'"
  return where
    
def get_erma_content_count(config, lan_id, query, env):
  where_clause = get_where_clause(lan_id, query, 'content')
  count_sql = "select count(distinct s.r_object_id) as total from erma_content s " + where_clause + ";"
  count_request = dql_request(config, count_sql, 10, 1, env)
  return count_request

def get_erma_noncontent_count(config, lan_id, query, env):
  where_clause = get_where_clause(lan_id, query, 'doc')
  count_sql = "select count(distinct s.erma_doc_id) as total from erma_doc s " + where_clause + ";"
  count_request = dql_request(config, count_sql, 10, 1, env)
  return count_request

# Returns a triple (success, data, response)
# If some intermediate query fails, we se success to false and return a response
# Otherwise success is true and we return the records pulled
def get_erma_content(config, lan_id, items_per_page, page_number, query, env):
  where_clause = get_where_clause(lan_id, query, 'content')
  doc_info_sql = ("select s.r_object_id as r_object_id, "
                  "s.a_content_type as content_type, "
                  "s.r_creation_date as upload_date,"
                  "s.r_full_content_size as r_full_content_size, "
                  "s.erma_doc_sensitivity as sensitivity, "
                  "s.erma_custodian as custodian, "
                  "s.erma_content_title as title, "
                  "s.erma_folder_path as file_path, "
                  "s.erma_content_description as description, "
                  "s.erma_content_schedule as record_schedule, "
                  "s.erma_content_creator as creator, " 
                  "s.erma_content_creation_date as creation_date, "
                  "s.erma_content_close_date as close_date, "
                  "s.erma_content_rights as rights, "
                  "s.erma_content_coverage as coverage, "
                  "s.erma_content_relation as relationships, "
                  "s.erma_content_tags as tags "
                  "from erma_content s " + where_clause + " order by s.r_creation_date desc;" )
  r = dql_request(config, doc_info_sql, items_per_page, page_number, env)
  if r.status_code != 200:
      return False, None, Response('Documentum doc info request returned status ' + str(r.status_code) + ' and error ' + str(r.text), status=500, mimetype='text/plain')
  if 'entries' not in r.json():
      return True, [], None
  doc_info = []
  for doc in r.json()['entries']:
      properties = doc['content']['properties']
      object_id = properties['r_object_id']
      size = properties['r_full_content_size']
      if properties['sensitivity'] == '3':
          sensitivity = 'private'
      else:
          sensitivity = 'shared'
      if properties['content_type'] in ['html', 'xml', 'eml']:
          doc_type = 'email'
      else:
          doc_type = 'document'
      split_sched = properties['record_schedule'].split('_')
      if len(split_sched) != 3:
        split_sched = ['','','']
      doc_data = {
          "doc_id": object_id,
          "size": size,
          "object_ids": [object_id],
          "title": properties['title'],
          "date": properties['creation_date'],
          "sensitivity": sensitivity,
          "custodian": properties['custodian'],
          "doc_type": doc_type,
          "upload_date": properties['upload_date'],
          "metadata": {
              'file_path': properties['file_path'],
              'custodian': properties['custodian'],
              'title': properties['title'],
              'description': properties['description'],
              'record_schedule': {
                  'function_number': split_sched[0],
                  'schedule_number': split_sched[1],
                  'disposition_number': split_sched[2]
              },
              'creator': properties['creator'],
              'creation_date': properties['creation_date'],
              'close_date': properties['close_date'],
              'sensitivity': properties['sensitivity'],
              'rights': properties['rights'],
              'coverage': properties['coverage'],
              'relationships': properties['relationships'],
              'tags': properties['tags'],
              'user_activity': None
          }
      }
      doc_info.append(doc_data)
  doc_list = [DocumentumDocInfo(**x) for x in doc_info]
  return True, doc_list, None 

def get_erma_noncontent(config, lan_id, items_per_page, page_number, query, env):
  where_clause = get_where_clause(lan_id, query, 'doc')
  doc_id_sql = "select erma_doc_id, creation_date from (select s.ERMA_DOC_ID as erma_doc_id, MAX(s.R_CREATION_DATE) as creation_date from erma_doc s " + where_clause + " group by erma_doc_id) ORDER BY creation_date DESC;"
  r = dql_request(config, doc_id_sql, items_per_page, page_number, env)
  if r.status_code != 200:
      return False, None, Response('Documentum doc ID request returned status ' + str(r.status_code) + ' and error ' + str(r.text), status=500, mimetype='text/plain')
  doc_id_resp = r.json()
  if 'entries' not in doc_id_resp:
      return True, [], None
  doc_ids = [x['content']['properties']['erma_doc_id'] for x in doc_id_resp['entries']]
  doc_where_clause = ' OR '.join(["erma_doc_id = '" + str(x) + "'" for x in doc_ids])
  doc_info_sql = "select s.erma_doc_sensitivity as sensitivity, s.r_creation_date as upload_date, s.R_OBJECT_TYPE as r_object_type, s.ERMA_DOC_DATE as erma_doc_date, s.ERMA_DOC_CUSTODIAN as erma_doc_custodian, s.ERMA_DOC_ID as erma_doc_id, s.R_FULL_CONTENT_SIZE as r_full_content_size, s.R_OBJECT_ID as r_object_id, s.ERMA_DOC_TITLE as erma_doc_title from ECMSRMR65.ERMA_DOC_SV s where " + doc_where_clause + " order by s.r_creation_date desc;"
  r = dql_request(config, doc_info_sql, items_per_page, page_number, env)
  if r.status_code != 200:
      return False, None, Response('Documentum doc info request returned status ' + str(r.status_code) + ' and error ' + str(r.text), status=500, mimetype='text/plain')
  doc_info = {}
  for doc in r.json()['entries']:
      properties = doc['content']['properties']
      doc_id = properties['erma_doc_id']
      object_id = properties['r_object_id']
      size = properties['r_full_content_size']
      if properties['sensitivity'] == '3':
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
              "doc_type": doc_type,
              "upload_date": properties['upload_date'],
              "metadata": None
          }
  return True, [DocumentumDocInfo(**x) for x in doc_info.values()], None

def get_documentum_records(config, lan_id, items_per_page, page_number, query, env):
  # First get count of erma_content records
  content_count = get_erma_content_count(config, lan_id, query, env)
  if content_count.status_code != 200:
      return Response('Documentum content count request returned status ' + str(content_count.status_code) + ' and error ' + str(content_count.text), status=500, mimetype='text/plain')
  content_count = int(content_count.json()['entries'][0]['content']['properties']['total'])
  # Count of records which are not erma_content (erma_doc or erma_mail)
  noncontent_count = get_erma_noncontent_count(config, lan_id, query, env)
  if noncontent_count.status_code != 200:
      return Response('Documentum noncontent count request returned status ' + str(noncontent_count.status_code) + ' and error ' + str(noncontent_count.text), status=500, mimetype='text/plain')
  noncontent_count = int(noncontent_count.json()['entries'][0]['content']['properties']['total'])

  # Determine if only need erma_content, only need erma_doc, or both
  total_count = content_count + noncontent_count
  offset = items_per_page * (page_number - 1)

  # Case where we need only pull erma_content
  if content_count >= (offset + items_per_page):
    success, records, response = get_erma_content(config, lan_id, items_per_page, page_number, query, env)
    if not success:
        return response
    return Response(DocumentumRecordList(records=records, total=total_count).to_json(), status=200, mimetype='application/json')

  # Case where we need only pull erma_doc/email
  elif content_count < offset:
    noncontent_offset = offset - content_count
    starting_page = int(noncontent_offset / items_per_page) + 1
    page_offset = noncontent_offset - (starting_page - 1) * items_per_page
    success, records, response = get_erma_noncontent(config, lan_id, items_per_page, starting_page, query, env)
    if not success:
        return response
    second_success, second_records, second_response = get_erma_noncontent(config, lan_id, items_per_page, starting_page + 1, query, env)
    if not second_success:
        return second_response
    sliced_records = records[page_offset:] + second_records[:page_offset]
    return Response(DocumentumRecordList(records=sliced_records, total=total_count).to_json(), status=200, mimetype='application/json')

  # Case where we are paging across the boundary
  else:
      success, records, response = get_erma_content(config, lan_id, items_per_page, page_number, query, env)
      if not success:
        return response
      second_success, second_records, second_response = get_erma_noncontent(config, lan_id, items_per_page, 1, query, env)
      if not second_success:
        return second_response
      sliced_records = records + second_records[0:(items_per_page - len(records))]
      return Response(DocumentumRecordList(records=sliced_records, total=total_count).to_json(), status=200, mimetype='application/json')
      

def object_id_is_valid(config, object_id):
  return re.fullmatch('[a-z0-9]{16}', object_id) is not None and object_id[2:8] == config.records_repository_id

def download_documentum_record(config, user_info, object_ids, env):
  lan_id = user_info.lan_id
  if env == 'prod':
    ecms_host = config.documentum_prod_url
    ecms_user = config.documentum_prod_username
    ecms_password = config.documentum_prod_password
  else:
    ecms_host = config.documentum_dev_url
    ecms_user = config.documentum_dev_username
    ecms_password = config.documentum_dev_password
  # Validate object_ids
  for object_id in object_ids:
    valid = object_id_is_valid(config, object_id)
    if not valid:
      return Response('Object ID invalid: ' + object_id, status=400, mimetype='text/plain')
  doc_where_clause = ' OR '.join(["s.r_object_id = '" + str(x) + "'" for x in object_ids])
  doc_info_sql = "select s.ERMA_CUSTODIAN as erma_doc_custodian, r_object_id, r_object_type from erma_content s where " + doc_where_clause + ";"
  # This gives some buffer, even though there should be exactly len(object_ids) items to recover
  r = dql_request(config, doc_info_sql, 2*len(object_ids), 1, env)
  entries = r.json()['entries']
  if r.status_code != 200:
    app.logger.error(r.text)
    return Response('Documentum content info request returned status ' + str(r.status_code), status=500, mimetype='text/plain')
  remaining_ids = set(object_ids) - set([doc['content']['properties']['r_object_id'] for doc in r.json()['entries']])
  if len(remaining_ids) > 0:
    remaining_where_clause = ' OR '.join(["s.r_object_id = '" + str(x) + "'" for x in remaining_ids])
    doc_info_sql = "select s.ERMA_DOC_CUSTODIAN as erma_doc_custodian, r_object_id, r_object_type from erma_doc s where " + remaining_where_clause + ";"
    remaining_r = dql_request(config, doc_info_sql, 2*len(object_ids), 1, env)
    if remaining_r.status_code != 200:
      app.logger.error(remaining_r.text)
      return Response('Documentum doc info request returned status ' + str(r.status_code), status=500, mimetype='text/plain')
    for x in remaining_r.json()['entries']:
      entries.append(x)
  missing_ids = set(object_ids) - set([doc['content']['properties']['r_object_id'] for doc in entries])
  if len(missing_ids) != 0:
    return Response('The following object_ids could not be found: ' + ', '.join(list(missing_ids)), status=400, mimetype='text/plain')
  # TODO: Reenable custodian validation
  for doc in entries:
    if doc['content']['properties'].get('erma_doc_custodian', '') != lan_id:
      return Response('User ' + lan_id + ' is not the custodian of all files requested.', status=401, mimetype='text/plain')
  
  hrefs = ['https://' + ecms_host + '/dctm-rest/repositories/ecmsrmr65/objects/' + obj for obj in object_ids]
  data = {'hrefs': list(set(hrefs))}
  archive_url = 'https://' + ecms_host + '/dctm-rest/repositories/ecmsrmr65/archived-contents'
  post_headers = {
    'cache-control': 'no-cache',
    'Content-Type': 'application/vnd.emc.documentum+json'
  }
  archive_req = requests.post(archive_url, headers=post_headers, json=data, auth=(ecms_user,ecms_password), timeout=30)
  if archive_req.status_code != 200:
    app.logger.error(r.text)
    return Response('Documentum archive request returned status ' + str(archive_req.status_code), status=500, mimetype='text/plain')
  b = io.BytesIO(archive_req.content)
  safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '7', config)
  return send_file(b, mimetype='application/zip', as_attachment=True, attachment_filename='ecms_download.zip')

def get_badges(config, employee_number):
  if employee_number is None:
    return []
  params={'type':'badges', 'employee_id':employee_number, 'api_key':config.patt_api_key}
  url = 'https://' + config.patt_host + '/app/mu-plugins/pattracking/includes/admin/pages/games/receiver.php'
  r = requests.post(url, params=params)
  if r.status_code != 200:
    return []
  else:
    return [BadgeInfo(badge_title=x['badge_title'], badge_description=x['badge_description'], badge_image=x['badge_image']) for x in r.json()]

def get_profile(config, employee_number):
  if employee_number is None:
    return None
  params={'type':'profile', 'employee_id':employee_number, 'api_key':config.patt_api_key}
  url = 'https://' + config.patt_host + '/app/mu-plugins/pattracking/includes/admin/pages/games/receiver.php'
  r = requests.post(url, params=params)
  
  if r.status_code != 200 or len(r.json()) == 0:
    return None
  else:
    profile = r.json()[0]
    return ProfileInfo(points=profile['points'], level=profile['level'], office_rank=profile['office_rank'], overall_rank=profile['overall_rank'])
    
def get_user_settings(lan_id):
    user = User.query.filter_by(lan_id = lan_id).all()
    if len(user) == 0:
        return default_settings
    else:
        user = user[0]
        settings = user.user_settings
        if len(settings) == 0:
            return default_settings
        else:
            settings = settings[0]
            return UserSettings(preferred_system=settings.system, default_edit_mode=settings.default_edit_mode)

def get_user_info(config, token_data):
  # Handle service accounts separately
  if token_data['email'][:4].lower() == 'svc_':
    return True, None, UserInfo(token_data['email'], token_data['email'], token_data['email'].split('@')[0], 'SERVICE_ACCOUNT', '', '', [], None, default_settings)
  url = 'https://' + config.wam_host + '/iam/governance/scim/v1/Users?attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Department&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Company&attributes=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:PARENTORGCODE&attributes=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber&attributes=userName&attributes=Active&attributes=displayName&filter=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Upn eq "' + token_data['email'] + '"'
  try:
    wam = requests.get(url, auth=(config.wam_username, config.wam_password), timeout=30)
    if wam.status_code != 200:
      return False, 'WAM request failed with status ' + str(wam.status_code) + ' and error ' + str(wam.text), None
    user_data = wam.json()['Resources'][0]
    lan_id = user_data['userName'].lower()
    display_name = user_data['displayName']
    department = user_data.get('urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User', {}).get('Department', None)
    enterprise_department = user_data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User', {}).get('department', None)
    employee_number = user_data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User', {}).get('employeeNumber', None)
    company = user_data.get('urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User', {}).get('Company', None)
    if enterprise_department is None:
      enterprise_department = company
    active = user_data['active']
    if not active:
      return False, 'User is not active.', None
  except:
    return False, 'WAM request failed.', None
  try:
    badges = get_badges(config, employee_number)
    profile = get_profile(config, employee_number)
  except:
    badges=[]
    profile=None
    app.logger.info('Profile requests failed for ' + token_data['email'])
  try:
    user_settings = get_user_settings(lan_id)
  except:
    user_settings = default_settings
    app.logger.info('Preferred system database read failed for ' + token_data['email'])
  return True, None, UserInfo(token_data['email'], display_name, lan_id, department, enterprise_department, employee_number, badges, profile, user_settings)

def get_sems_special_processing(config, region):
  special_processing = requests.get('http://' + config.sems_host + '/sems-ws/outlook/getSpecialProcessing/' + region, timeout=10)
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
  files = {'metadata': json.dumps({'properties': documentum_metadata.to_dict()}), 'contents': content}
  r = requests.post(url, files=files, auth=HTTPBasicAuth(ecms_user, ecms_password), timeout=30)
  if r.status_code == 201 and 'r_object_id' in r.json()['properties']:
    return True, r.json()['properties']['r_object_id'], None
  else:
    return False, None, Response(r.text, r.status_code, mimetype='text/plain')

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
    object_name=ecms_metadata.file_path,
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

def upload_documentum_email(upload_email_request, access_token, user_info, config):
  ecms_metadata = upload_email_request.metadata
  content = get_eml_file(upload_email_request.email_id, ecms_metadata.title, access_token, config)
  if content is None:
    return Response('Unable to retrieve email.', status=400, mimetype='text/plain')
  documentum_metadata = convert_metadata(ecms_metadata, upload_email_request.email_unid)
  success, r_object_id, resp = upload_documentum_record(content, documentum_metadata, config, upload_email_request.documentum_env)
  if not success:
    return resp 
  save_req = MarkSavedRequest(email_id = upload_email_request.email_id, sensitivity=ecms_metadata.sensitivity)
  save_resp = mark_saved(save_req, access_token, config)
  if save_resp.status != '200 OK':
    return save_resp

  success, response = add_submission_analytics(upload_email_request.user_activity, ecms_metadata.record_schedule, user_info.lan_id, r_object_id, None)
  if not success:
    return response
  else:
    log_upload_activity(user_info, upload_email_request.user_activity, ecms_metadata, config)
    return Response(StatusResponse(status='OK', reason='File successfully uploaded.').to_json(), status=200, mimetype='application/json')
  
def simplify_sharepoint_record(raw_rec, sensitivity):
  detected_sched = None
  mapping = schedule_cache.get_schedule_mapping()
  for item in raw_rec['webUrl'].split('/'):
    if item in mapping:
      detected_sched = mapping[item]
      break
  return SharepointRecord(
    web_url = raw_rec['webUrl'],
    records_status = raw_rec['listItem']['fields'].get('Records_x0020_Status', None),
    sensitivity = sensitivity,
    name = raw_rec['name'],
    drive_item_id = raw_rec['id'],
    created_date = raw_rec['createdDateTime'],
    last_modified_date = raw_rec['lastModifiedDateTime'],
    detected_schedule = detected_sched
  )

def check_or_create_records_folder(access_token):
  headers = {'Authorization': 'Bearer ' + access_token, 'Content-Type':'application/json'}
  r = requests.get("https://graph.microsoft.com/v1.0/me/drive/root/children/?$filter=name eq 'EPA Records'", headers=headers, timeout=10)
  if r.status_code != 200:
    return False, Response('Records folder request failed. ' + r.text, status=500, mimetype='text/plain')
  values = r.json().get('value', [])
  if len(values) == 0:
    # If folder is not present, create it
    body = {
      "name": "EPA Records",
      "folder": {},
      "@microsoft.graph.conflictBehavior": "fail"
    }
    r = requests.post("https://graph.microsoft.com/v1.0/me/drive/root/children/", json=body, headers=headers, timeout=10)
    if r.status_code == 201:
      return True, None
    elif r.status_code == 409:
      if r.json().get('error', {}).get('code', '') == 'nameAlreadyExists':
        return True, None
      else:
        app.logger.error('Failed to create EPA Records folder with status ' + str(r.status_code))
        app.logger.error(r.text)
        return False, Response('Failed to create EPA Records folder.', status=500, mimetype='text/plain')
    else:
      app.logger.error('Failed to create EPA Records folder with status ' + str(r.status_code))
      app.logger.error(r.text)
      return False, Response('Failed to create EPA Records folder.', status=500, mimetype='text/plain')
  else:
    return True, None

# TODO: handle case when shared/private folders contain more than 5000 records.
def list_sharepoint_records(req: GetSharepointRecordsRequest, access_token):
  success, response = check_or_create_records_folder(access_token)
  if not success:
    return response
  page_number = int(req.page_number)
  items_per_page = int(req.items_per_page)
  if page_number <= 0:
    return Response('Invalid page number. ', status=400, mimetype='text/plain')
  if items_per_page <= 0:
    return Response('Items per page must be > 0.', status=400, mimetype='text/plain')
  all_records = []
  # Get shared records
  headers = {'Authorization': 'Bearer ' + access_token}
  shared = requests.get("https://graph.microsoft.com/v1.0/me/drive/root:/EPA Records:/children/?$expand=listitem", headers=headers, timeout=10)
  if shared.status_code != 200:
    return Response('Failed to retrieve shared OneDrive items.', status=500, mimetype='text/plain')
  shared_items = shared.json()['value']
  for doc in shared_items:
    all_records.append(simplify_sharepoint_record(doc, 'Shared'))
  filtered_records = list(filter(lambda x: x.records_status == 'Pending', all_records))
  filtered_records = sorted(filtered_records, key=lambda x: x.last_modified_date, reverse=True)
  total_count = len(filtered_records)
  paged_records = filtered_records[(page_number - 1) * items_per_page : page_number * items_per_page]
  response = SharepointListResponse(records=paged_records, total_count=total_count)
  return Response(response.to_json(), status=200, mimetype='application/json')

def sharepoint_record_prediction(req: SharepointPredictionRequest, access_token, c):
  headers = {'Authorization': 'Bearer ' + access_token}
  url = 'https://graph.microsoft.com/v1.0/me/drive/items/' + req.drive_item_id
  r = requests.get(url, headers=headers, timeout=30)
  if r.status_code != 200:
    app.logger.error('Unable to find OneDrive item: ' + r.text)
    return Response('Unable to find OneDrive item: ' + str(r.text), status=400, mimetype='application/json')
  download_url = r.json()['@microsoft.graph.downloadUrl']
  content_req = requests.get(download_url, timeout=30)
  if content_req.status_code != 200:
    return Response('Content request failed with status ' + str(content_req.status_code), status=500, mimetype='application/json')
  content = content_req.content
  success, text, response = tika(content, c, extraction_type='text')
  if not success:
      return response
  predicted_schedules, default_schedule = model.predict(text, 'document', PredictionMetadata(req.file_name, req.department))
  predicted_title = mock_prediction_with_explanation
  predicted_description = mock_prediction_with_explanation
  prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule)
  return Response(prediction.to_json(), status=200, mimetype='application/json')

def upload_sharepoint_record(req: SharepointUploadRequest, access_token, user_info, c):
  headers = {'Authorization': 'Bearer ' + access_token}
  url = 'https://graph.microsoft.com/v1.0/me/drive/items/' + req.drive_item_id + '?expand=listItem,sharepointIds'
  r = requests.get(url, headers=headers, timeout=30)
  if r.status_code != 200:
    app.logger.error('Unable to find OneDrive item: ' + r.text)
    return Response('Unable to find OneDrive item: ' + str(r.text), status=400, mimetype='application/json')
  drive_item = r.json()
  download_url = drive_item['@microsoft.graph.downloadUrl']
  content_req = requests.get(download_url, timeout=30)
  if content_req.status_code != 200:
    app.logger.error('Content request failed: ' + r.text)
    return Response('Content request failed with status ' + str(content_req.status_code), status=500, mimetype='text/plain')
  content = content_req.content
  documentum_metadata = convert_metadata(req.metadata, req.drive_item_id)
  success, r_object_id, resp = upload_documentum_record(content, documentum_metadata, c, req.documentum_env)
  if not success:
    return resp

  ## If successful, update Sharepoint metadata
  site_id = drive_item['sharepointIds']['siteId']
  list_id = drive_item['sharepointIds']['listId']
  list_item_id = drive_item['sharepointIds']['listItemId']
  status = "Saved to ECMS Staging"
  success, response = update_sharepoint_record_status(site_id, list_id, list_item_id, status, access_token)
  if not success:
    return response 
  
  ## Add submission analytics to table
  ## TODO: find correct path to id in upload_resp
  success, response = add_submission_analytics(req.user_activity, req.metadata.record_schedule, user_info.lan_id, r_object_id, None)
  if not success:
    return response
  else:
    log_upload_activity(user_info, req.user_activity, req.metadata, c)
    return Response(StatusResponse(status='OK', reason='File successfully uploaded.').to_json(), status=200, mimetype='application/json')

def upload_sharepoint_batch(req: SharepointBatchUploadRequest, user_info, c):
  ## Save submission to S3
  try:
    s3 = boto3.resource('s3')
    current_time = datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
    file_path = user_info.lan_id + '_' + current_time + '.json'
    object = s3.Object(c.bucket_name, 'pending_uploads/' + file_path)
    object.put(Body=req.to_json())
  except:
    return Response(StatusResponse(status='Failed', reason='Failed to upload batch to S3.').to_json(), status=500, mimetype='application/json')
  return Response(StatusResponse(status='OK', reason='Uploaded batch to S3.').to_json(), status=200, mimetype='application/json')

def sched_to_string(sched):
  return '-'.join([sched.function_number, sched.schedule_number, sched.disposition_number])

def add_submission_analytics(data: SubmissionAnalyticsMetadata, selected_schedule, lan_id, documentum_id, nuxeo_id):
  # Handle nulls for documentum and nuxeo ids
  if documentum_id is None:
    doc_id = null()
  else:
    doc_id = documentum_id
  if nuxeo_id is None:
    nux_id = null()
  else:
    nux_id = nuxeo_id
  
  if data.default_schedule is None:
    default_schedule = null()
  else:
    default_schedule = sched_to_string(data.default_schedule)

  # Find user in DB or add user
  user = User.query.filter_by(lan_id = lan_id).all()
  if len(user) == 0:
      user = User(lan_id = lan_id)
      db.session.add(user)
  else:
      user = user[0]
  
  predicted_schedule_one = null()
  predicted_probability_one = null()
  predicted_schedule_two = null()
  predicted_probability_two = null()
  predicted_schedule_three = null()
  predicted_probability_three = null()
  if data.predicted_schedules is not None:
    sorted_predictions = list(sorted(data.predicted_schedules, key=lambda x: x.probability, reverse=True))
    if len(sorted_predictions) > 0:
      predicted_schedule_one = sched_to_string(sorted_predictions[0].schedule)
      predicted_probability_one = sorted_predictions[0].probability
    
    if len(sorted_predictions) > 1:
      predicted_schedule_two = sched_to_string(sorted_predictions[1].schedule)
      predicted_probability_two = sorted_predictions[1].probability
    
    if len(sorted_predictions) > 2:
      predicted_schedule_three = sched_to_string(sorted_predictions[2].schedule)
      predicted_probability_three = sorted_predictions[2].probability
    
  submission = RecordSubmission(
    arms_documentum_id = doc_id,
    arms_nuxeo_id = nux_id,
    predicted_schedule_one = predicted_schedule_one,
    predicted_schedule_one_probability = predicted_probability_one,
    predicted_schedule_two = predicted_schedule_two,
    predicted_schedule_two_probability = predicted_probability_two,
    predicted_schedule_three = predicted_schedule_three,
    predicted_schedule_three_probability = predicted_probability_three,
    default_schedule = default_schedule,
    selected_schedule = sched_to_string(selected_schedule),
    used_modal_form = data.used_modal_form,
    used_recommended_schedule = data.used_recommended_schedule,
    used_schedule_dropdown = data.used_schedule_dropdown,
    used_default_schedule = data.used_default_schedule,
    used_favorite_schedule = data.used_favorite_schedule,
    user = user
  )

  user.submissions.append(submission)
  
  try:
    db.session.commit()
    return True, None
  except:
    return False, Response("Error committing submission analytics.", status=500, mimetype="text/plain")


def update_sharepoint_record_status(site_id, list_id, item_id, status, access_token):
  url = 'https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items/{item_id}/fields'.format(site_id = site_id, list_id = list_id, item_id = item_id)
  headers = {'Authorization': 'Bearer ' + access_token}
  data = {"Records_x0020_Status": status}
  update_req = requests.patch(url, json=data, headers=headers, timeout=30)
  if update_req.status_code != 200:
    app.logger.error('Unable to update item with item_id = ' + item_id + ': ' + update_req.text)
    return False, Response('Unable to update item with item_id = ' + item_id, status=500, mimetype='text/plain')
  else:
    return True, None

def get_help_item(req: GetHelpItemRequest):
  items = help_item_cache.get_help_items()
  for item in items:
    if item.name == req.name:
      return Response(item.to_json(), status=200, mimetype='application/json')
  return Response('Item not found.', status=400, mimetype='text/plain')

def get_all_help_items():
  items = AllHelpItemsResponse(help_items=help_item_cache.get_help_items())
  return Response(items.to_json(), status=200, mimetype='application/json')

def submit_sems_email(req: SEMSEmailUploadRequest, config):
  data = req.to_json()
  r = requests.post('http://' + config.sems_host + '/sems-ws/outlook/saveMails', data=data, timeout=10)
  if r.status_code != 200:
    return Response('Failed to send email to SEMS.', status=500, mimetype='text/plain')
  return Response(r.json(), status=200, mimetype='application/json')

def log_upload_activity(user_info, user_activity, metadata, config):
  safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '3', config)
  if not user_activity.used_default_schedule or user_activity.used_schedule_dropdown or user_activity.used_recommended_schedule:
      safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '4', config)
  if len(metadata.description) > 0 or len(metadata.close_date) > 0 or metadata.rights is not None or metadata.coverage is not None or metadata.relationships is not None or metadata.tags is not None:
      safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '6', config)

def safe_user_activity_request(employee_id, lan_id, office_code, event_id, config):
  try:
    activity_request = LogActivityRequest(employee_id=employee_id, lan_id=lan_id, office_code=office_code, event_id=event_id)
    success, error_status = user_activity_request(activity_request, config)
    if not success:
        app.logger.info('Failed to log user activity for ' + lan_id + '. Activity request failed with status ' + str(error_status))
  except:
    app.logger.info('Failed to log user activity for ' + lan_id)

def user_activity_request(req: LogActivityRequest, config):
  params={'employee_id':req.employee_id, 'lan_id':req.lan_id, 'office_code':req.office_code, 'event_id':req.event_id, 'api_key':config.patt_api_key}
  url = 'https://' + config.patt_host + '/app/mu-plugins/pattracking/includes/admin/pages/games/activity.php'
  r = requests.post(url, params=params)
  if r.status_code == 200:
    return True, None
  else:
    return False, r.status_code

def log_user_activity(req: LogActivityRequest, config):
  success, error_status = user_activity_request(req, config)
  if not success:
    return Response('Failed to log activity with status ' + str(error_status), status=400, mimetype='text/plain')
  else:
    return Response(StatusResponse(status='OK', reason='Successfully logged user activity.').to_json(), status=200, mimetype='application/json')