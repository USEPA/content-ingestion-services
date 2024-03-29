import requests
from requests.auth import HTTPBasicAuth
from .data_classes import *
import json 
from flask import Response, current_app as app, send_file, g
import urllib 
import io
import re
import uuid
from .models import User, RecordSubmission, BatchUpload, BatchUploadStatus, BatchUploadSource, DelegationRule, db
from sqlalchemy import null
from . import model, help_item_cache, schedule_cache, keyword_extractor, identifier_extractor, capstone_detector
from xhtml2pdf import pisa
from email import policy 
from email.parser import BytesParser
import hashlib
import base64
import datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import boto3
import mimetypes
from bs4 import BeautifulSoup
import traceback
from exchangelib import Account, OAuth2Credentials, Credentials, Configuration, DELEGATE, Folder, IMPERSONATION, OAUTH2, Identity
from oauthlib.oauth2 import OAuth2Token
import pytz

TIKA_CUTOFF = 20
TIKA_TEXT_UPPER_LIMIT = 10000
ARMS_ARCHIVE_FOLDER_NAME = 'ARMS Archive'
ARMS_SYNC_FOLDER_NAME = 'ARMS File Sync'

def tika(file, config):
  headers = {
            "X-Tika-PDFOcrStrategy": "auto",
            "X-Tika-PDFextractInlineImages": "false",
            "Cache-Control": "no-cache",
            "accept": 'application/json'
          }
  server = "http://" + config.tika_server + "/rmeta/text"
  try:
    r = requests.put(server, data=file, headers=headers, timeout=30)
  except:
    app.logger.error(traceback.format_exc())
    return False, None, Response(StatusResponse(status='Failed', reason='Could not connect to Tika server', request_id=g.get('request_id', None)).to_json(), 500, mimetype='application/json')

  if r.status_code != 200 or len(r.json()[0].get('X-TIKA:content','')) < TIKA_CUTOFF:
      headers = {
          "X-Tika-PDFOcrStrategy": "ocr_only",
          "X-Tika-PDFextractInlineImages": "true",
          "Cache-Control": "no-cache",
          "accept": 'application/json'
        }
      r = requests.put(server, data=file, headers=headers, stream=True)
      if r.status_code != 200:
          return False, None, Response(StatusResponse(status='Failed', reason='Tika failed with status ' + str(r.status_code), request_id=g.get('request_id', None)).to_json(), 500, mimetype='application/json')
  
  try:
    result = r.json()[0]
    text = result.get('X-TIKA:content','')
    is_encrypted = result.get('pdf:encrypted', 'false') == 'true'
    cui_categories = []
    for k, v in result.items():
      if 'MSIP_Label_' in k and '_Name' in k:
        cui_categories.append(v)
    tika_result = TikaResult(text=text, is_encrypted=is_encrypted, cui_categories=cui_categories)
  except:
    app.logger.error(traceback.format_exc())
    return False, None, Response(StatusResponse(status='Failed', reason='Failed to parse Tika result.', request_id=g.get('request_id', None)).to_json(), 500, mimetype='application/json')

  return True, tika_result, None

def get_eml_file_archive(email_id, mailbox, access_token):
  token = OAuth2Token({'access_token':access_token})
  creds = OAuth2Credentials(
    '','', access_token=token,
  )
  config = Configuration(server='outlook.office.com', credentials=creds, auth_type=OAUTH2)
  account = Account(primary_smtp_address=mailbox, config=config, autodiscover=False, access_type=DELEGATE, default_timezone=pytz.UTC)
  inbox = account.archive_root / 'Top of Information Store'
  email = inbox.get(id=email_id)
  return email.mime_content

def get_eml_file(email_id, emailsource, mailbox, access_token):

  if emailsource.lower() == 'archive':
    return get_eml_file_archive(email_id, mailbox, access_token)
  else:
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
    url = "https://graph.microsoft.com/v1.0/users/" + mailbox + "/messages/" + email_id + "/$value"
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 200:
        return r.content
    else:
      app.logger.error('Get EML file request with graph, ended with status ' + str(r.status_code) + '. Response: ' + r.text)
      return None

def get_email_text_archive(email_id, mailbox, access_token):
  token = OAuth2Token({'access_token':access_token})
  creds = OAuth2Credentials(
    '','', access_token=token,
  )
  config = Configuration(server='outlook.office.com', credentials=creds, auth_type=OAUTH2)
  account = Account(primary_smtp_address=mailbox, config=config, autodiscover=False, access_type=DELEGATE, default_timezone=pytz.UTC)
  inbox = account.archive_root / 'Top of Information Store'
  email = inbox.get(id=email_id)
  return email.text_body

def get_email_text(email_id, emailsource, mailbox, access_token):
   if emailsource.lower() == 'archive':
    return get_email_text_archive(email_id, mailbox, access_token)
   else:
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token, "Prefer": 'outlook.body-content-type="text"'}
    url = "https://graph.microsoft.com/v1.0/users/" + mailbox + "/messages/" + email_id
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 200:
        return r.json()['body']['content']
    else:
      app.logger.error('Get email text request with graph, ended with status ' + str(r.status_code) + '. Response: ' + r.text)
      return None

def create_outlook_record_category(access_token, user_email):
  body = {"displayName": "Record", "color": "preset22"}
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  try:
    r = requests.post("https://graph.microsoft.com/v1.0/me/outlook/masterCategories", data=json.dumps(body), headers=headers)
    if r.status_code != 201 and r.status_code != 409:
      app.logger.error('Failed to create Outlook Record category for user ' + user_email)
  except:
    app.logger.error(traceback.format_exc())
    app.logger.error('Failed to create Outlook Record category for user ' + user_email)

def eml_to_pdf(eml):    
    msg = BytesParser(policy=policy.default).parsebytes(eml)
    emb_img = {} 
    attachments = []
    html = ""
    
    for part in msg.walk():
      if part.get_content_maintype() == 'multipart' and part.is_multipart():
        continue
      
      if 'html' in part.get_content_type():
        html = part.get_content()

      if ('image' in part.get_content_type()) and (not part.is_attachment()):
        a=part.get_payload()
        emb_img['src="cid:' + part['Content-ID'].replace('<','').replace('>','')] = 'src="data:image/' + part.get_filename()[-3:] + ';base64, ' + a +'"'
          
      if part.is_attachment():
        attachments.append((part.get_filename(), part.get_payload()))
      
      if part.get_content_type() == 'text/plain':
        content = part.get_content()
        lines = content.split('\n')
        for line in lines:
          html += "<p>" + line + "</p>"
        
    for i in emb_img.keys():
      html = html.replace(i,emb_img[i])
                
    #need to check each field
    field = ['To','From','Cc','Bcc'] #subject as name if name not provided
    final_text = ''
    for i in field:
      if msg[i] is not None:
        final_text += "<strong>" + i +": </strong>" + msg[i].replace("<", "&#60;").replace(">", "&#62;") + "</br>"

    final_text += "<strong>Subject: </strong>" + msg['subject'] + "</br>" + "<strong>Date: </strong>" + msg['date'] + "</br></br></br>"
    # Only keep attachments with names
    attachments = list(filter(lambda y: y[0] is not None, attachments))
    if len(attachments) > 0:
      final_text += "<strong> Attachments: </strong>" + ', '.join([x[0] for x in attachments]) + "</br>"

    # Breaks styling
    # html = html.replace('<','{').replace('>','}')

    # Fix hidden template table styling
    html = BeautifulSoup(html, 'html.parser')
    for td in html.find_all('td'):
      if 'style' in td.attrs:
        del td.attrs['style']

    for tr in html.find_all('tr'):
      if 'style' in tr.attrs:
        del tr.attrs['style']
    
    try:
      pdf_text = final_text + html.prettify()
      result = io.BytesIO()
      pisa_status = pisa.CreatePDF(pdf_text,dest=result)
      success = pisa_status.err == 0
      result.seek(0)
    except:
      pdf_text = final_text + html.get_text()
      result = io.BytesIO()
      pisa_status = pisa.CreatePDF(pdf_text,dest=result)
      success = pisa_status.err == 0
      result.seek(0)

    #conversion --return as bytes
    

    return success, result, attachments

def parse_email_metadata(graph_email_value, mailbox, access_token, emailsource):
  categories = set(graph_email_value.get('categories', []))
  filtered_cats = [x for x in categories if x.lower() != 'record']
  return EmailMetadata(
      unid=graph_email_value['internetMessageId'], #internetMessageId contains '.prod.outlook.com'
      subject=graph_email_value['subject'], 
      email_id=graph_email_value['id'], 
      received=graph_email_value['receivedDateTime'], 
      _from=graph_email_value['from']['emailAddress']['address'],
      to=';'.join([(y['emailAddress']['address']) for y in graph_email_value['toRecipients']]),
      cc=';'.join([(y['emailAddress']['address']) for y in graph_email_value['ccRecipients']]),
      sent=graph_email_value['sentDateTime'],
      attachments= extract_attachments_from_response_graph(graph_email_value['id'], graph_email_value['hasAttachments'], mailbox, access_token),
      mailbox_source= emailsource,
      categories = filtered_cats
    )

