from flask import Flask, request, Response, make_response, send_file
from flask import current_app as app
from .cis_requests import *
from werkzeug.utils import secure_filename
from .data_classes import * 
import json
import urllib
from io import BytesIO
from .models import User, Favorite, db
from . import key_cache, c, model, mailbox_manager, schedule_cache, sems_site_cache
XTIKA_CUTOFF = 10

@app.route('/file_metadata_prediction', methods=['POST'])
def file_metadata_prediction():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    file = request.files.get('file')
    if file:
        filename = secure_filename(file.filename)
        extension = filename.split('.')[-1]
        success, text, response = tika(file, c)
        if not success:
            return response
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
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = request.args
    req = EmailPredictionRequest(**req)
    eml_file = get_eml_file(req.email_id, "default_file_name", access_token, c)
    if eml_file is None:
        return Response("Could not retrieve eml file.", status=400, mimetype='text/plain')
    success, text, response = tika(eml_file, c, extraction_type='text')
    if not success:
        return response
    predicted_schedules = model.predict(text)
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description)
    return prediction.to_json()

## TODO: Implement file upload
@app.route('/upload_file', methods=['POST'])
def upload_file():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
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
    return mailbox_manager.list_shared_mailboxes(token_data['email'])

@app.route('/get_emails', methods=['GET'])
def get_emails():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = dict(request.args)
    if 'items_per_page' not in req:
        req['items_per_page'] = req.pop('count', 10)
    if 'page_number' not in req:
        req['page_number'] = 1
    req = GetEmailRequest(items_per_page=int(req['items_per_page']), page_number=int(req['page_number']), mailbox=req['mailbox'])
    if not mailbox_manager.validate_mailbox(token_data['email'], req.mailbox):
        return Response("User " + token_data['email'] + " is not authorized to access " + req.mailbox + ".", status=401, mimetype='text/plain')
    return list_email_metadata(req, token_data['email'], access_token, c)

@app.route('/get_attachment', methods=['GET'])
def get_attachment():
    valid, message, _ = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = request.args
    req = DownloadAttachmentRequest(**req)
    return download_attachment(req, access_token, c)

@app.route('/describe_email', methods=['GET'])
def get_email_description():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = request.args
    req = DescribeEmailRequest(**req)
    return describe_email(req, access_token, c)

@app.route('/get_email_body', methods=['GET'])
def get_body():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = request.args
    req = GetEmailBodyRequest(**req)
    return get_email_body(req, access_token, c)

## TODO: Implement email upload
@app.route('/upload_email', methods=['POST'])
def upload_email():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = request.json
    schedule = RecordSchedule(**req['metadata']['record_schedule'])
    req['metadata']['record_schedule'] = schedule
    metadata = ECMSMetadata(**req['metadata'])
    req['metadata'] = metadata
    req = UploadEmailRequest(**req)
    # TODO: Improve custodian validation based on role
    if metadata.custodian != lan_id:
        return Response('User ' + lan_id + ' is not authorized to list ' + req.metadata.custodian + ' as custodian.', status=400, mimetype='text/plain')
    return upload_documentum_email(req, access_token, c)

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
    content = get_eml_file(req.email_id, req.file_name, access_token, c)
    if content is None:
        Response("File download failed. Ensure that email_id is valid.", status=500, mimetype='text/plain')
    return send_file(BytesIO(content), attachment_filename=req.file_name, as_attachment=True)

@app.route('/mark_email_saved', methods=['POST'])
def mark_email_saved():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = request.json
    req = MarkSavedRequest(**req)
    return mark_saved(req, access_token, c)

@app.route('/untag_email', methods=['POST'])
def untag_email():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    access_token = request.headers.get('X-Access-Token')
    if access_token is None:
        return Response("X-Access-Token is required.", status=400, mimetype='text/plain')
    req = request.json
    req = UntagRequest(**req)
    return untag(req, access_token, c)

@app.route('/get_favorites', methods=['GET'])
def get_favorites():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        get_favorites_response = GetFavoritesResponse(favorites = [])
    else:
        user = user[0]
        schedules = [RecordSchedule(function_number=f.function_number, schedule_number=f.schedule_number, disposition_number=f.disposition_number) for f in user.favorites]
        get_favorites_response = GetFavoritesResponse(favorites=schedules)
    return get_favorites_response.to_json()

