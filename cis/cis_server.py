from flask import Flask, request
from cis_requests import *
from config import *
from waitress import serve
from werkzeug.utils import secure_filename
from hf_model import HuggingFaceModel
import argparse
from data_classes import * 

app = Flask(__name__)
XTIKA_CUTOFF = 10
c = None
model = None


@app.route('/record_schedule_prediction', methods=['POST'])
def record_schedule_prediction():
    file = request.files.get('file')
    if file:
        filename = secure_filename(file.filename)
        extension = filename.split('.')[-1]
        text = tika(file, c)
        if extension == 'pdf' and len(text) < XTIKA_CUTOFF:
            text = xtika(file, c)
        prediction = model.predict(text)
        return {'predictions': prediction}
    else:
        return {'error': 'No file found.'}

@app.route('/get_favorites', methods=['POST'])
def get_favorites():
    data = request.json()
    lan_id = data['lan_id']
    return ["108-1035-b"]



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='The CIS backend server provides APIs which power the EZDesktop application.')
    parser.add_argument('--model_path', 
                    help='Path to HuggingFace classifier model.')
    parser.add_argument('--label_mapping_path', 
                    help='Path to mapping between prediction indices and corresponding record schedules.')
    parser.add_argument('--config_path', default='dev_config.json',
                    help='Path to config file with environment dependent variables.')
    args = parser.parse_args()
    model = HuggingFaceModel(args.model_path, args.label_mapping_path)
    c = config_from_file(args.config_path)
    serve(app, host='0.0.0.0', port=8000)

