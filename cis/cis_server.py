from flask import Flask, request
from cis_requests import *
from config import *
from waitress import serve
from werkzeug.utils import secure_filename
from hf_model import HuggingFaceModel
import argparse
from data_classes import * 
from flask_swagger_ui import get_swaggerui_blueprint
from yaml import Loader, load
import json
import urllib

app = Flask(__name__)
SWAGGER_URL = ''  # URL for exposing Swagger UI
SWAGGER_PATH = 'swagger.yaml'
swagger_yml = load(open(SWAGGER_PATH, 'r'), Loader=Loader)


XTIKA_CUTOFF = 10
c = None
model = None


@app.route('/file_metadata_prediction', methods=['POST'])
def file_metadata_prediction():
    file = request.files.get('file')
    if file:
        filename = secure_filename(file.filename)
        extension = filename.split('.')[-1]
        text = tika(file, c)
        if extension == 'pdf' and len(text) < XTIKA_CUTOFF:
            text = xtika(file, c)
        predicted_schedules = model.predict(text)
        predicted_title = mock_prediction_with_explanation
        predicted_description = mock_prediction_with_explanation
        prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description)
        return prediction.to_json()
    else:
        return {'error': 'No file found.'}

@app.route('/text_metadata_prediction', methods=['POST'])
def text_metadata_prediction():
    req = request.json
    req = TextPredictionRequest(**req)
    predicted_schedules = model.predict(req.text)
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description)
    return prediction.to_json()

@app.route('/email_metadata_prediction', methods=['POST'])
def email_metadata_prediction():
    req = request.json
    req = EmailPredictionRequest(**req)
    prediction = mock_metadata_prediction
    return prediction.to_json()

@app.route('/upload_file', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    metadata = ECMSMetadata(**json.loads(request.form['metadata']))
    if file:
        return mock_status_response.to_json()
    else:
        return {'error': 'No file found.'}

@app.route('/get_mailboxes', methods=['POST'])
def get_mailboxes():
    req = request.json
    req = GetMailboxesRequest(**req)
    return mock_get_mailboxes_response.to_json()

@app.route('/get_emails', methods=['POST'])
def get_emails():
    req = request.json
    req = GetEmailRequest(**req)
    return mock_get_email_response.to_json()

@app.route('/upload_email', methods=['POST'])
def upload_email():
    req = request.json
    req = UploadEmailRequest(**req)
    return mock_status_response.to_json()

## TODO: Make this return a real EML file.
@app.route('/download_email', methods=['POST'])
def download_email():
    req = request.json
    req = DownloadEmailRequest(**req)
    return mock_status_response.to_json()

@app.route('/mark_email_saved', methods=['POST'])
def mark_email_saved():
    req = request.json
    req = MarkSavedRequest(**req)
    return mock_status_response.to_json()

@app.route('/untag_email', methods=['POST'])
def untag_email():
    req = request.json
    req = UntagRequest(**req)
    return mock_status_response.to_json()

@app.route('/get_favorites', methods=['POST'])
def get_favorites():
    req = request.json
    req = GetFavoritesRequest(**req)
    return mock_get_favorites_response.to_json()

@app.route('/add_favorites', methods=['POST'])
def add_favorites():
    req = request.json
    req = AddFavoritesRequest(**req)
    return mock_status_response.to_json()

@app.route('/remove_favorites', methods=['POST'])
def remove_favorites():
    req = request.json
    req = RemoveFavoritesRequest(**req)
    return mock_status_response.to_json()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='The CIS backend server provides APIs which power the EZDesktop application.')
    parser.add_argument('--model_path', 
                    help='Path to HuggingFace classifier model.')
    parser.add_argument('--label_mapping_path', 
                    help='Path to mapping between prediction indices and corresponding record schedules.')
    parser.add_argument('--config_path', default='dev_config.json',
                    help='Path to config file with environment dependent variables.')
    parser.add_argument('--tika_server', default=None,
                    help='Host for tika service.')
    parser.add_argument('--cis_server', default=None,
                    help='Host for tika service.')
    args = parser.parse_args()
    model = HuggingFaceModel(args.model_path, args.label_mapping_path)
    c = config_from_file(args.config_path)
    if args.tika_server:
        c.tika_server = args.tika_server
    if args.cis_server:
        c.cis_server = args.cis_server
    swagger_yml['host'] = urllib.parse.urlparse(c.cis_server).netloc
    blueprint = get_swaggerui_blueprint(SWAGGER_URL, SWAGGER_PATH, config={'spec': swagger_yml})
    app.register_blueprint(blueprint)
    serve(app, host='0.0.0.0', port=8000)