@app.route('/add_favorites', methods=['POST'])
def add_favorites():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.json
    try:
        req = AddFavoritesRequest(**req)
    except:
        Response("Unable to parse request.", status=400, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        user = User(lan_id = user_info.lan_id)
        db.session.add(user)
    else:
        user = user[0]
    add_any_sched = False
    for sched in req.record_schedules:
        add_sched = True
        for fav in user.favorites:
            if fav.function_number == sched['function_number'] and fav.schedule_number == sched['schedule_number'] and fav.disposition_number == sched['disposition_number']:
                add_sched = False
                break
        if add_sched:
            add_any_sched = True
            user.favorites.append(Favorite(function_number=sched['function_number'], schedule_number=sched['schedule_number'], disposition_number=sched['disposition_number'], user=user))
    if add_any_sched:
        try:
            db.session.commit()
            return Response(StatusResponse(status="OK", reason="Favorites were added.").to_json(), status=200, mimetype="application/json")
        except:
            return Response("Error committing updates.", status=500, mimetype="text/plain")
    else:
        return Response(StatusResponse(status="OK", reason="All favorites given were already in the database.").to_json(), status=200, mimetype="text/plain")

@app.route('/remove_favorites', methods=['POST'])
def remove_favorites():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    req = request.json
    req = RemoveFavoritesRequest(**req)
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        user = User(lan_id = user_info.lan_id)
    else:
        user = user[0]

    for fav in user.favorites:
        for sched in req.record_schedules:
            if fav.function_number == sched['function_number'] and fav.schedule_number == sched['schedule_number'] and fav.disposition_number == sched['disposition_number']:
                db.session.delete(fav)
    db.session.commit()
    return Response(StatusResponse(status="OK", reason="Favorites were removed.").to_json(), status=200, mimetype="application/json")

@app.route('/get_record_schedules', methods=['GET'])
def get_record_schedules():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    try:
        schedules = schedule_cache.get_schedules()
        return Response(schedules.to_json(), status=200, mimetype='application/json')
    except:
        # TODO: Improve error logging
        return Response("Record schedules unable to be found.", status=500, mimetype='text/plain')

@app.route('/my_records', methods=['GET'])
def my_records():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    req = request.args
    req = MyRecordsRequest(**req)
    if user_info.lan_id != req.lan_id:
        return Response('User ' + user_info.lan_id + ' is not authorized to download records for ' + req.lan_id + '.', status=401, mimetype='text/plain')
    return get_documentum_records(c, user_info.lan_id, req.items_per_page, req.page_number)

@app.route('/my_records_count', methods=['GET'])
def my_records_count():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    return get_documentum_record_count(c, user_info.lan_id)

@app.route('/get_user_info', methods=['GET'])
def user_info():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    return Response(user_info.to_json(), status=200, mimetype='application/json')

@app.route('/my_records_download', methods=['GET'])
def my_records_download():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    success, message, user_info = get_user_info(c, token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    req = request.args
    req = RecordDownloadRequest(**req)
    # TODO: Sanitize object ids.
    if user_info.lan_id != req.lan_id:
        return Response('User ' + user_info.lan_id + ' is not authorized to download records for ' + req.lan_id + '.', status=401, mimetype='text/plain')
    return download_documentum_record(c, user_info.lan_id, req.object_ids.split(','))

@app.route('/get_sites', methods=['GET'])
def get_sites():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.args
    req = GetSitesRequest(**req)
    sites = sems_site_cache.get_sites(req.region)
    return Response(GetSitesResponse(sites).to_json(), status=200, mimetype='application/json')

@app.route('/get_special_processing', methods=['GET'])
def get_special_processing():
    valid, message, token_data = key_cache.validate_request(request, c)
    if not valid:
        return Response(message, status=401, mimetype='text/plain')
    req = request.args
    req = GetSpecialProcessingRequest(**req)
    return get_sems_special_processing(c, req.region)