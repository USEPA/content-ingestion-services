import requests

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