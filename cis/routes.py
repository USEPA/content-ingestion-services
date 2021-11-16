from flask import request, Response, send_file, g
from flask import current_app as app
from .cis_requests import *
from werkzeug.utils import secure_filename
from .data_classes import * 
from io import BytesIO
from .models import User, Favorite, db
import uuid
from . import key_cache, c, model, mailbox_manager, schedule_cache, sems_site_cache
import json

@app.before_request
def log_request_info():
    if 'favicon' not in request.path and 'swagger' not in request.path and request.path != '/':
        valid, message, token_data = key_cache.validate_request(request, c)
        if not valid:
            return Response(message, status=401, mimetype='text/plain')
        else:
            g.token_data = token_data
            g.request_id = str(uuid.uuid4())
            g.access_token = request.headers.get('X-Access-Token')
        log_headers = dict(request.headers)
        # Remove sensitive information from logs
        log_headers.pop('Authorization', None)
        log_headers.pop('X-Access-Token', None)
        log_headers.pop('Cookie', None)
        log_data = {
            'request_id': g.request_id, 
            'path': request.path, 
            'user': token_data['email'], 
            'headers': log_headers,
            'remote_addr': request.remote_addr
            }
        app.logger.info('Incoming request -- ' + json.dumps(log_data))

@app.after_request
def after_request_func(response):
    log_data = {
        'request_id': g.pop('request_id', None),
        'user': g.pop('token_data', {}).get('email'),
        'status': response.status,
        'message': None
    }
    if response.status != '200 OK':
        log_data['message'] = str(response.get_data(as_text=True))
    app.logger.info('Request complete -- ' + json.dumps(log_data))
    return response

@app.route('/file_metadata_prediction', methods=['POST'])
def file_metadata_prediction():
    file = request.files.get('file')
    if file:
        #filename = secure_filename(file.filename)
        success, text, response = tika(file, c)
        if not success:
            return response
        predicted_schedules, default_schedule = model.predict(text)
        predicted_title = mock_prediction_with_explanation
        predicted_description = mock_prediction_with_explanation
        prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule)
        return Response(prediction.to_json(), status=200, mimetype='application/json')
    else:
        return Response("No file found.", status=400, mimetype='text/plain')

@app.route('/text_metadata_prediction', methods=['POST'])
def text_metadata_prediction():  
    req = request.json
    req = TextPredictionRequest.from_dict(req)
    predicted_schedules, default_schedule = model.predict(req.text)
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule)
    return Response(prediction.to_json(), status=200, mimetype='application/json')

@app.route('/email_metadata_prediction', methods=['GET'])
def email_metadata_prediction():
    if g.access_token is None:
        return Response("X-Outlook-Token is required.", status=400, mimetype='text/plain')
    req = request.args
    req = EmailPredictionRequest.from_dict(req)
    eml_file = get_eml_file(req.email_id, "default_file_name", g.access_token, c)
    if eml_file is None:
        return Response("Could not retrieve eml file.", status=400, mimetype='text/plain')
    success, text, response = tika(eml_file, c, extraction_type='text')
    if not success:
        return response
    schedules = schedule_cache.get_schedules().schedules
    valid_schedules = list(filter(lambda x: x.ten_year, schedules))
    valid_schedules = ["{fn}-{sn}-{dn}".format(fn=x.function_number, sn=x.schedule_number, dn=x.disposition_number) for x in valid_schedules]
    predicted_schedules, default_schedule = model.predict(text, valid_schedules=valid_schedules)
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule)
    return Response(prediction.to_json(), status=200, mimetype='application/json')

@app.route('/upload_file', methods=['POST'])
def upload_file():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    file = request.files.get('file')
    metadata = ECMSMetadata.from_json(request.form['metadata'])
    user_activity = SubmissionAnalyticsMetadata.from_json(request.form['user_activity'])
    # Default to dev environment
    env = request.form.get('documentum_env', 'dev')
    if metadata.custodian != user_info.lan_id:
        return Response('User ' + user_info.lan_id + ' is not authorized to list ' + metadata.custodian + ' as custodian.', status=400, mimetype='text/plain')
    if file is None:
        return Response("No file found.", status=400, mimetype="text/plain")
    success, r_object_id, response = upload_documentum_record(file, convert_metadata(metadata), c, env)
    if not success:
        return response
    # Add submission analytics
    success, response = add_submission_analytics(user_activity, metadata.record_schedule, user_info.lan_id, r_object_id, None)
    if not success:
        return response
    else:
        log_upload_activity(user_info, user_activity, metadata, c)
        return Response(StatusResponse(status='OK', reason='File successfully uploaded.').to_json(), status=200, mimetype='text/plain')
        

