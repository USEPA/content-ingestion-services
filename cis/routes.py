from flask import request, Response, send_file, g
from flask import current_app as app
from .cis_requests import *
from .data_classes import * 
from io import BytesIO
from .models import User, Favorite, AppSettings, DelegationRequest, DelegationRequestStatus, DelegationRule, db
import uuid
from . import key_cache, c, model, mailbox_manager, schedule_cache, keyword_extractor, identifier_extractor, capstone_detector
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta

@app.before_request
def log_request_info():
    if 'favicon' not in request.path and 'swagger' not in request.path and request.path != '/' and 'disposition_calc' not in request.path:
        valid, message, token_data = key_cache.validate_request(request, c)
        if not valid:
            return Response(StatusResponse(status='Authentication Token Validation Failed', reason=message, request_id=None).to_json(), status=401, mimetype='application/json')
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

@app.errorhandler(500)
def internal_service_error(_):
    return Response(StatusResponse(status='Internal Error', reason="Unknown error, contact ARMS team for assistance.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

@app.route('/file_metadata_prediction', methods=['POST'])
def file_metadata_prediction():
    file = request.files.get('file')
    prediction_metadata = request.form.get('prediction_metadata')
    try:
        prediction_metadata = PredictionMetadata.from_json(prediction_metadata)
    except:
        return Response(StatusResponse(status='Failed', reason='Prediction metadata not formatted correctly.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if file:
        return get_file_metadata_prediction(c, file, prediction_metadata)
    else:
        return Response(StatusResponse(status='Failed', reason="No file found.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')

@app.route('/text_metadata_prediction', methods=['POST'])
def text_metadata_prediction():  
    req = request.json
    try:
        req = TextPredictionRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason='Request not formatted correctly.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    keyword_weights = keyword_extractor.extract_keywords(req.text)
    keywords = [x[0] for x in sorted(keyword_weights.items(), key=lambda y: y[1], reverse=True)][:5]
    subjects=keyword_extractor.extract_subjects(req.text, keyword_weights)
    has_capstone=capstone_detector.detect_capstone_text(req.text)
    identifiers=identifier_extractor.extract_identifiers(req.text)
    spatial_extent, temporal_extent = identifier_extractor.extract_spatial_temporal(req.text)
    predicted_schedules, default_schedule = model.predict(req.text, 'document', req.prediction_metadata, has_capstone, keywords, subjects, attachments=[])
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule, subjects=subjects, identifiers=identifiers, spatial_extent=spatial_extent, temporal_extent=temporal_extent)
    return Response(prediction.to_json(), status=200, mimetype='application/json')

@app.route('/email_metadata_prediction/<emailsource>', methods=['GET'])
def email_metadata_prediction_graph(emailsource):
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason='X-Access-Token is required.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.args
    try:
        req = EmailPredictionRequestGraph.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason='Missing required parameters.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    eml_file = get_eml_file(req.email_id, emailsource, req.mailbox, g.access_token)
    if eml_file is None:
        return Response(StatusResponse(status='Failed', reason="Could not retrieve eml file.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    if 'Content-Type: application/pkcs7-mime' in str(eml_file):
        is_encrypted = True
    else:
        is_encrypted = False
    if is_encrypted:
        prediction = MetadataPrediction(predicted_schedules=[], title=mock_prediction_with_explanation, is_encrypted=True, description=mock_prediction_with_explanation, default_schedule=None, subjects=[], identifiers={}, cui_categories=[])
        return Response(prediction.to_json(), status=200, mimetype='application/json')
    ## Get email text
    email_text = get_email_text(req.email_id, emailsource, req.mailbox, g.access_token)
    if email_text is None:
        return Response(StatusResponse(status='Failed', reason="Could not retrieve email text.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    schedules = schedule_cache.get_schedules().schedules
    valid_schedules = list(filter(lambda x: x.ten_year, schedules))
    valid_schedules = ["{fn}-{sn}-{dn}".format(fn=x.function_number, sn=x.schedule_number, dn=x.disposition_number) for x in valid_schedules]
    keyword_weights = keyword_extractor.extract_keywords(email_text)
    keywords = [x[0] for x in sorted(keyword_weights.items(), key=lambda y: y[1], reverse=True)][:5]
    subjects=keyword_extractor.extract_subjects(email_text, keyword_weights)
    has_capstone=capstone_detector.detect_capstone_text(email_text)
    identifiers=identifier_extractor.extract_identifiers(email_text)
    spatial_extent, temporal_extent = identifier_extractor.extract_spatial_temporal(email_text)
    
    # TODO: Handle case where attachments are present
    predicted_schedules, default_schedule = model.predict(email_text, 'email', PredictionMetadata(req.file_name, req.department), has_capstone, keywords, subjects, attachments=[], valid_schedules=valid_schedules)
    
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule, subjects=subjects, identifiers=identifiers, is_encrypted=is_encrypted, spatial_extent=spatial_extent, temporal_extent=temporal_extent)
    return Response(prediction.to_json(), status=200, mimetype='application/json')

@app.route('/upload_file/v3', methods=['POST'])
def upload_file_v3():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    file = request.files.get('file')
    try:
        metadata = ECMSMetadataV2.from_json(request.form['metadata'])
    except:
        return Response(StatusResponse(status='Failed', reason="Metadata is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    try:
        user_activity = SubmissionAnalyticsMetadata.from_json(request.form['user_activity'])
    except:
        return Response(StatusResponse(status='Failed', reason="User activity data is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    # Default to dev environment
    env = request.form.get('nuxeo_env', 'dev')
    if metadata.custodian != user_info.lan_id and metadata.custodian != user_info.employee_number:
        success, response = validate_custodian(metadata, user_info)
        if not success:
            return response
        if user_info.employee_number not in metadata.epa_contacts:
            metadata.epa_contacts.append(user_info.employee_number)
    if file is None:
        return Response(StatusResponse(status='Failed', reason="No file found.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype="application/json")
    # This is where we need to upload record to ARMS
    file.stream.seek(0)
    data = file.read()
    success, error, uid = submit_nuxeo_file_v2(c, data, user_info, metadata, env)
    if not success:
        return Response(StatusResponse(status='Failed', reason=error, request_id=g.get('request_id', None)).to_json(), status=500, mimetype="application/json")

    # Add submission analytics
    success, response = add_submission_analytics(user_activity, metadata.record_schedule, user_info.lan_id, None, uid)
    if not success:
        return response
    else:
        log_upload_activity_v2(user_info, user_activity, metadata, c)
        upload_resp = UploadResponse(record_id=metadata.record_id, uid=uid)
        return Response(upload_resp.to_json(), status=200, mimetype='application/json')

@app.route('/my_records_download/v2', methods=['GET'])
def download_v2():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    req = dict(request.args)
    try:
        req = RecordDownloadRequestV2.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return download_nuxeo_record(c, user_info, req)

@app.route('/get_mailboxes', methods=['GET'])
def get_mailboxes():
    return mailbox_manager.list_shared_mailboxes(g.token_data['email'])

@app.route('/get_emails/<emailsource>', methods=['GET'])
def get_emails_graph(emailsource):
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = dict(request.args)
    if 'items_per_page' not in req:
        req['items_per_page'] = req.pop('count', 10)
    if 'page_number' not in req:
        req['page_number'] = 1
    if 'mailbox' not in req:
        req['mailbox'] = g.token_data['email']
    req = GetEmailRequest(items_per_page=int(req['items_per_page']), page_number=int(req['page_number']), mailbox=req['mailbox'], emailsource=emailsource)
    return list_email_metadata_graph(req, g.access_token)

@app.route('/upload_email/v3/<emailsource>', methods=['POST'])
def upload_email_v3(emailsource):
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.json
    try:
        req = UploadEmailRequestV3.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    # TODO: Improve custodian validation based on role
    if req.metadata.custodian != user_info.lan_id and req.metadata.custodian != user_info.employee_number:
        success, response = validate_custodian(req.metadata, user_info)
        if not success:
            return response
        if user_info.employee_number not in req.metadata.epa_contacts:
            req.metadata.epa_contacts.append(user_info.employee_number)
    return upload_nuxeo_email_v2(c, req, emailsource, user_info)

@app.route('/upload_sems_email/<emailsource>', methods=['POST'])
def upload_sems_email_(emailsource):
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.json
    try:
        req = UploadSEMSEmail.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')

    return upload_sems_email(c, req, emailsource, user_info)

#mark and untag email
@app.route('/mark_email_saved/<emailsource>', methods=['POST'])
def mark_email_saved_graph(emailsource):
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.json
    try:
        req = MarkSavedRequestGraph.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return mark_saved(req, g.access_token, emailsource)

@app.route('/disposition_calc', methods=['GET'])
def disposition_calc():
    req = dict(request.args)
    if 'close_date' not in req:
        return Response(StatusResponse(status='Failed', reason="No close_date.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype="application/json")
    if 'record_schedule' not in req:
        return Response(StatusResponse(status='Failed', reason="No record_schedule.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype="application/json")
    req = GetCloseDate(close_date=req['close_date'],record_schedule=req['record_schedule'])
    return get_disposition_date(req)

@app.route('/badge_info', methods=['GET'])
def badge_info():
    return get_badge_info(c)

@app.route('/gamification_data', methods=['GET'])
def gamification_data():
    req = request.args
    try:
        req = GamificationDataRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return get_gamification_data(c, req.employee_number)

@app.route('/overall_leaderboard', methods=['GET'])
def overall_leaderboard():
    return get_overall_leaderboard(c)

@app.route('/office_leaderboard', methods=['GET'])
def office_leaderboard():
    req = request.args
    try:
        req = OfficeLeaderBoardRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return get_office_leaderboard(c, req.parent_org_code)

@app.route('/get_favorites', methods=['GET'])
def get_favorites():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
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
        Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
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
            return Response(StatusResponse(status="OK", reason="Favorites were added.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")
        except:
            return Response(StatusResponse(status='Failed', reason="Error committing updates.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype="application/json")
    else:
        return Response(StatusResponse(status="OK", reason="All favorites given were already in the database.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")

@app.route('/remove_favorites', methods=['POST'])
def remove_favorites():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    req = request.json
    try:
        req = RemoveFavoritesRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
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
    return Response(StatusResponse(status="OK", reason="Favorites were removed.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")

@app.route('/get_record_schedules', methods=['GET'])
def get_record_schedules():
    try:
        schedules = schedule_cache.get_schedules()
        return Response(schedules.to_json(), status=200, mimetype='application/json')
    except:
        return Response(StatusResponse(status='Failed', reason="Record schedules unable to be found.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

@app.route('/my_records/v2', methods=['GET'])
def my_records_v2():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    req = dict(request.args)
    try:
        req = MyRecordsRequestV2.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if req.nuxeo_env not in ['dev', 'prod']:
        return Response(StatusResponse(status='Failed', reason='Invalid nuxeo_env.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return get_nuxeo_records(c, req, user_info.employee_number)

@app.route('/get_user_info', methods=['GET'])
def user_info():
    success, message, user_info = get_user_info(c, g.token_data, g.access_token)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        user = User(lan_id = user_info.lan_id)
        db.session.add(user)
        try:
            db.session.commit()
        except:
            return Response(StatusResponse(status='Failed', reason="Error creating new user.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype="application/json")
    return Response(user_info.to_json(), status=200, mimetype='application/json')

@app.route('/get_sites', methods=['GET'])
def get_sites():
    req = dict(request.args)
    if 'region_id' not in req:
        return Response(StatusResponse(status='Failed', reason="region_id field is required", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req['region_id'] = req['region_id'].split(',')
    if 'program_type' in req:
        req['program_type'] = req['program_type'].split(',')
    try:
        req = SemsSiteRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return get_sems_sites(req, c)

@app.route('/get_special_processing', methods=['GET'])
def get_special_processing():
    req = request.args
    try:
        req = GetSpecialProcessingRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return get_sems_special_processing(c, req.region)

@app.route('/get_sharepoint_records', methods=['GET'])
def get_sharepoint_records():
    req = request.args
    try:
        req = GetSharepointRecordsRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return list_sharepoint_records(req, g.access_token)

@app.route('/sharepoint_metadata_prediction', methods=['GET'])
def sharepoint_prediction():
    req = request.args
    try:
        req = SharepointPredictionRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return sharepoint_record_prediction(req, g.access_token, c)

@app.route('/upload_sharepoint_record/v3', methods=['POST'])
def sharepoint_upload_v3():
    req = request.json
    try:
        req = SharepointUploadRequestV3.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if req.metadata.custodian != user_info.lan_id and req.metadata.custodian != user_info.employee_number:
        success, response = validate_custodian(req.metadata, user_info)
        if not success:
            return response
        if user_info.employee_number not in req.metadata.epa_contacts:
            req.metadata.epa_contacts.append(user_info.employee_number)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    return upload_sharepoint_record_v3(req, g.access_token, user_info, c)      

@app.route('/upload_batch', methods=['POST'])
def upload_batch():
    req = request.json
    try:
        req = BatchUploadRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    if req.metadata.custodian != user_info.lan_id and req.metadata.custodian != user_info.employee_number:
        success, response = validate_custodian(req.metadata, user_info)
        if not success:
            return response
        if user_info.employee_number not in req.metadata.epa_contacts:
            req.metadata.epa_contacts.append(user_info.employee_number)
    return create_batch(req, user_info)

def format_batch(batch: BatchUpload):
    completion_date = batch.completion_date
    if completion_date is not None:
        completion_date = completion_date.strftime('%Y-%m-%d')
    return BatchUploadData(id=batch.id, status=batch.status.name, source=batch.source.name, email=batch.email, upload_metadata=batch.upload_metadata, user_id=batch.user_id, mailbox=batch.mailbox, completion_date=completion_date)

@app.route('/get_batch_uploads', methods=['GET'])
def get_batch_uploads():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) > 0:
        user = user[0]
    else:
        return Response(StatusResponse(status='Failed', reason="Could not find user.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    batches = BatchUpload.query.filter_by(user_id=user.id).all()
    response = BatchUploadResponse(batches=[format_batch(b) for b in batches])
    return Response(response.to_json(), status=200, mimetype='application/json')

@app.route('/get_help_item', methods=['GET'])
def get_help_by_id():
    req = request.args
    try:
        req = GetHelpItemRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return get_help_item(req)

@app.route('/update_help_items', methods=['GET'])
def update_help():
    return update_help_items()

@app.route('/get_all_help_items', methods=['GET'])
def get_all_help():
    req = request.args
    if req.get('override', False):
        return Response(StatusResponse(status='Failed', reason="Request returned 500 for testing purposes.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    return get_all_help_items()

@app.route('/extract_keywords', methods=['POST'])
def extract():
    req = request.json
    try:
        req = KeywordExtractionRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    keyword_weights = keyword_extractor.extract_keywords(req.text)
    response = KeywordExtractionResponse(
        keywords = list(keyword_weights.keys()),
        subjects=keyword_extractor.extract_subjects(req.text, keyword_weights),
        identifiers=identifier_extractor.extract_identifiers(req.text)
    )
    return Response(response.to_json(), status=200, mimetype='application/json')

@app.route('/log_activity', methods=['POST'])
def log_activity():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    req = request.json
    try:
        req = LogActivityRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    # Validate request
    if req.lan_id != user_info.lan_id:
        return Response(StatusResponse(status='Failed', reason="User is not authorized to submit activity for the specified lan_id.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if req.employee_id != user_info.employee_number:
        return Response(StatusResponse(status='Failed', reason="User is not authorized to submit activity for the specified employee_id.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if req.event_id not in ['1','2','3','4','5','6','7']:
        return Response(StatusResponse(status='Failed', reason="Invalid event_id.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if req.office_code not in [user_info.parent_org_code, user_info.manager_parent_org_code]:
        return Response(StatusResponse(status='Failed', reason="Invalid office_code.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json') 
    return log_user_activity(req, c)

@app.route('/update_preferred_system', methods=['POST'])
def update_preferred_system():
    req = request.json
    try:
        req = UpdatePreferredSystemRequest.from_dict(req)
    except:
        Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        user = User(lan_id = user_info.lan_id)
        db.session.add(user)
    else:
        user = user[0]
    settings = user.user_settings
    if len(settings) == 0:
        user.user_settings.append(AppSettings(system=req.preferred_system, default_edit_mode='basic'))
    else:
        current_settings = settings[0]
        user.user_settings = [AppSettings(system=req.preferred_system, default_edit_mode=current_settings.default_edit_mode)]
    try:
        db.session.commit()
        return Response(StatusResponse(status="OK", reason="Preferred system updated.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")
    except:
        return Response(StatusResponse(status='Failed', reason="Error committing updates.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype="application/json")

@app.route('/update_default_edit_mode', methods=['POST'])
def update_default_edit_mode():
    req = request.json
    try:
        req = UpdateEditModeRequest.from_dict(req)
    except:
        Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        user = User(lan_id = user_info.lan_id)
        db.session.add(user)
    else:
        user = user[0]
    settings = user.user_settings
    if len(settings) == 0:
        user.user_settings.append(AppSettings(system='ARMS', default_edit_mode=req.default_edit_mode))
    else:
        current_settings = settings[0]
        user.user_settings = [AppSettings(system=current_settings.system, default_edit_mode=req.default_edit_mode)]
    try:
        db.session.commit()
        return Response(StatusResponse(status="OK", reason="Default edit mode updated.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")
    except:
        return Response(StatusResponse(status='Failed', reason="Error committing updates.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype="application/json")

@app.route('/add_parent_child_relationship', methods=['POST'])
def add_parent_child_relationship():
    req = request.json
    try:
        req = AddParentChildRequest.from_dict(req)
    except:
        Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    return add_relationship(req, user_info, c, req.nuxeo_env)

@app.route('/search_users', methods=['GET'])
def search_users():
    req = request.args
    try:
        req = SearchUsersRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return get_users(req, c)

@app.route('/create_delegation_request', methods=['POST'])
def create_delegation_request():
    req = request.json
    try:
        req = CreateDelegationRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    target_display_name = get_display_name_by_employee_number(c, req.target_employee_number)
    if target_display_name is None:
        return Response(StatusResponse(status='Failed', reason="Could not find target in WAM.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        user = User(lan_id = user_info.lan_id)
        db.session.add(user)
        db.session.flush()
        db.session.refresh(user)
    else:
        user = user[0]
    request_uuid = str(uuid.uuid4())
    delegation_request = DelegationRequest(uuid=request_uuid, 
                                           requesting_user_id=user.id,
                                           requesting_user_employee_number=user_info.employee_number, 
                                           requesting_user_display_name=user_info.display_name, 
                                           target_user_employee_number=req.target_employee_number, 
                                           target_user_display_name=target_display_name,
                                           date_sent=datetime.now())
    db.session.add(delegation_request)
    db.session.commit()
    return Response(StatusResponse(status="OK", reason="Delegation request created.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")

def process_delegation_request(req: DelegationRequest):
    status_date = None
    if req.status_date is not None:
        status_date=req.status_date.strftime('%Y-%m-%d')
    return DelegationRequestData(request_id=req.uuid, 
                                 requesting_user_employee_number=req.requesting_user_employee_number, 
                                 requesting_user_display_name=req.requesting_user_display_name, 
                                 target_user_employee_number=req.target_user_employee_number,
                                 target_user_display_name=req.target_user_display_name,
                                 date_sent=req.date_sent.strftime('%Y-%m-%d'),
                                 request_status=req.status.name,
                                 status_date=status_date,
                                 expiration_email_sent=req.expiration_email_sent
                                 )

@app.route('/get_delegation_requests', methods=['GET'])
def get_delegation_requests():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        return Response(StatusResponse(status='Failed', reason="User not found.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    else:
        user = user[0]
    delegation_requests = [process_delegation_request(x) for x in user.delegation_requests]
    incoming_requests = [process_delegation_request(x) for x in DelegationRequest.query.filter_by(target_user_employee_number=user_info.employee_number).all()]
    response = ListDelegationRequestResponse(delegation_requests=delegation_requests, incoming_requests=incoming_requests)
    return Response(response.to_json(), status=200, mimetype='application/json')

@app.route('/delegation_response', methods=['POST'])
def delegation_response():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    req = request.json
    try:
        req = DelegationResponse.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason='Missing required parameters.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    delegation_request = DelegationRequest.query.filter_by(uuid=req.request_id, target_user_employee_number=user_info.employee_number, status=DelegationRequestStatus.PENDING).first_or_404()
    if datetime.now() > delegation_request.date_sent + relativedelta(days=30):
        delegation_request.status = DelegationRequestStatus.EXPIRED
        delegation_request.status_date = datetime.now()
        try:
            db.session.commit()
            return Response(StatusResponse(status="EXPIRED", reason="Delegation request is over 30 days old. Please submit a new request.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype="application/json")
        except:
            return Response(StatusResponse(status='Failed', reason="Failed to update database.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    if req.is_accepted:
        delegation_request.status = DelegationRequestStatus.ACCEPTED
        delegation_request.status_date = datetime.now()
        rule = DelegationRule(submitting_user_id=delegation_request.requesting_user_id, 
                              submitting_user_display_name=delegation_request.requesting_user_display_name,
                              submitting_user_employee_number=delegation_request.requesting_user_employee_number, 
                              target_user_display_name=delegation_request.target_user_display_name, 
                              target_user_employee_number=delegation_request.target_user_employee_number, 
                              delegation_request_id=delegation_request.id)
        db.session.add(rule)
    else:
        delegation_request.status = DelegationRequestStatus.REJECTED
        delegation_request.status_date = datetime.now()
    try:
        db.session.commit()
        return Response(StatusResponse(status="OK", reason="Delegation request updated.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")
    except:
        return Response(StatusResponse(status='Failed', reason="Failed to update database.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')

def process_rule(rule):
    return DelegationRuleData(rule_id=rule.id, submitting_user_employee_number=rule.submitting_user_employee_number, submitting_user_display_name=rule.submitting_user_display_name, target_user_employee_number=rule.target_user_employee_number, target_user_display_name=rule.target_user_display_name)

@app.route('/get_delegation_rules', methods=['GET'])
def get_delegation_rules():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    user = User.query.filter_by(lan_id = user_info.lan_id).all()
    if len(user) == 0:
        return Response(StatusResponse(status='Failed', reason="User not found.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    else:
        user = user[0]
    submitting_rules = [process_rule(x) for x in user.delegation_rules]
    target_rules = DelegationRule.query.filter_by(target_user_employee_number=user_info.employee_number).all()
    target_rules = [process_rule(x) for x in target_rules]
    response = DelegationRuleResponse(submitting_rules=submitting_rules, target_rules=target_rules)
    return Response(response.to_json(), status=200, mimetype='application/json')

@app.route('/delete_delegation_rule', methods=['POST'])
def delete_delegation_rule():
    req = request.json
    try:
        req = DeleteDelegationRuleRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    rule = DelegationRule.query.filter_by(id=req.rule_id).first_or_404()
    if rule.submitting_user_employee_number != user_info.employee_number and rule.target_user_employee_number != user_info.employee_number:
        return Response(StatusResponse(status='Failed', reason="User is not authorized to remove this rule.", request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    db.session.delete(rule)
    db.session.commit()
    return Response(StatusResponse(status="OK", reason="Delegation rule removed.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")