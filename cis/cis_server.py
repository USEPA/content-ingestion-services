from flask import Flask, request, Response, make_response
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
from validation import PublicKeyCache
from werkzeug import FileWrapper

app = Flask(__name__)
SWAGGER_URL = ''  # URL for exposing Swagger UI
SWAGGER_PATH = 'swagger.yaml'
swagger_yml = load(open(SWAGGER_PATH, 'r'), Loader=Loader)
key_cache = PublicKeyCache()

XTIKA_CUTOFF = 10
c = None
model = None

@app.route('/file_metadata_prediction', methods=['POST'])
def file_metadata_prediction():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
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

@app.route('/text_metadata_prediction', methods=['GET'])
def text_metadata_prediction():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')    
    req = request.args
    req = TextPredictionRequest(**req)
    predicted_schedules = model.predict(req.text)
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description)
    return prediction.to_json()

@app.route('/email_metadata_prediction', methods=['GET'])
def email_metadata_prediction():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')   
    req = request.args
    req = EmailPredictionRequest(**req)
    prediction = mock_metadata_prediction
    return prediction.to_json()

@app.route('/upload_file', methods=['POST'])
def upload_file():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    file = request.files.get('file')
    metadata = ECMSMetadata(**json.loads(request.form['metadata']))
    if file:
        return mock_status_response.to_json()
    else:
        return {'error': 'No file found.'}

@app.route('/get_mailboxes', methods=['GET'])
def get_mailboxes():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.args
    try:
        req = GetMailboxesRequest(**req)
    except:
        Response("Unable to parse request.", status=400, mimetype='text/plain')
    return mock_get_mailboxes_response.to_json()

@app.route('/get_emails', methods=['GET'])
def get_emails():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.args
    req = GetEmailRequest(**req)
    return list_email_metadata(req, c).to_json()

@app.route('/describe_email', methods=['GET'])
def describe_email():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.args
    req = DescribeEmailRequest(**req)
    return {}

@app.route('/upload_email', methods=['POST'])
def upload_email():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.json
    req = UploadEmailRequest(**req)
    return mock_status_response.to_json()

## TODO: Make this return a real EML file.
@app.route('/download_email', methods=['GET'])
def download_email():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = request.args
    try:
        req = DownloadEmailRequest(**req)
    except:
        Response("Unable to parse request.", status=400, mimetype='text/plain')
    file = get_eml_file(req.email_id, req.file_name, access_token, c)
    if file is None:
        Response("File download failed. Ensure that email_id is valid.", status=500, mimetype='text/plain')
    resp = make_response(FileWrapper(file))
    resp.headers['Content-Type'] = 'application/octet-stream'
    resp.headers['Content-Disposition'] = 'attachment;filename=' + req.file_name
    return resp

@app.route('/mark_email_saved', methods=['POST'])
def mark_email_saved():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.json
    req = MarkSavedRequest(**req)
    return mock_status_response.to_json()

@app.route('/untag_email', methods=['POST'])
def untag_email():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.json
    req = UntagRequest(**req)
    return mock_status_response.to_json()

@app.route('/get_favorites', methods=['GET'])
def get_favorites():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.args
    req = GetFavoritesRequest(**req)
    return mock_get_favorites_response.to_json()

@app.route('/add_favorites', methods=['POST'])
def add_favorites():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.json
    req = AddFavoritesRequest(**req)
    return mock_status_response.to_json()

@app.route('/remove_favorites', methods=['POST'])
def remove_favorites():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
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
                    help='Host for this (CIS) service.')
    parser.add_argument('--ezemail_server', default=None,
                    help='Host for ezemail service.')
    args = parser.parse_args()
    model = HuggingFaceModel(args.model_path, args.label_mapping_path)
    c = config_from_file(args.config_path)
    if args.tika_server:
        c.tika_server = args.tika_server
    if args.cis_server:
        c.cis_server = args.cis_server
    if args.ezemail_server:
        c.ezemail_server = args.ezemail_server
    swagger_yml['host'] = c.cis_server
    blueprint = get_swaggerui_blueprint(SWAGGER_URL, SWAGGER_PATH, config={'spec': swagger_yml})
    app.register_blueprint(blueprint)
    serve(app, host='0.0.0.0', port=8000)