@app.route('/get_mailboxes', methods=['GET'])
def get_mailboxes():
    return mailbox_manager.list_shared_mailboxes(g.token_data['email'])

@app.route('/get_emails', methods=['GET'])
def get_emails():
    if g.access_token is None:
        return Response("X-Outlook-Token is required.", status=400, mimetype='text/plain')
    req = dict(request.args)
    if 'items_per_page' not in req:
        req['items_per_page'] = req.pop('count', 10)
    if 'page_number' not in req:
        req['page_number'] = 1
    req = GetEmailRequest(items_per_page=int(req['items_per_page']), page_number=int(req['page_number']), mailbox=req['mailbox'])
    if not mailbox_manager.validate_mailbox(g.token_data['email'], req.mailbox):
        return Response("User " + g.token_data['email'] + " is not authorized to access " + req.mailbox + ".", status=401, mimetype='text/plain')
    return list_email_metadata(req, g.token_data['email'], g.access_token, c)

@app.route('/describe_email', methods=['GET'])
def get_email_description():
    if g.access_token is None:
        return Response("X-Outlook-Token is required.", status=400, mimetype='text/plain')
    req = request.args
    req = DescribeEmailRequest.from_dict(req)
    return describe_email(req, g.access_token, c)

@app.route('/upload_email', methods=['POST'])
def upload_email():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    if g.access_token is None:
        return Response("X-Outlook-Token is required.", status=400, mimetype='text/plain')
    req = request.json
    schedule = RecordSchedule.from_dict(req['metadata']['record_schedule'])
    req['metadata']['record_schedule'] = schedule
    metadata = ECMSMetadata.from_dict(req['metadata'])
    req['metadata'] = metadata
    req = UploadEmailRequest.from_dict(req)
    # TODO: Improve custodian validation based on role
    if metadata.custodian != user_info.lan_id:
        return Response('User ' + user_info.lan_id + ' is not authorized to list ' + req.metadata.custodian + ' as custodian.', status=400, mimetype='text/plain')
    return upload_documentum_email(req, g.access_token, user_info, c)

@app.route('/download_email', methods=['GET'])
def download_email():
    if g.access_token is None:
        return Response("X-Outlook-Token is required.", status=400, mimetype='text/plain')
    req = request.args
    try:
        req = DownloadEmailRequest.from_dict(req)
    except:
        Response("Unable to parse request.", status=400, mimetype='text/plain')
    content = get_eml_file(req.email_id, req.file_name, g.access_token, c)
    if content is None:
        Response("File download failed. Ensure that email_id is valid.", status=500, mimetype='text/plain')
    return send_file(BytesIO(content), attachment_filename=req.file_name, as_attachment=True)

@app.route('/mark_email_saved', methods=['POST'])
def mark_email_saved():
    if g.access_token is None:
        return Response("X-Outlook-Token is required.", status=400, mimetype='text/plain')
    req = request.json
    req = MarkSavedRequest.from_dict(req)
    return mark_saved(req, g.access_token, c)

@app.route('/untag_email', methods=['POST'])
def untag_email():
    if g.access_token is None:
        return Response("X-Outlook-Token is required.", status=400, mimetype='text/plain')
    req = request.json
    req = UntagRequest.from_dict(req)
    return untag(req, g.access_token, c)

@app.route('/get_favorites', methods=['GET'])
def get_favorites():
    success, message, user_info = get_user_info(c, g.token_data)
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
    req = request.json
    try:
        req = AddFavoritesRequest.from_dict(req)
    except:
        Response("Unable to parse request.", status=400, mimetype='text/plain')
    success, message, user_info = get_user_info(c, g.token_data)
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
            if fav.function_number == sched.function_number and fav.schedule_number == sched.schedule_number and fav.disposition_number == sched.disposition_number:
                add_sched = False
                break
        if add_sched:
            add_any_sched = True
            user.favorites.append(Favorite(function_number=sched.function_number, schedule_number=sched.schedule_number, disposition_number=sched.disposition_number, user=user))
    if add_any_sched:
        try:
            db.session.commit()
            safe_user_activity_request(user_info.employee_number, user_info.lan_id, user_info.parent_org_code, '1', c)
            return Response(StatusResponse(status="OK", reason="Favorites were added.").to_json(), status=200, mimetype="application/json")
        except:
            return Response("Error committing updates.", status=500, mimetype="text/plain")
    else:
        return Response(StatusResponse(status="OK", reason="All favorites given were already in the database.").to_json(), status=200, mimetype="text/plain")

