import requests
from data_classes import *
import json 
from io import BytesIO

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
    return BytesIO(r.content)
  else:
    return None

def list_email_metadata(req: GetEmailRequest, config):
  headers = {"Content-Type": "application/json", "Authorization": "Bearer " + req.access_token}
  body = {"mailbox": req.mailbox, "count": req.count}
  p = requests.get(
    "http://" + config.ezemail_server + "/ezemail/v1/getrecords/", 
    data=json.dumps(body), 
    headers=headers
  )
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
  return GetEmailResponse(total_count=total_count, emails=emails)