def list_email_metadata_archive(req: GetEmailRequest, access_token, category_name='Record'):
  offset = req.items_per_page * (req.page_number -1)
  upper_bound = offset + req.items_per_page

  token = OAuth2Token({'access_token':access_token})
  creds = OAuth2Credentials(
    '','', access_token=token,
  )
  config = Configuration(server='outlook.office.com', credentials=creds, auth_type=OAUTH2)
  account = Account(primary_smtp_address=req.mailbox, config=config, autodiscover=False, access_type=DELEGATE, default_timezone=pytz.UTC)
  inbox = account.archive_root / 'Top of Information Store'

  emails = inbox.filter(categories__contains=[category_name])
  total_count = emails.count()

  email_info = [EmailMetadata(
        unid=x.message_id, 
        subject=x.subject, 
        email_id=x.id, 
        received=str(x.datetime_received), 
        _from=x.sender.email_address, 
        to=[e.email_address for e in (x.to_recipients or [])], 
        cc = [e.email_address for e in (x.cc_recipients or [])],
        sent=str(x.datetime_sent),
        attachments=[EmailAttachment(name=attachment.name, attachment_id=attachment.attachment_id.id) for attachment in (x.attachments or [])],
        mailbox_source='archive',
        categories = x.categories
      ) for x in emails[offset:upper_bound]]
  
  return total_count, email_info