@app.route('/remove_favorites', methods=['POST'])
def remove_favorites():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    req = request.json
    req = RemoveFavoritesRequest.from_dict(req)
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        user = User(lan_id = user_info.lan_id)
    else:
        user = user[0]

    for fav in user.favorites:
        for sched in req.record_schedules:
            if fav.function_number == sched.function_number and fav.schedule_number == sched.schedule_number and fav.disposition_number == sched.disposition_number:
                db.session.delete(fav)
    db.session.commit()
    return Response(StatusResponse(status="OK", reason="Favorites were removed.").to_json(), status=200, mimetype="application/json")

@app.route('/get_record_schedules', methods=['GET'])
def get_record_schedules():
    try:
        schedules = schedule_cache.get_schedules()
        return Response(schedules.to_json(), status=200, mimetype='application/json')
    except:
        # TODO: Improve error logging
        return Response("Record schedules unable to be found.", status=500, mimetype='text/plain')

@app.route('/my_records', methods=['GET'])
def my_records():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    req = request.args
    req = MyRecordsRequest.from_dict(req)
    if user_info.lan_id != req.lan_id:
        return Response('User ' + user_info.lan_id + ' is not authorized to download records for ' + req.lan_id + '.', status=401, mimetype='text/plain')
    return get_documentum_records(c, user_info.lan_id, int(req.items_per_page), int(req.page_number), req.query, req.documentum_env)

@app.route('/get_user_info', methods=['GET'])
def user_info():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    return Response(user_info.to_json(), status=200, mimetype='application/json')

@app.route('/my_records_download', methods=['GET'])
def my_records_download():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    req = dict(request.args)
    if 'object_ids' not in req:
        return Response("object_ids field is required", status=400, mimetype='text/plain')
    req['object_ids'] = req['object_ids'].split(',')
    req = RecordDownloadRequest.from_dict(req)
    if user_info.lan_id != req.lan_id:
        return Response('User ' + user_info.lan_id + ' is not authorized to download records for ' + req.lan_id + '.', status=401, mimetype='text/plain')
    return download_documentum_record(c, user_info.lan_id, req.object_ids, req.documentum_env)

@app.route('/get_sites', methods=['GET'])
def get_sites():
    req = request.args
    req = GetSitesRequest.from_dict(req)
    sites = sems_site_cache.get_sites(req.region)
    if sites is None:
        return Response('Unable to retrieve SEMS sites.', status=500, mimetype='text/plain')
    return Response(GetSitesResponse(sites).to_json(), status=200, mimetype='application/json')

@app.route('/get_special_processing', methods=['GET'])
def get_special_processing():
    req = request.args
    req = GetSpecialProcessingRequest.from_dict(req)
    return get_sems_special_processing(c, req.region)

@app.route('/get_sharepoint_records', methods=['GET'])
def get_sharepoint_records():
    req = request.args
    req = GetSharepointRecordsRequest.from_dict(req)
    return list_sharepoint_records(req, g.access_token)

@app.route('/sharepoint_metadata_prediction', methods=['GET'])
def sharepoint_prediction():
    req = request.args
    req = SharepointPredictionRequest.from_dict(req)
    return sharepoint_record_prediction(req, g.access_token, c)

@app.route('/upload_sharepoint_record', methods=['POST'])
def sharepoint_upload():
    req = request.json
    req = SharepointUploadRequest.from_dict(req)
    success, message, user_info = get_user_info(c, g.token_data)
    if req.metadata.custodian != user_info.lan_id:
        return Response('User ' + user_info.lan_id + ' is not authorized to list ' + req.metadata.custodian + ' as custodian.', status=400, mimetype='text/plain')
    if not success:
        return Response(message, status=400, mimetype='text/plain')
    return upload_sharepoint_record(req, g.access_token, user_info, c)

@app.route('/get_help_item', methods=['GET'])
def get_help_by_id():
    req = request.args
    req = GetHelpItemRequest.from_dict(req)
    return get_help_item(req, c)

@app.route('/get_all_help_items', methods=['GET'])
def get_all_help():
    return get_all_help_items()

@app.route('/submit_sems_email', methods=['POST'])
def submit_email_sems():
    req = request.json
    req = SEMSEmailUploadRequest.from_dict(req)
    return submit_sems_email(req, c)

@app.route('/log_activity', methods=['POST'])
def log_activity():
    req = request.json
    req = LogActivityRequest.from_dict(req)
    return log_user_activity(req, c)
