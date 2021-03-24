import requests
from .data_classes import *
import json 
import email
from flask import Response, current_app as app

def deep_detect_classify(text, config, threshold=0.4):
    data = {
          "service": 'records',
          "parameters": {
            "input": {},
            "output": {
              "confidence_threshold": threshold
            },
            "mllib": {
              "gpu": False
            }
          },
          "data": [text]
        }
    server = config.deep_detect_api_server + '/predict'
    r = requests.post(server,json=data)
    #return r.json()['body']['predictions'][0]['classes'][0]
    return r.json()

def nlp_buddy_analyze(text, config):
    data = { "text":  text }
    server = config.nlp_buddy_server + '/api/analyze'
    r = requests.post(server,json=data)
    return r.json()

def tika(file, config):
    files = {'file': file}
    headers = {
                "Cache-Control": "no-cache",
                "accept": "text/plain"
              }
    server = "http://" + config.tika_server + '/tika/form'
    r = requests.post(server, files=files, headers=headers)
    return r.text

def xtika(file, config):
    headers = {
              "Content-Type" : "application/pdf",
              "X-Tika-PDFOcrStrategy": "ocr_only",
              "Cache-Control": "no-cache",
              "accept": "text/plain"
            }
    server = "http://" + config.tika_server + "/tika"
    r = requests.put(server, data=file, headers=headers)
    return r.text

def get_eml_file(email_id, file_name, access_token, config):
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"filename":file_name, "emailid":email_id}
  r = requests.get("http://" + config.ezemail_server + "/ezemail/v1/getemlfile", data=json.dumps(body), headers=headers)
  if r.status_code == 200:
    return r.content
  else:
    return None

def extract_eml_content(eml_message):
  body = ""
  attachments = []
  for part in eml_message.walk():
    content_type = part.get_content_type()
    charset = part.get_content_charset()
    disposition = part.get_content_disposition()
    
    if content_type == 'text/plain' and charset is not None and disposition is None:
        text = part.get_payload()
        try:
            body = text.decode(charset).encode('utf-8')
        except:
            body = text
    
    if disposition == 'attachment':
        attachments.append(part.get_filename())
  return body, attachments


def extract_eml_data(eml_bytes, email_id):
  e = email.message_from_bytes(eml_bytes)
  body, attachments = extract_eml_content(e)
  return DescribeEmailResponse(
    email_id=email_id, 
    _from = e['From'],
    to = e['To'],
    cc = e['CC'],
    subject = e['Subject'],
    date = e['Date'],
    body = body,
    attachments = attachments
  )

def describe_email(req: DescribeEmailRequest, access_token, config):
  eml_file = get_eml_file(req.email_id, "default_file_name", access_token, config)
  if eml_file is None:
    return Response("Could not retrieve eml file.", status=400, mimetype='text/plain')
  try:
    eml_response = extract_eml_data(eml_file, req.email_id)
  except:
    return Response("Error extracting data from eml file.", status=500, mimetype='text/plain')
  return Response(eml_response.to_json(), status=200, mimetype='application/json')
  

def list_email_metadata(req: GetEmailRequest, access_token, config):
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + access_token}
  body = {"mailbox": req.mailbox, "count": req.count}
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
  p = requests.post(
    "http://" + config.ezemail_server + "/ezemail/v1/setcategory", 
    json=body, 
    headers=headers
  )
  if p.status_code != 204:
    return Response("Unable to mark as saved.", status=400, mimetype='text/plain')
  else:
    return Response(StatusResponse(status="OK", reason="Email with id " + req.email_id + "was marked saved.").to_json(), status=200, mimetype="application/json")

def get_lan_id(display_name):
  pass