def list_email_metadata_graph(req: GetEmailRequest, access_token):

  #get records from archive
  if req.emailsource.lower() == 'archive':
    total_count, emails = list_email_metadata_archive(req, access_token)

  else:
    mailbox = 'users/' + req.mailbox
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
    url = "https://graph.microsoft.com/v1.0/" + mailbox + "/messages?$filter=categories/any(a:a+eq+'Record')&$top="+ str(req.items_per_page) + "&$skip=" + str((req.page_number -1)*req.items_per_page) + "&$count=true" 
    p = requests.get(url, headers=headers, timeout=60)
    
    if p.status_code == 404:
      app.logger.info("Graph API returned 404 for mailbox " + req.mailbox + ". " + p.text)
      return Response(StatusResponse(status='Failed', reason="Unable to retrieve records for regular " + req.mailbox, request_id=g.get('request_id', None)).to_json(), status=404, mimetype='application/json')
    if p.status_code != 200:
      app.logger.info("Regular getrecords graph request failed for mailbox " + req.mailbox + " with status " + str(p.status_code) + ". " + p.text)
      return Response(StatusResponse(status='Failed', reason="Unable to retrieve records for regular " + req.mailbox, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    
    resp = p.json() 
    emails = [parse_email_metadata(graph_email_value, mailbox, access_token, req.emailsource) for graph_email_value in resp['value']]

    total_count=resp['@odata.count'] 
    
    #'@odata.count' will add 1 for each "meetingMessageType": "meetingRequest" type, this value is not present for regular messages
    count = 0
    for x in resp['value']:
      if "meetingMessageType" in x.keys():
        count =+ 1 
    total_count -= count

  return Response(GetEmailResponse(total_count=total_count, items_per_page=req.items_per_page, page_number=req.page_number, emails=emails).to_json(), status=200, mimetype="application/json")

def extract_attachments_from_response_graph(messageId, hasAttachments, mailbox, access_token):
  if hasAttachments:
    url = "https://graph.microsoft.com/v1.0/" + mailbox + "/messages/" + str(messageId) + "/attachments?$select=name,id"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
    p = requests.get(url, headers=headers, timeout=60)
    resp = p.json()
    attachments = [EmailAttachment(name=x['name'], attachment_id=x['id']) for x in resp['value']]
    return attachments
  else: 
    return []

#combined untag and mark_saved
def mark_saved_archive(req: MarkSavedRequestGraph, access_token, saved_cat="Saved to ARMS"):
  try:
    token = OAuth2Token({'access_token':access_token})
    creds = OAuth2Credentials(
      '','', access_token=token,
    )
    config = Configuration(server='outlook.office.com', credentials=creds, auth_type=OAUTH2)
    account = Account(primary_smtp_address=req.mailbox, config=config, autodiscover=False, access_type=DELEGATE, default_timezone=pytz.UTC)
    inbox = account.archive_root / 'Top of Information Store'
    email = inbox.get(id=req.email_id)
    cats = email.categories
    if 'Record' in cats: 
      cats.remove('Record')
    cats.append(saved_cat)
    email.categories = cats
    email.save()      
    return Response(StatusResponse(status="OK", reason="Email was marked saved.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")
  except:
    return Response(StatusResponse(status='Failed', reason="Unable to mark as saved.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

def mark_saved(req: MarkSavedRequestGraph, access_token, emailsource, saved_cat="Saved to ARMS"):
  if emailsource.lower() == 'archive':
    return mark_saved_archive(req, access_token, saved_cat)
  else:
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
    #TODO: Make this work for shared email boxes
    #get current categories for message to mark_saved without removing other categories
    urlo =  "https://graph.microsoft.com/v1.0/users/" + req.mailbox + "/messages/" + req.email_id + '?$select=categories'
    p = requests.get(urlo, headers=headers)
    cats = p.json()['categories']
    if 'Record' in cats: 
      cats.remove('Record')
    cats.append(saved_cat)
    #update categories
    url = "https://graph.microsoft.com/v1.0/users/" + req.mailbox + "/messages/" + req.email_id
    body = json.dumps({'categories':cats})
    p = requests.patch(url, headers=headers, data=body, timeout=30)
    if p.status_code != 200:
      return Response(StatusResponse(status='Failed', reason="Unable to mark as saved.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    else:
      return Response(StatusResponse(status="OK", reason="Email was marked saved.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")
    
def get_badge_info(config):
  params={'api_key':config.patt_api_key, 'table':'rewards'}
  url = 'https://' + config.patt_host + '/app/mu-plugins/pattracking/includes/admin/pages/games/get_data.php'
  r = requests.post(url, params=params)
  if r.status_code != 200:
    return Response(StatusResponse(status='Failed', reason='Badge info request returned status ' + str(r.status_code) + ' and error ' + str(r.text), request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  return Response(json.dumps([BadgeInfo(**x).to_dict() for x in r.json()]), status=200, mimetype='application/json')

def get_overall_leaderboard(config):
  url = 'https://' + config.patt_host + '/app/mu-plugins/pattracking/includes/admin/pages/games/overall_leader_board.php'
  r = requests.post(url)
  if r.status_code != 200:
    return Response(StatusResponse(status='Failed', reason='Overall leaderboard request returned status ' + str(r.status_code) + ' and error ' + str(r.text), request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  return Response(json.dumps(r.json()), status=200, mimetype='application/json')

def get_office_leaderboard(config, parent_org_code):
  url = 'https://' + config.patt_host + '/app/mu-plugins/pattracking/includes/admin/pages/games/office_leader_board.php'
  params={'api_key':config.patt_api_key, 'office_code' : parent_org_code}
  r = requests.post(url, params=params)
  if r.status_code != 200:
    return Response(StatusResponse(status='Failed', reason= 'Leaderboard request returned status ' + str(r.status_code) + ' and error ' + str(r.text), request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  return Response(json.dumps(r.json()), status=200, mimetype='application/json')

def get_nuxeo_creds(c, env):
  if env == 'dev':
    return c.nuxeo_dev_url, c.nuxeo_dev_username, c.nuxeo_dev_password
  else:
    return c.nuxeo_prod_url, c.nuxeo_prod_username, c.nuxeo_prod_password

def validate_by_uid(c, uid, env, employee_number):
  headers = {'Content-Type':'application/json', 'X-NXproperties':'*'}
  try:
    nuxeo_url, nuxeo_username, nuxeo_password = get_nuxeo_creds(c, env)
    r = requests.get(f'{nuxeo_url}/nuxeo/api/v1/search/lang/NXQL/execute?query=select * from epa_record where ecm:uuid="{uid}"', headers=headers, auth=HTTPBasicAuth(nuxeo_username, nuxeo_password))
    record_custodian = r.json()['entries'][0]['properties']['arms:epa_contact']
    if record_custodian == employee_number:
      return True, None, True
    else:
      return True, None, False
  except:
    app.logger.error(traceback.format_exc())
    return False, 'Failed to find record metadata for validation', None
  
def download_nuxeo_record(c, user_info, req):
  # Validate that the user is the custodian
  success, error, valid = validate_by_uid(c, req.uid, req.nuxeo_env, user_info.employee_number)
  if not success:
    return Response(StatusResponse(status='Failed', reason=error, request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
  if not valid:
    return Response(StatusResponse(status='Failed', reason='User is not authorized to download this record.', request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')

  # Download record
  nuxeo_url, nuxeo_username, nuxeo_password = get_nuxeo_creds(c, req.nuxeo_env)
  headers = {'Content-Type':'application/json', 'X-NXproperties':'*'}
  d = requests.get(nuxeo_url + '/nuxeo/nxfile/default/' + req.uid + '/file:content/' + req.name, headers=headers, auth=HTTPBasicAuth(nuxeo_username, nuxeo_password))  
  if d.status_code != 200:
    return Response(StatusResponse(status='Failed', reason='Failed to download record.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
  b = io.BytesIO(d.content)
  return send_file(b, mimetype='application/octet-stream', as_attachment=True, attachment_filename=req.name)

def convert_nuxeo_metadata(nuxeo_dict):
  properties = nuxeo_dict['properties']
  file_path = properties.get('arms:folder_path', '')
  ## TODO: Use WAM to recover the LAN ID
  custodian = properties.get('arms:epa_contact')
  title = nuxeo_dict.get('title', '')
  nuxeo_sched = properties.get('arms:record_schedule', None)
  record_schedule = schedule_cache.get_schedule_mapping().get(nuxeo_sched, None)
  if properties.get('arms:sensitivity', '1') == '0':
    sensitivity = 'Shared'
  else:
    sensitivity = 'Private'
  description: Optional[str] = properties.get('dc:description', '')
  creator: Optional[str] = properties.get('dc:creator', '')
  creation_date: Optional[str] = properties.get('dc:created', '')
  close_date: Optional[str] = properties.get('arms:close_date', '')
  disposition_date: Optional[str] = properties.get('arms:disposition_date', '')
  rights: Optional[list[str]] = properties.get('arms:rights_holder', [])
  coverage: Optional[list[str]] = properties.get('dc:coverage', [])
  ## TODO: Update this since relationships field is out of date
  relationships: Optional[list[str]] = None
  tags: Optional[list[str]] = [x['label'] for x in properties.get('nxtag:tags', [])]
  
  return ECMSMetadata(
    file_path=file_path, 
    custodian=custodian, 
    title=title, 
    record_schedule=record_schedule, 
    sensitivity=sensitivity,
    description=description, 
    creator=creator,
    creation_date=creation_date,
    close_date=close_date,
    disposition_date=disposition_date,
    rights=rights,
    coverage=coverage,
    relationships=relationships,
    tags=tags
    )

def convert_nuxeo_record(nuxeo_dict):
  metadata = convert_nuxeo_metadata(nuxeo_dict)
  properties = nuxeo_dict['properties']
  if properties.get('arms:sensitivity', '1') == '0':
    sensitivity = 'Shared'
  else:
    sensitivity = 'Private'
  if properties['file:content'] is None:
    size = None
    name = properties.get('dc:title', '')
  else:
    size = properties.get('file:content', {}).get('length', 0)
    name = properties.get('file:content', {}).get('name', '')
  custodian = properties.get('arms:epa_contact', '')
  upload_date = properties.get('dc:created', '')
  return NuxeoDocInfo(sensitivity=sensitivity, uid=nuxeo_dict['uid'], name=name, size=size, custodian=custodian, upload_date=upload_date, metadata=metadata)

def get_nuxeo_records(c, req, employee_number):
  nuxeo_url, nuxeo_username, nuxeo_password = get_nuxeo_creds(c, req.nuxeo_env)
  headers = {'Content-Type':'application/json', 'X-NXproperties':'*'}
  nuxeo_query = nuxeo_url + '/nuxeo/api/v1/search/lang/NXQL/execute?query=select * from epa_record where arms:epa_contact="' + employee_number + '" and ecm:versionLabel <> "0.0" and NOT ecm:path STARTSWITH "/EPA%20Organization/ThirdParty" and NOT ecm:path STARTSWITH "/EPA%20Organization/ThirdParty-Queue" and NOT ecm:path STARTSWITH "/EPA%20Organization/UnPublished"'
  if req.query is not None:
    nuxeo_query += ' and ecm:fulltext.dc:title = "' + req.query + '"'
  if req.shared_private_filter is not None:
    if req.shared_private_filter.lower() == 'shared':
      nuxeo_query += ' and arms:sensitivity="0"'
    if req.shared_private_filter.lower() == 'private':
      nuxeo_query += ' and arms:sensitivity="1"'
  nuxeo_query += ' order by dc:created desc&pageSize=' + str(req.items_per_page) + '&currentPageIndex=' + str(req.page_number)
  r = requests.get(nuxeo_query, headers=headers, auth=HTTPBasicAuth(nuxeo_username, nuxeo_password))
  if r.status_code != 200:
    app.logger.error(r.text)
    return Response(StatusResponse(status='Failed', reason='Failed to access Nuxeo find API.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
  data = r.json()
  records = [convert_nuxeo_record(x) for x in r.json()['entries']]
  response = NuxeoRecordList(total=data['resultsCount'], records=records)
  return Response(response.to_json(), status=200, mimetype='application/json')

def get_disposition_date(req): 
  # Find record schedule information
  schedule_info = None
  for item in schedule_cache.get_schedules().schedules:
    if item.display_name == req.record_schedule:
      schedule_info = item
      break
  
  # If record_schedule doesn't exist in db then return error
  if schedule_info is None:
    return Response(StatusResponse(status='Failed', reason="Could not find record schedule.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')

  fiscal_year_flag = schedule_info.fiscal_year_flag
  calendar_year_flag = schedule_info.calendar_year_flag
  
  retention_year = schedule_info.retention_year
  retention_month = schedule_info.retention_month
  retention_day = schedule_info.retention_day

  try:
    close_date = datetime.datetime.strptime(req.close_date, '%Y-%m-%d').date()
  except:
    app.logger.error(traceback.format_exc())
    return Response(StatusResponse(status='Failed', reason="Incorrect date format, should be YYYY-MM-DD", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')

  # Determine Cutoff (9/30 or 12/31)
  month_only = close_date.month
  year_only = close_date.year
  year_only_1 = close_date.year + 1

  # if all these conditions do not satisfy, need default cutoff date
  if fiscal_year_flag:
    if month_only <= 9:
        cutoff = str(year_only)+'-09-30'
    if month_only > 9:
        cutoff = str(year_only_1)+'-09-30'
    
  if calendar_year_flag:
      cutoff = str(year_only)+'-12-31'
    
  cutoff_date = datetime.datetime.strptime(cutoff, '%Y-%m-%d').date()

  cutoff_date = cutoff_date + timedelta(days = 1)

  add_years = cutoff_date + relativedelta(years = retention_year)
  add_months = add_years + relativedelta(months = retention_month)
  disposition_date = add_months + timedelta(days = retention_day)
  
  return Response(DispositionDate(disposition_date=str(disposition_date)).to_json(), status=200, mimetype="application/json")

def get_badges(config, employee_number):
  if employee_number is None:
    return []
  params={'type':'badges', 'employee_id':employee_number, 'api_key':config.patt_api_key}
  url = 'https://' + config.patt_host + '/app/mu-plugins/pattracking/includes/admin/pages/games/receiver.php'
  r = requests.post(url, params=params)
  if r.status_code != 200:
    app.logger.error('Badge request failed for employee number ' + employee_number)
    return []
  else:
    return [BadgeInfo(id=x['id'], name=x['badge_title'], description=x['badge_description'], image_url=x['badge_image']) for x in r.json()]

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
    
def get_user_settings(employee_number):
    user = User.query.filter_by(employee_number = employee_number).all()
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

def get_wam_info_by_display_name(config, display_name):
  url = 'https://' + config.wam_host + '/iam/governance/scim/v1/Users?attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Department&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Company&attributes=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:PARENTORGCODE&filter=displayName eq "' + display_name + '"'
  wam = requests.get(url, auth=(config.wam_username, config.wam_password), timeout=30)
  if wam.status_code != 200:
    app.logger.error('WAM request by display_name failed for display_name ' + display_name)
    return None
  user_data = wam.json()
  if 'Resources' in user_data and len(user_data['Resources']) > 0:
    user_data = user_data['Resources'][0]
    department = user_data.get('urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User', {}).get('Department', None)
    enterprise_department = user_data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User', {}).get('department', None)
    company = user_data.get('urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User', {}).get('Company', None)
    if enterprise_department is None:
      enterprise_department = company
    return department, enterprise_department
  else:
    app.logger.error('User data empty for display_name ' + display_name)
    return None

def get_email_token(config):
    try:
        params = {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "scope": "Mail.Send",
            "grant_type": "password",
            "username": config.email_username,
            "password": config.email_password
        }
        r = requests.get("https://login.microsoftonline.com/" + config.tenant_id + "/oauth2/v2.0/token", data=params)
        return r.json()['access_token']
    except:
        return None

def create_delegation_email_content(config, submitter_display_name, target_display_name, request_id):
  return f'''
  <!DOCTYPE html>
  <html lang="en">
  <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Request Email</title>
      <style>
          .button {{
              display: inline-block;
              padding: 10px 20px;
              font-size: 16px;
              text-align: center;
              text-decoration: none;
              border-radius: 5px;
              margin: 5px;
          }}
          .accept {{
              background-color: #4CAF50;
              color: white;
              border: none;
          }}
          .reject {{
              background-color: #f44336;
              color: white;
              border: none;
          }}
      </style>
  </head>
  <body>
      <h1>Request for Approval</h1>
      <p>Dear {target_display_name},</p>
      <p>{submitter_display_name} has requested the ability to submit documents to the Agency Records Management System (ARMS) on your behalf. Please accept or reject the request by clicking one of the buttons below.</p>
      <a href="{config.ui_url}/delegationResponse?request_id={request_id}&is_accepted=true" class="button accept">Accept</a>
      <a href="{config.ui_url}/delegationResponse?request_id={request_id}&is_accepted=false" class="button reject">Reject</a>
      <p>If you have any questions or concerns, please feel free to contact us at ARMS@epa.gov.</p>
      <p>Thank you,</p>
      <p>ARMS Team</p>
  </body>
  </html>
  '''

def send_delegation_notification(config, email, submitter_display_name, target_display_name, request_id):
  token = get_email_token(config)
  email = {
    'message': {
        'subject': 'ARMS Delegation Request',
        'body': {
            'contentType': 'Html',
            'content': create_delegation_email_content(config, submitter_display_name, target_display_name, request_id)
        },
        'toRecipients': [
            {
                'emailAddress': {
                    'address': email
                }
            }
        ]
    },
    'saveToSentItems': 'true'
  }
    # Set the request headers
  headers = {
      'Authorization': f'Bearer {token}',
      'Content-Type': 'application/json'
  }

  # Send the email
  response = requests.post(
      'https://graph.microsoft.com/v1.0/me/sendMail',
      headers=headers,
      data=json.dumps(email)
  )

  # Check for a successful response
  if response.status_code == 202:
      return True
  else:
      return False

def get_display_name_by_employee_number(config, employee_number):
  url = 'https://' + config.wam_host + '/iam/governance/scim/v1/Users?attributes=displayName&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Upn&filter=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber eq "' + employee_number + '"'
  wam = requests.get(url, auth=(config.wam_username, config.wam_password), timeout=30)
  if wam.status_code != 200:
    app.logger.error('WAM request by display_name failed for display_name ' + display_name)
    return None
  user_data = wam.json()
  if 'Resources' in user_data and len(user_data['Resources']) > 0:
    user_data = user_data['Resources'][0]
    display_name = user_data.get('displayName', None)
    email = user_data.get('urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User', {}).get('Upn', None)
    return display_name, email
  else:
    app.logger.error('User data empty for display_name ' + display_name)
    return None
  
def get_direct_reports(token_data, access_token):
  headers = {'Authorization': 'Bearer ' + access_token, 'Content-Type':'application/json'}
  r = requests.get("https://graph.microsoft.com/v1.0/me/directReports", headers=headers, timeout=10)
  if r.status_code != 200:
    app.logger.error('Failed to fetch direct reports for ' + token_data['email'])
    return []
  else:
    return [x['userPrincipalName'] for x in r.json()['value']]

def get_folder_id(access_token, folder_name):
  # Get ID for ARMS Archive folder
  headers = {'Authorization': 'Bearer ' + access_token}
  folder_req = requests.get(f"https://graph.microsoft.com/v1.0/me/drive/root:/{folder_name}:", headers=headers, timeout=30)
  if folder_req.status_code != 200:
    app.logger.error(f'Unable to find {folder_name} folder: ' + folder_req.text)
    return False, None, Response(f'Unable to find {folder_name} folder: ' + str(folder_req.text), status=400, mimetype='application/json')
  return True, folder_req.json()['id'], None

def create_arms_readme(access_token):
  file_name = 'ARMS Archive Guidance.txt'
  file_content = 'The files in this folder are convenience copies of records that you uploaded to the Agency Records Management System (ARMS) but do not contain metadata. These files will remain in this folder for the duration of the retention period and be dispositioned (deleted) per the records schedule assigned to official record copy in ARMS. If you move a file outside of this folder, you are responsible for managing its disposition according to the appropriate records schedule. If the record is kept beyond its approved disposition, it will be responsive to any litigation holds or FOIA requests in the future.'
  encoded_content = base64.b64encode(file_content.encode()).decode()
  url = f'https://graph.microsoft.com/v1.0/me/drive/root:/{ARMS_ARCHIVE_FOLDER_NAME}/{file_name}'
  headers = {'Authorization': 'Bearer ' + access_token, 'Content-Type': 'application/json'}
  data = {'file': {}, '@microsoft.graph.sourceUrl': f'data:text/plain;base64,{encoded_content}'}
  r = requests.put(url, json=data, headers=headers)
  return r.status_code == 201 or r.status_code == 409

def get_user_info(config, token_data, access_token=None):
  # Handle service accounts separately
  if token_data['email'][:4].lower() == 'svc_' or 'java_review' in token_data['email'].lower():
    return True, None, UserInfo(token_data['email'], token_data['email'], token_data['email'].split('@')[0], 'SERVICE_ACCOUNT', '', None, None, '', [], None, default_settings)
  url = 'https://' + config.wam_host + '/iam/governance/scim/v1/Users?attributes=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:manager&attributes=name&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Department&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Company&attributes=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:PARENTORGCODE&attributes=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber&attributes=userName&attributes=Active&attributes=displayName&filter=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Upn eq "' + token_data['email'] + '"'
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
    manager_name = user_data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User', {}).get('manager', {}).get('displayName', None)
    first_name = user_data.get('name', {}).get('givenName', None)
    last_name = user_data.get('name', {}).get('familyName', None)
    manager_department = None
    manager_enterprise_department = None
    try:
      if manager_name is not None:
        manager_data = get_wam_info_by_display_name(config, manager_name)
        if manager_data is not None:
          manager_department = manager_data[0]
          manager_enterprise_department = manager_data[1]
        else:
          app.logger.error('Manager lookup data empty for manager name ' + str(manager_name))
    except:
      app.logger.error(traceback.format_exc())
      app.logger.error('Manager lookup failed for manager name ' + str(manager_name))

    if enterprise_department is None:
      enterprise_department = company
    active = user_data['active']
    if not active:
      return False, 'User is not active.', None
  except:
    app.logger.error(traceback.format_exc())
    return False, 'WAM request failed.', None
  try:
    badges = get_badges(config, employee_number)
    profile = get_profile(config, employee_number)
    if profile is None:
      profile = ProfileInfo(points="0", level="Beginner", office_rank="1000", overall_rank="10000")
  except:
    app.logger.error(traceback.format_exc())
    badges = []
    profile = ProfileInfo(points="0", level="Beginner", office_rank="1000", overall_rank="10000")
    app.logger.info('Profile requests failed for ' + token_data['email'])
  try:
    user_settings = get_user_settings(employee_number)
  except:
    app.logger.error(traceback.format_exc())
    user_settings = default_settings
    app.logger.info('Preferred system database read failed for ' + token_data['email'])
  if access_token is not None:
    direct_reports = get_direct_reports(token_data, access_token)
    success, response = check_or_create_folder(access_token, ARMS_SYNC_FOLDER_NAME)
    if not success:
      return response
    success, response = check_or_create_folder(access_token, ARMS_ARCHIVE_FOLDER_NAME)
    if not success:
      return response
    try:
      success = create_arms_readme(access_token)
      if not success:
        app.logger.info('Did not create ARMS README for ' + token_data['email'])
    except:
      app.logger.info('Did not create ARMS README for ' + token_data['email'])
  else:
    direct_reports = []
  return True, None, UserInfo(token_data['email'], display_name, lan_id, department, enterprise_department, manager_department, manager_enterprise_department, employee_number, badges, profile, user_settings, direct_reports, first_name=first_name, last_name=last_name)

def get_gamification_data(config, employee_number):
  try:
    badges = get_badges(config, employee_number)
    profile = get_profile(config, employee_number)
    data = GamificationDataResponse(badges, profile)
    return Response(data.to_json(), status=200, mimetype='application/json')
  except:
    app.logger.error(traceback.format_exc())
    badges=[]
    profile=None
    app.logger.info('Profile requests failed for ' + employee_number)

def get_sems_special_processing(config, region):
  special_processing = requests.get('https://' + config.sems_host + '/sems-ws/outlook/getSpecialProcessing/' + region, timeout=10)
  if special_processing.status_code == 200:
    response_object = GetSpecialProcessingResponse([SemsSpecialProcessing(**obj) for obj in special_processing.json()])
    return Response(response_object.to_json(), status=200, mimetype='application/json')
  else:
    return Response(StatusResponse(status='Failed', reason=special_processing.text, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

def get_sems_sites(req: SemsSiteRequest, config):
  params = req.to_dict()
  params = {k:v for k,v in params.items() if v is not None}
  try:
    sites = requests.get('https://' + config.sems_host + '/sems-ws/outlook/getSites', params=params, timeout=120)
  except:
    app.logger.error(traceback.format_exc())
    return Response(StatusResponse(status='Failed', reason="Request to SEMS server failed.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  if sites.status_code == 200:
    response_object = SemsSiteResponse.from_dict(sites.json())
    return Response(response_object.to_json(), status=200, mimetype='application/json')
  else:
    return Response(StatusResponse(status='Failed', reason=sites.text, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

def detect_schedule_from_string(text, schedule_mapping):
  if text is None:
    return None
  m = re.search('([0-1]{1}[0-7]{1}[0-9]{2}|\d{3})\s?[a-z]\s?(\(([a-z]|[0-9])\)\s?)*', text)
  if m is not None:
    match = m[0].replace(' ', '').replace('%20', '').replace('-','')
    if match in schedule_mapping:
      return schedule_mapping[match]
  return None

def simplify_sharepoint_record(raw_rec, sensitivity):
  default_schedule = None
  schedule_found = False
  mapping = schedule_cache.get_schedule_mapping()
  path_tags = set()
  for item in raw_rec['parentReference']['path'].split('/'):
    if item.strip() not in set(['drive', 'root:', ARMS_SYNC_FOLDER_NAME, '']):
      path_tags.add(item.strip())
    if not schedule_found:
      detected_schedule = detect_schedule_from_string(item.replace('%20', ' '), mapping)
      if detected_schedule is not None:
        default_schedule = detected_schedule
        schedule_found = True
        
  return SharepointRecord(
    web_url = raw_rec['webUrl'],
    sensitivity = sensitivity,
    name = raw_rec['name'],
    drive_item_id = raw_rec['id'],
    created_date = raw_rec['createdDateTime'],
    last_modified_date = raw_rec['lastModifiedDateTime'],
    detected_schedule = default_schedule,
    size = raw_rec["size"],
    path_tags = list(path_tags)
  )

def check_or_create_folder(access_token, folder_name):
  headers = {'Authorization': 'Bearer ' + access_token, 'Content-Type':'application/json'}
  r = requests.get(f"https://graph.microsoft.com/v1.0/me/drive/root/children/?$filter=name eq '{folder_name}'", headers=headers, timeout=10)
  if r.status_code != 200:
    return False, Response(StatusResponse(status='Failed', reason='Records folder request failed. ' + r.text, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  values = r.json().get('value', [])
  if len(values) == 0:
    # If folder is not present, create it
    body = {
      "name": folder_name,
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
        app.logger.error('Failed to create folder with status ' + str(r.status_code))
        app.logger.error(r.text)
        return False, Response(StatusResponse(status='Failed', reason='Failed to create folder.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    else:
      app.logger.error('Failed to create folder with status ' + str(r.status_code))
      app.logger.error(r.text)
      return False, Response(StatusResponse(status='Failed', reason='Failed to create folder.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  else:
    return True, None

# Note: Depth increases when passing to a subfolder, or to a next page of results
def read_sharepoint_folder(relative_path, access_token, depth, link = None, max_depth=5):
  if depth > max_depth:
    return True, []
  headers = {'Authorization': 'Bearer ' + access_token}
  if link:
    shared = requests.get(link, headers=headers, timeout=10)
  else: 
    shared = requests.get("https://graph.microsoft.com/v1.0/me/drive/root:/" + relative_path + ":/children/?$top=1000", headers=headers, timeout=10)
  if shared.status_code != 200:
    return False, Response(StatusResponse(status='Failed', reason='Failed to retrieve shared OneDrive items for folder ' + relative_path, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  shared_items = shared.json()['value']
  # Process records in this folder
  all_records = [simplify_sharepoint_record(doc, 'Shared') for doc in shared_items if "folder" not in doc]
  # Process subfolders
  folders = list(filter(lambda x: "folder" in x, shared_items))
  for folder in folders:
    read_successful, data = read_sharepoint_folder(relative_path + "/" + folder["name"], access_token, depth + 1, link=None, max_depth=max_depth)
    if not read_successful:
      return False, data
    else:
      all_records = all_records + data
  # If number of items in this folder is too large, process the rest of the items in the folder
  if "@odata.nextLink" in shared.json():
    next_link = shared.json()['@odata.nextLink']
    read_successful, recursive_data = read_sharepoint_folder(relative_path, access_token, depth + 1, link=next_link, max_depth=max_depth)
    if not read_successful:
      return False, recursive_data
    else:
      all_records = all_records + recursive_data
  return True, all_records

def list_sharepoint_records(req: GetSharepointRecordsRequest, access_token):
  page_number = int(req.page_number)
  items_per_page = int(req.items_per_page)
  if page_number <= 0:
    return Response(StatusResponse(status='Failed', reason='Invalid page number.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
  if items_per_page <= 0:
    return Response(StatusResponse(status='Failed', reason='Items per page must be > 0.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
  # Get shared records
  read_successful, data = read_sharepoint_folder(ARMS_SYNC_FOLDER_NAME, access_token, 0)
  if not read_successful:
    return data
  else:
    filtered_records = sorted(data, key=lambda x: x.last_modified_date, reverse=True)
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
  success, tika_result, response = tika(content, c)
  if not success:
      return response
  if tika_result.is_encrypted:
    prediction = MetadataPrediction(predicted_schedules=[], title=mock_prediction_with_explanation, is_encrypted=True, description=mock_prediction_with_explanation, default_schedule=None, subjects=[], identifiers={}, cui_categories=tika_result.cui_categories)
    return Response(prediction.to_json(), status=200, mimetype='application/json')
  keyword_weights = keyword_extractor.extract_keywords(tika_result.text)
  keywords = [x[0] for x in sorted(keyword_weights.items(), key=lambda y: y[1], reverse=True)][:5]
  subjects=keyword_extractor.extract_subjects(tika_result.text, keyword_weights)
  identifiers=identifier_extractor.extract_identifiers(tika_result.text)
  has_capstone=capstone_detector.detect_capstone_text(tika_result.text)
  spatial_extent, temporal_extent = identifier_extractor.extract_spatial_temporal(tika_result.text)
  # TODO: Handle case where attachments are present
  predicted_schedules, default_schedule = model.predict(tika_result.text, 'document', PredictionMetadata(req.file_name, req.department), has_capstone, keywords, subjects, attachments=[])
  predicted_title = mock_prediction_with_explanation
  predicted_description = mock_prediction_with_explanation
  prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, is_encrypted=tika_result.is_encrypted, description=predicted_description, default_schedule=default_schedule, subjects=subjects, identifiers=identifiers, cui_categories=tika_result.cui_categories, spatial_extent=spatial_extent, temporal_extent=temporal_extent)
  return Response(prediction.to_json(), status=200, mimetype='application/json')

def upload_sharepoint_record_v3(req: SharepointUploadRequestV3, access_token, user_info, c):
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
    return Response(StatusResponse(status='Failed', reason='Content request failed with status ' + str(content_req.status_code), request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  content = content_req.content
  metadata = req.metadata
  identifiers = metadata.identifiers
  identifiers['onedrive_id'] = [req.drive_item_id]
  metadata.identifiers = identifiers
  success, error, uid = submit_nuxeo_file_v2(c, content, user_info, metadata, req.nuxeo_env)
  if not success:
    return Response(StatusResponse(status='Failed', reason='Nuxeo upload for sharepoint file failed with error ' + error, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  
  # Get ID for ARMS Archive folder
  success, archived_folder_id, response = get_folder_id(access_token, ARMS_ARCHIVE_FOLDER_NAME)
  if not success:
    return response

  # Move file to ARMS Archive folder
  body = {"parentReference": {"id": archived_folder_id}}
  move_req = requests.patch(f"https://graph.microsoft.com/v1.0/me/drive/items/{req.drive_item_id}", json=body, headers=headers, timeout=30)
  if move_req.status_code != 200:
    app.logger.error('Unable to move OneDrive item: ' + move_req.text)
    return Response('Unable to move OneDrive item: ' + str(move_req.text), status=400, mimetype='application/json')
  
  ## Add submission analytics to table
  success, response = add_submission_analytics(req.user_activity, req.metadata.record_schedule, user_info.employee_number, None, uid)
  if not success:
    return response
  else:
    log_upload_activity_v2(user_info, req.user_activity, req.metadata, c)
    upload_resp = UploadResponse(record_id=req.metadata.record_id, uid=uid)
    return Response(upload_resp.to_json(), status=200, mimetype='application/json')

def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx:min(ndx + n, l)]

def sched_to_string(sched):
  return '-'.join([sched.function_number, sched.schedule_number, sched.disposition_number])

def upload_nuxeo_file(config, file, file_md5):
  client = boto3.client('s3')
  try:
    client.put_object(Body=file, Bucket=config.arms_upload_bucket, Key=config.arms_upload_prefix + '/' + file_md5, ACL='bucket-owner-full-control')
    return True
  except:
    app.logger.error(traceback.format_exc())
    return False

def update_nuxeo_metadata(uid, properties, config, env):
  try:
    nuxeo_url, nuxeo_username, nuxeo_password = get_nuxeo_creds(config, env)
    body = {"entity-type": "document", "properties": properties}
    r = requests.put(nuxeo_url + '/nuxeo/api/v1/id/' + uid, json=body, auth=HTTPBasicAuth(nuxeo_username, nuxeo_password))
    if r.status_code == 200:
      return True
    else:
      app.logger.error('Nuxeo metadata update failed for UID: ' + uid + ' with status ' + str(r.status_code) + '. ' + r.text)
      return False
  except:
    app.logger.error(traceback.format_exc())
    app.logger.error('Nuxeo metadata update failed.')
    return False

def get_nuxeo_metadata(uid, config, env, property_string="*"):
  nuxeo_url, nuxeo_username, nuxeo_password = get_nuxeo_creds(config, env)
  headers = {'Content-Type':'application/json', 'X-NXproperties':'*'}
  try:
    r = requests.get(nuxeo_url + f'/nuxeo/api/v1/search/lang/NXQL/execute?query=select {property_string} from epa_record where ecm:uuid="{uid}"', headers=headers, auth=HTTPBasicAuth(nuxeo_username, nuxeo_password))
    properties = r.json()['entries'][0]['properties']
    return True, properties
  except:
    app.logger.error(traceback.format_exc())
    return False, None

def add_relationship(req: AddParentChildRequest, user_info, config, env):
  # Validate parent and child ids all belong to the sender
  metadata_dict = {}
  success, parent_metadata = get_nuxeo_metadata(req.parent_id, config, env)
  if not success:
    return Response(StatusResponse(status='Failed', reason='Failed to get parent metadata for id ' + req.parent_id, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  metadata_dict[req.parent_id] = parent_metadata
  
  record_custodian = parent_metadata.get('arms:epa_contact')
  if record_custodian != user_info.employee_number:
    return Response(StatusResponse(status='Failed', reason=f'User {user_info.lan_id} is not authorized to edit {req.parent_id}', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')

  for child_id in req.child_ids:
    success, child_metadata = get_nuxeo_metadata(child_id, config, env)
    if not success:
      return Response(StatusResponse(status='Failed', reason='Failed to get child metadata for id ' + child_id, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    metadata_dict[child_id] = child_metadata
    record_custodian = parent_metadata.get('arms:epa_contact')
    if record_custodian != user_info.employee_number:
      return Response(StatusResponse(status='Failed', reason=f'User {user_info.lan_id} is not authorized to edit {child_id}', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    
  # Update parent properties
  existing_parts = metadata_dict[req.parent_id].get('arms:relation_has_part', [])
  updated_parts = list(set(existing_parts + req.child_ids))
  updated_properties = {'arms:relation_has_part': updated_parts}
  success = update_nuxeo_metadata(req.parent_id, updated_properties, config, env)
  if not success:
    return Response(StatusResponse(status='Failed', reason='Failed to update metadata for uid ' + req.parent_id, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  
  # Update child properties
  for child_id in req.child_ids:
    existing_parts = metadata_dict[child_id].get('arms:relation_is_part_of', [])
    updated_parts = list(set(existing_parts + [req.parent_id]))
    updated_properties = {'arms:relation_is_part_of': updated_parts}
    success = update_nuxeo_metadata(child_id, updated_properties, config, env)
    if not success:
      return Response(StatusResponse(status='Failed', reason=f'Failed to update metadata for uid {child_id}', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  return Response(StatusResponse(status='OK', reason='Updated relationships.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')

def convert_metadata_for_nuxeo_v2(user_info, metadata, doc_type, parent_id=None, source_system="ARMS_UPLOADER"):
  data = { "entity-type": "document", "name": metadata.title, "type": "epa_record"}
  schedule = metadata.record_schedule.schedule_number + metadata.record_schedule.disposition_number
  sensitivity = "1"
  if metadata.sensitivity.lower() == 'shared':
    sensitivity = "0"
  essential_records = 0
  if metadata.essential_records.lower() == 'yes':
    essential_records = 1
  properties = {
    ## TODO: enable submission of EPA Contacts, non EPA Contacts, CUI/PII categories, Access/Use Restriction fields, Security Classification, Subjects 
    ## TODO: epa_contact will become a multi valued field
    ## TODO: Add this once creators are enabled in Nuxeo
    ## TODO: Remove epa_contact and all usages
    ## "arms:creators": metadata.creators,
    "arms:custodian": user_info.employee_number,
    "arms:epa_contact": user_info.employee_number,
    "arms:aa_ship": user_info.parent_org_code[0] + '0000000',
    "arms:document_type": doc_type,
    "arms:record_schedule": schedule,
    "arms:folder_path": [metadata.file_path],
    "arms:application_id": source_system,
    ## TODO: Look up whether the current user is capstone and populate this correctly. 
    "arms:has_capstone": False,
    "arms:program_office": [user_info.manager_parent_org_code],
    "arms:sensitivity": sensitivity,
    "arms:spatial_extent": metadata.spatial_extent,
    "arms:temporal_extent": metadata.temporal_extent,
    "arms:subjects": metadata.subjects,
    "arms:specific_access_restrictions": metadata.specific_access_restriction,
    "arms:specific_use_restrictions": metadata.specific_use_restriction,
    "arms:essential_records": essential_records,
    "arms:rights_holder": metadata.rights_holder,
    "dc:description": metadata.description,
    "dc:title": metadata.title,
    ## TODO: Switch this to employee_number when Nuxeo changes schema
    "dc:creator": user_info.lan_id.upper(), 
    "nxtag:tags": [{"label": tag,"username": metadata.custodian} for tag in metadata.tags],
    }
  if metadata.identifiers is not None:
    properties['arms:identifiers'] = [{"key": k, "value":v} for k,v in metadata.identifiers.items()]
  if metadata.close_date is not None:
    properties['arms:close_date'] = metadata.close_date
  if metadata.disposition_date is not None:
    properties['arms:disposition_date'] = metadata.disposition_date
  if parent_id is not None:
    properties['arms:relation_is_part_of'] = [parent_id]
  data['properties'] = properties
  return data

def create_nuxeo_record_v2(config, user_info, metadata, env, parent_id=None):
  nuxeo_url, nuxeo_username, nuxeo_password = get_nuxeo_creds(config, env)
  headers = {'Content-Type': 'application/json'}
  data = convert_metadata_for_nuxeo_v2(user_info, metadata, 'Other', parent_id=parent_id)
  try:
    r = requests.post(nuxeo_url + '/nuxeo/api/v1/path/EPA Organization/ThirdParty', json=data, headers=headers, auth=HTTPBasicAuth(nuxeo_username, nuxeo_password))
    if r.status_code == 201:
      uid = r.json()['uid']
      return True, None, uid
    else:
      app.logger.error(r.text)
      return False, "Record creation request returned " + str(r.status_code) + ' response.', None
  except:
    app.logger.error(traceback.format_exc())
    return False, "Failed to complete record creation request.", None

def attach_nuxeo_blob(config, uid, content_blob: NuxeoBlob, attachment_blobs: list[NuxeoBlob], env):
  nuxeo_url, nuxeo_username, nuxeo_password = get_nuxeo_creds(config, env)
  headers = {'Content-Type': 'application/json'}
  body = {
    'input': uid,
    'params': {
      'blobs': {
        'content': content_blob.to_dict()
      }
    }
  }
  if len(attachment_blobs) > 0:
    body['params']['blobs']['arms:attachment_file'] = [x.to_dict() for x in attachment_blobs]

  try:
    r = requests.post(nuxeo_url + '/nuxeo/site/automation/ARMSLinkS3Blobs', json=body, headers=headers, auth=HTTPBasicAuth(nuxeo_username, nuxeo_password))
    if r.status_code == 200:
      return True, None
    else:
      app.logger.error(r.text)
      app.logger.error('Request body that failed: ' + json.dumps(body))
      return False, "Link blobs request returned " + str(r.status_code) + ' response.'
  except:
    app.logger.error(traceback.format_exc())
    app.logger.error(r.text)
    return False, "Failed to link S3 blobs."
  
def convert_sems_metadata(user_info, sems_metadata: SEMSMetadata):
  # TODO: How to fill use and access restrictions
  # TODO: How to incorporate other SEMS metadata
  if len(sems_metadata.access_control) == 1 and 'UCTL' in sems_metadata.access_control:
    sensitivity = "Shared"
  else:
    sensitivity = "Private"
  return ECMSMetadataV2(
    file_path=sems_metadata.file_name,
    custodian=user_info.employee_number,
    title=sems_metadata.file_name,
    record_schedule=sems_metadata.record_schedule,
    sensitivity=sensitivity,
    access_restriction_status="",
    use_restriction_status="",
    essential_records="",
    description=sems_metadata.description,
    tags=sems_metadata.tags,
    identifiers={'SEMS EPA ID': [sems_metadata.sems_uid]}
  )

def create_nuxeo_email_record_v2(config, user_info, metadata, env, source_system="ARMS_UPLOADER"):
  nuxeo_url, nuxeo_username, nuxeo_password = get_nuxeo_creds(config, env)
  headers = {'Content-Type': 'application/json'}
  data = convert_metadata_for_nuxeo_v2(user_info, metadata, 'Email', source_system=source_system)
  try:
    r = requests.post(nuxeo_url + '/nuxeo/api/v1/path/EPA Organization/ThirdParty', json=data, headers=headers, auth=HTTPBasicAuth(nuxeo_username, nuxeo_password))
    if r.status_code == 201:
      uid = r.json()['uid']
      return True, None, uid
    else:
      app.logger.error(r.text)
      return False, "Record creation request returned " + str(r.status_code) + ' response.', None
  except:
    app.logger.error(traceback.format_exc())
    app.logger.error(r.text)
    return False, "Failed to complete record creation request.", None

def submit_nuxeo_file_v2(config, file, user_info, metadata, env):
  # Step 1: Upload files
  file_md5 = hashlib.md5(file).hexdigest()
  success = upload_nuxeo_file(config, file, file_md5)

  if not success:
    return False, "Failed to upload file."
  
  # Step 2: Create Nuxeo record
  success, error, uid = create_nuxeo_record_v2(config, user_info, metadata, env)
  if not success:
    return False, error, None
  
  # Step 3: Attach blob
  mimetype = mimetypes.guess_type(metadata.file_path)[0]
  if mimetype is None:
    mimetype = 'application/octet-stream'
  content_blob = NuxeoBlob(filename=metadata.file_path, mimetype=mimetype, digest=file_md5, length=len(file))
  success, error = attach_nuxeo_blob(config, uid, content_blob, [], env)
  if not success:
    return False, error, None

  return True, None, uid

def upload_nuxeo_email_v2(config, req, source, user_info):

  # Step 0: Get EML file from graph
  content = get_eml_file(req.email_id, source, req.mailbox, g.access_token)
  if content is None:
    return Response(StatusResponse(status='Failed', reason='Unable to retrieve email.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  # Step 1: Upload all files - PDF rendition, EML, and attachments
  success, pdf_render, attachments = eml_to_pdf(content)

  # Upload PDF
  pdf_bytes = pdf_render.getvalue()
  pdf_md5 = hashlib.md5(pdf_bytes).hexdigest()
  success = upload_nuxeo_file(config, pdf_bytes, pdf_md5)

  if not success:
    return Response(StatusResponse(status='Failed', reason='Unable to upload PDF rendition.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  
  # Upload original
  content_md5 = hashlib.md5(content).hexdigest() 
  success = upload_nuxeo_file(config, content, content_md5)
  if not success:
    return Response(StatusResponse(status='Failed', reason='Unable to upload EML.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
        
  # Step 3: Create Nuxeo record
  
  # Create record for PDF rendition with EML as Nuxeo attachment
  # TODO: Ask NRMP if this should be added to attachments
  metadata = req.metadata
  identifiers = metadata.identifiers
  identifiers['email_id'] = [req.email_id]
  metadata.identifiers = identifiers
  success, error, uid = create_nuxeo_email_record_v2(config, user_info, metadata, req.nuxeo_env)

  if not success:
    app.logger.error(error)
    return Response(StatusResponse(status='Failed', reason='Unable to create email record.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  # Step 4: Attach blobs
  content_blob = NuxeoBlob(filename=req.metadata.title + '.pdf', mimetype='application/pdf', digest=pdf_md5, length=len(pdf_bytes))
  attachment_blob = NuxeoBlob(filename=req.metadata.title + '.eml', mimetype='application/octet-stream', digest=content_md5, length=len(content))
  success, error = attach_nuxeo_blob(config, uid, content_blob, [attachment_blob], req.nuxeo_env)
  if not success:
    app.logger.error(error)
    return Response(StatusResponse(status='Failed', reason='Unable to link email S3 blobs.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  # Create records for each attachment listing the first record as a parent
  schedule_map = {x.name:x.schedule for x in req.attachment_schedules}
  close_date_map = {x.name:x.close_date for x in req.attachment_schedules}
  disposition_date_map = {x.name:x.disposition_date for x in req.attachment_schedules}
  attachment_uids = []

  for attachment in attachments:
    # Upload attachments
    attachment_name = attachment[0]
    attachment_content = base64.b64decode(attachment[1].encode('ascii'))
    attachment_md5 = hashlib.md5(attachment_content).hexdigest() 
    success = upload_nuxeo_file(config, attachment_content, attachment_md5)
    if not success:
      return Response(StatusResponse(status='Failed', reason='Unable to upload attachment ' + attachment[0] + '.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

    # Create Nuxeo records for each
    metadata = ECMSMetadataV2(
      file_path = req.metadata.file_path,
      custodian = req.metadata.custodian,
      title = attachment[0],
      essential_records="",
      record_schedule = schedule_map.get(attachment[0], req.metadata.record_schedule),
      sensitivity = req.metadata.sensitivity,
      access_restriction_status = req.metadata.access_restriction_status,
      use_restriction_status = req.metadata.use_restriction_status,
      specific_access_restriction = req.metadata.specific_access_restriction,
      specific_use_restriction = req.metadata.specific_use_restriction,
      rights_holder = req.metadata.rights_holder,
      description = req.metadata.description,
      cui_pii_categories = req.metadata.cui_pii_categories,
      creators = req.metadata.creators,
      subjects = req.metadata.subjects,
      spatial_extent = req.metadata.spatial_extent,
      temporal_extent = req.metadata.temporal_extent,
      close_date = close_date_map.get(attachment[0], req.metadata.close_date),
      disposition_date = disposition_date_map.get(attachment[0], req.metadata.disposition_date),
      tags = req.metadata.tags
    )

    success, error, attachment_uid = create_nuxeo_record_v2(config, user_info, metadata, req.nuxeo_env, parent_id=uid)
    if not success:
      app.logger.error('Failed to create attachment record for attachment ' + str(attachment[0] + '. ' + error))
      return Response(StatusResponse(status='Failed', reason='Unable to create attachment record.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    
    # Link attachment blob
    mimetype_guess = mimetypes.guess_type(attachment_name)[0]
    if mimetype_guess is None:
      mimetype_guess = 'application/octet-stream'
    attachment_blob = NuxeoBlob(filename=attachment_name, mimetype=mimetype_guess, digest=attachment_md5, length=len(attachment_content))
    success, error = attach_nuxeo_blob(config, attachment_uid, attachment_blob, [], req.nuxeo_env)
    if not success:
      app.logger.error('Failed to link attachment blob for attachment ' + str(attachment[0] + '. ' + error))
      return Response(StatusResponse(status='Failed', reason='Unable to create attachment record.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    
    attachment_uids.append(attachment_uid)

  # Step 5: Update parent record to contain attachment links as children
  if len(attachment_uids) > 0:
    properties = {'arms:relation_has_part': attachment_uids}
    success = update_nuxeo_metadata(uid, properties, config, req.nuxeo_env)
    if not success:
      return Response(StatusResponse(status='Failed', reason='Failed to update document relationships.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  # Step 6: Mark record saved in Outlook
  save_req = MarkSavedRequestGraph(email_id = req.email_id, sensitivity=req.metadata.sensitivity, mailbox=req.mailbox)
  save_resp = mark_saved(save_req, g.access_token, source)
  if save_resp.status != '200 OK':
    return save_resp
  
  # Step 7: Store submission analytics
  success, response = add_submission_analytics(req.user_activity, req.metadata.record_schedule, user_info.employee_number, None, uid)
  if not success:
    return response
  else:
    log_upload_activity_v2(user_info, req.user_activity, req.metadata, config)
  
  upload_resp = UploadResponse(record_id=req.metadata.record_id, uid=uid)

  return Response(upload_resp.to_json(), status=200, mimetype='application/json')

def create_sems_record(config, req: UploadSEMSEmail, user_info: UserInfo, nuxeo_uid, doc_md5, sems_children):
  sems_request = {
    "metadata": {
      "region": req.metadata.region,
      "programType": req.metadata.program_type,
      "sites": req.metadata.sites,
      "ous": req.metadata.ous,
      "ssids": req.metadata.ssids,
      "recordSchedule": req.metadata.record_schedule.schedule_number + req.metadata.record_schedule.disposition_number,
      "accessControl": req.metadata.access_control,
      "programAreas": req.metadata.program_areas,
      "specialProcessing": req.metadata.special_processing,
      "processingComments": req.metadata.processing_comments,
      "description": req.metadata.description,
      "tags": req.metadata.tags
    },
    "document": {
      "semsUid": req.metadata.sems_uid,
      "fileName": req.metadata.file_name,
      "nuxeoUid": nuxeo_uid,
      "md5Hash": doc_md5,
      "children": sems_children
    },
    "submitter": {
      "email": user_info.email,
      "lanId": user_info.lan_id,
      "firstName": user_info.first_name,
      "lastName": user_info.last_name
    },
    "emailMetadata": {
      "to": req.email_info.to,
      "cc": req.email_info.cc,
      "from": req.email_info._from,
      "date": req.email_info.date,
      "subject": req.email_info.subject,
      "messageId": req.email_id,
      "mailbox": req.mailbox
    }
  }

  try:
    r = requests.post("https://" + config.sems_host + '/sems-ws/outlook/submissions/email', json=sems_request, timeout=60)
    if r.status_code == 200:
      return True, None
    else:
      app.logger.error(r.text)
      return False, "SEMS record creation request returned " + str(r.status_code) + ' response.'
  except:
    app.logger.error(traceback.format_exc())
    return False, "Failed to complete record creation request."

def upload_sems_email(config, req: UploadSEMSEmail, source, user_info):
   # Step 0: Get EML file from graph
  content = get_eml_file(req.email_id, source, req.mailbox, g.access_token)
  if content is None:
    return Response(StatusResponse(status='Failed', reason='Unable to retrieve email.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  # Step 1: Upload all files - PDF rendition, EML, and attachments
  success, pdf_render, attachments = eml_to_pdf(content)

  # Upload PDF
  pdf_bytes = pdf_render.getvalue()
  pdf_md5 = hashlib.md5(pdf_bytes).hexdigest()
  success = upload_nuxeo_file(config, pdf_bytes, pdf_md5)

  if not success:
    return Response(StatusResponse(status='Failed', reason='Unable to upload PDF rendition.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  
  # Upload original
  content_md5 = hashlib.md5(content).hexdigest() 
  success = upload_nuxeo_file(config, content, content_md5)
  if not success:
    return Response(StatusResponse(status='Failed', reason='Unable to upload EML.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
        
  # Step 3: Create Nuxeo record
  
  # Create record for PDF rendition with EML as Nuxeo attachment
  arms_metadata = convert_sems_metadata(user_info, req.metadata)
  identifiers = arms_metadata.identifiers
  identifiers['email_id'] = [req.email_id]
  arms_metadata.identifiers = identifiers
  success, error, uid = create_nuxeo_email_record_v2(config, user_info, arms_metadata, req.nuxeo_env, source_system="SEMS")

  if not success:
    app.logger.error(error)
    return Response(StatusResponse(status='Failed', reason='Unable to create email record.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  # Step 4: Attach blobs
  content_blob = NuxeoBlob(filename=req.metadata.file_name + '.pdf', mimetype='application/pdf', digest=pdf_md5, length=len(pdf_bytes))
  attachment_blob = NuxeoBlob(filename=req.metadata.file_name + '.eml', mimetype='application/octet-stream', digest=content_md5, length=len(content))
  success, error = attach_nuxeo_blob(config, uid, content_blob, [attachment_blob], req.nuxeo_env)
  if not success:
    app.logger.error(error)
    return Response(StatusResponse(status='Failed', reason='Unable to link email S3 blobs.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  # Create records for each attachment listing the first record as a parent
  schedule_map = {x.name:x.record_schedule for x in req.attachment_info}
  attachment_uids = []
  sems_children = []
  for attachment in attachments:
    # Upload attachments
    attachment_name = attachment[0]
    attachment_content = base64.b64decode(attachment[1].encode('ascii'))
    attachment_md5 = hashlib.md5(attachment_content).hexdigest() 
    success = upload_nuxeo_file(config, attachment_content, attachment_md5)
    if not success:
      return Response(StatusResponse(status='Failed', reason='Unable to upload attachment ' + attachment[0] + '.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

    # Create Nuxeo records for each
    metadata = ECMSMetadataV2(
      file_path=attachment_name,
      custodian=user_info.employee_number,
      title=attachment_name,
      record_schedule=schedule_map.get(attachment_name, req.metadata.record_schedule),
      sensitivity=arms_metadata.sensitivity,
      access_restriction_status="",
      use_restriction_status="",
      essential_records="",
      description=req.metadata.description,
      tags=req.metadata.tags
    )

    success, error, attachment_uid = create_nuxeo_record_v2(config, user_info, metadata, req.nuxeo_env, parent_id=uid)
    if not success:
      app.logger.error('Failed to create attachment record for attachment ' + str(attachment[0] + '. ' + error))
      return Response(StatusResponse(status='Failed', reason='Unable to create attachment record.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    
    # Link attachment blob
    mimetype_guess = mimetypes.guess_type(attachment_name)[0]
    if mimetype_guess is None:
      mimetype_guess = 'application/octet-stream'
    attachment_blob = NuxeoBlob(filename=attachment_name, mimetype=mimetype_guess, digest=attachment_md5, length=len(attachment_content))
    success, error = attach_nuxeo_blob(config, attachment_uid, attachment_blob, [], req.nuxeo_env)
    if not success:
      app.logger.error('Failed to link attachment blob for attachment ' + str(attachment[0]) + '. ' + error)
      return Response(StatusResponse(status='Failed', reason='Unable to create attachment record.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    
    attachment_uids.append(attachment_uid)

    for sems_attachment in req.attachment_info:
      if sems_attachment.name == attachment_name:
        sems_children.append({"semsUid": sems_attachment.sems_uid, "fileName": attachment_name, "nuxeoUid": attachment_uid, "md5Hash": attachment_md5})

  # Step 5: Update parent record to contain attachment links as children
  if len(attachment_uids) > 0:
    properties = {'arms:relation_has_part': attachment_uids}
    success = update_nuxeo_metadata(uid, properties, config, req.nuxeo_env)
    if not success:
      return Response(StatusResponse(status='Failed', reason='Failed to update document relationships.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

  # Step 6: Submit record to SEMS
  success, error = create_sems_record(config, req, user_info, uid, content_md5, sems_children)
  if not success:
      app.logger.error('Failed to create SEMS record for Nuxeo UID ' + str(uid) + '. ' + error)
      return Response(StatusResponse(status='Failed', reason='Unable to create SEMS record.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    
  # Step 7: Mark record saved in Outlook
  save_req = MarkSavedRequestGraph(email_id = req.email_id, sensitivity=arms_metadata.sensitivity, mailbox=req.mailbox)
  save_resp = mark_saved(save_req, g.access_token, source, saved_cat="Saved to SEMS")
  if save_resp.status != '200 OK':
    return save_resp
  
  upload_resp = UploadResponse(record_id=req.record_id, uid=uid)

  return Response(upload_resp.to_json(), status=200, mimetype='application/json')

def add_submission_analytics(data: SubmissionAnalyticsMetadata, selected_schedule, employee_number, documentum_id, nuxeo_id):
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
  user = User.query.filter_by(employee_number = employee_number).all()
  if len(user) == 0:
      user = User(employee_number = employee_number)
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
    app.logger.error(traceback.format_exc())
    return False, Response(StatusResponse(status='Failed', reason="Error committing submission analytics.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype="application/json")

def update_sharepoint_record_status(site_id, list_id, item_id, status, access_token):
  url = 'https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items/{item_id}/fields'.format(site_id = site_id, list_id = list_id, item_id = item_id)
  headers = {'Authorization': 'Bearer ' + access_token}
  data = {"Records_x0020_Status": status}
  update_req = requests.patch(url, json=data, headers=headers, timeout=30)
  if update_req.status_code != 200:
    app.logger.error('Unable to update item with item_id = ' + item_id + ': ' + update_req.text)
    return False, Response(StatusResponse(status='Failed', reason='Unable to update some items.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
  else:
    return True, None

def get_help_item(req: GetHelpItemRequest):
  items = help_item_cache.get_help_items()
  for item in items:
    if item.name == req.name:
      return Response(item.to_json(), status=200, mimetype='application/json')
  return Response(StatusResponse(status='Failed', reason='Item not found.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')

def get_all_help_items():
  items = AllHelpItemsResponse(help_items=help_item_cache.get_help_items())
  return Response(items.to_json(), status=200, mimetype='application/json')

def update_help_items():
  try:
    help_item_cache.update_help_items()
    return Response(StatusResponse(status='Success', reason='Help items cache updated.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')
  except:
    app.logger.error(traceback.format_exc())
    return Response(StatusResponse(status='Failed', reason='Help item cache update failed.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

def log_upload_activity(user_info, user_activity, metadata, config, count=1):
  safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '3', config, count)
  if user_activity is not None and not user_activity.used_default_schedule or user_activity.used_schedule_dropdown or user_activity.used_recommended_schedule:
      safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '4', config)
  if metadata is not None and len(metadata.description) > 0 or metadata.close_date is not None or metadata.rights is not None or metadata.coverage is not None or metadata.relationships is not None or metadata.tags is not None:
      safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '6', config)

def log_upload_activity_v2(user_info, user_activity, metadata, config, count=1):
  safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '3', config, count)
  if user_activity is not None and not user_activity.used_default_schedule or user_activity.used_schedule_dropdown or user_activity.used_recommended_schedule:
      safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '4', config)
  if metadata is not None and len(metadata.description) > 0 or metadata.close_date is not None or len(metadata.spatial_extent) > 0 or len(metadata.temporal_extent) > 0 or len(metadata.subjects) > 0 or len(metadata.tags) > 0 or metadata.identifiers is not None:
      safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '6', config)

def safe_user_activity_request(employee_id, lan_id, office_code, event_id, config, count=1):
  try:
    activity_request = LogActivityRequest(employee_id=employee_id, lan_id=lan_id, office_code=office_code, event_id=event_id, bulk_number=count)
    success, error_status = user_activity_request(activity_request, config)
    if not success:
        app.logger.info('Failed to log user activity for ' + lan_id + '. Activity request failed with status ' + str(error_status))
  except:
    app.logger.error(traceback.format_exc())
    app.logger.info('Failed to log user activity for ' + lan_id)

def user_activity_request(req: LogActivityRequest, config):
  params={'employee_id':req.employee_id, 'lan_id':req.lan_id, 'bulk_number':req.bulk_number, 'office_code':req.office_code, 'event_id':req.event_id, 'api_key':config.patt_api_key}
  url = 'https://' + config.patt_host + '/app/mu-plugins/pattracking/includes/admin/pages/games/activity.php'
  r = requests.post(url, params=params)
  if r.status_code == 200:
    return True, None
  else:
    return False, r.status_code

def log_user_activity(req: LogActivityRequest, config):
  success, error_status = user_activity_request(req, config)
  if not success:
    return Response(StatusResponse(status='OK', reason='Failed to log activity with status ' + str(error_status), request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
  else:
    return Response(StatusResponse(status='OK', reason='Successfully logged user activity.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')

def get_file_metadata_prediction(config, file, prediction_metadata: PredictionMetadata):
  file_obj = file.read()
  success, tika_result, response = tika(file_obj, config)
  if not success:
      return response
  if tika_result.is_encrypted:
    prediction = MetadataPrediction(predicted_schedules=[], title=mock_prediction_with_explanation, is_encrypted=True, description=mock_prediction_with_explanation, default_schedule=None, subjects=[], identifiers={}, cui_categories=tika_result.cui_categories)
    return Response(prediction.to_json(), status=200, mimetype='application/json')
  keyword_weights = keyword_extractor.extract_keywords(tika_result.text)
  keywords = [x[0] for x in sorted(keyword_weights.items(), key=lambda y: y[1], reverse=True)][:5]
  subjects=keyword_extractor.extract_subjects(tika_result.text, keyword_weights)
  has_capstone=capstone_detector.detect_capstone_text(tika_result.text)
  identifiers=identifier_extractor.extract_identifiers(tika_result.text)
  spatial_extent, temporal_extent = identifier_extractor.extract_spatial_temporal(tika_result.text)

  # Auto detect schedule from path
  mapping = schedule_cache.get_schedule_mapping()
  default_schedule = None
  predicted_schedules = []
  if prediction_metadata.file_path is not None:
    for item in prediction_metadata.file_path.split('\\'):
      detected_schedule = detect_schedule_from_string(item, mapping)
      if detected_schedule is not None:
        default_schedule = detected_schedule
        predicted_schedules.append(Recommendation(schedule=default_schedule, probability=1))
        break

  # If not found then make prediction
  if default_schedule is None:
    predicted_schedules, default_schedule = model.predict(tika_result.text, 'document', prediction_metadata, has_capstone, keywords, subjects, attachments=[])
  predicted_title = mock_prediction_with_explanation
  predicted_description = mock_prediction_with_explanation

  prediction = MetadataPrediction(
      predicted_schedules=predicted_schedules, 
      title=predicted_title, 
      description=predicted_description, 
      default_schedule=default_schedule, 
      subjects=subjects, 
      identifiers=identifiers,
      cui_categories=tika_result.cui_categories,
      is_encrypted=tika_result.is_encrypted,
      spatial_extent=spatial_extent,
      temporal_extent=temporal_extent
      )
  return Response(prediction.to_json(), status=200, mimetype='application/json')

def create_batch(req: BatchUploadRequest, user_info):
  user = User.query.filter_by(employee_number = user_info.employee_number).all()
  if len(user) == 0:
      return Response(StatusResponse(status='Failed', reason='User not found.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
  else:
      user = user[0]
  aa_ship = user_info.parent_org_code[0] + '0000000'
  batch = BatchUpload(status=BatchUploadStatus.PENDING, source=BatchUploadSource[req.source], system=req.system, email_source=req.email_source, email=user_info.email, mailbox=req.mailbox, upload_metadata=req.metadata.to_dict(), user_id=user.id, employee_number=user_info.employee_number, program_office=user_info.manager_parent_org_code, aa_ship=aa_ship)
  db.session.add(batch)
  try:
    db.session.commit()
    return Response(StatusResponse(status='OK', reason='Successfully added batch.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')
  except:
    app.logger.error(traceback.format_exc())
    return Response(StatusResponse(status='Failed', reason='Failed to add batch.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

def get_users(req: SearchUsersRequest, c):
  url = "https://" + c.wam_host + "/iam/governance/scim/v1/Users?filter=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Upn sw " + req.prefix + "&attributes=active&attributes=displayName&attributes=urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber&attributes=urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User:Upn&count=" + str(req.count)
  wam = requests.get(url, auth=(c.wam_username, c.wam_password), timeout=30)
  users = []
  for user_data in wam.json()['Resources']:
    employee_number = user_data.get('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User', {}).get('employeeNumber', None)
    email = user_data.get('urn:ietf:params:scim:schemas:extension:oracle:2.0:OIG:User', {}).get('Upn', None)
    display_name = user_data.get('displayName', None)
    user_info = WAMUserInfo(employee_number=employee_number, email=email, display_name=display_name)
    if email.lower() != g.token_data['email'].lower():
      users.append(user_info)
  return Response(UserSearchResponse(users=users).to_json(), status=200, mimetype='application/json')

def validate_custodian(metadata: ECMSMetadataV2, user_info: UserInfo):
  rules = DelegationRule.query.filter_by(submitting_user_employee_number=user_info.employee_number, target_user_employee_number=metadata.custodian).all()
  if len(rules) > 0:
    return True, None
  else:
    return False, Response(StatusResponse(status='Failed', reason='User is not authorized to submit on behlaf of this custodian.', request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
