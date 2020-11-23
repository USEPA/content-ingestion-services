from flask import Flask, request
from cis.cis_requests import *
from cis.config import *
from waitress import serve
from werkzeug.utils import secure_filename

app = Flask(__name__)
XTIKA_CUTOFF = 10
c = config_from_file('dev_config.json')

@app.route('/record_schedule_prediction', methods=['POST'])
def record_schedule_prediction():
    file = request.files.get('file')
    if file:
        filename = secure_filename(file.filename)
        extension = filename.split('.')[-1]
        text = tika(file, c)
        if extension == 'pdf' and len(text) < XTIKA_CUTOFF:
            text = xtika(file, c)
        text = nlp_buddy_analyze(text, c)['summary']
        prediction = deep_detect_classify(text, c)
        return {'prediction': prediction}
    else:
        return {'error': 'No file found.'}

if __name__ == "__main__":
    serve(app, host='0.0.0.0', port=8000)
