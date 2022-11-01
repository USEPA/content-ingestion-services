from flask import request, Response, send_file, g
from flask import current_app as app
from .cis_requests import *
from .data_classes import * 
from io import BytesIO
from .models import User, Favorite, AppSettings, db
import uuid
from . import key_cache, c, model, mailbox_manager, schedule_cache, keyword_extractor, identifier_extractor, capstone_detector
import json

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
    if prediction_metadata != None:
        try:
            prediction_metadata = PredictionMetadata.from_json(prediction_metadata)
        except:
            return Response(StatusResponse(status='Failed', reason='Prediction metadata not formatted correctly.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if file:
        file_obj = file.read()
        success, text, response = tika(file_obj, c)
        if not success:
            return response
        keyword_weights = keyword_extractor.extract_keywords(text)
        keywords = [x[0] for x in sorted(keyword_weights.items(), key=lambda y: y[1], reverse=True)][:5]
        subjects=keyword_extractor.extract_subjects(text, keyword_weights)
        has_capstone=capstone_detector.detect_capstone_text(text)
        identifiers=identifier_extractor.extract_identifiers(text)
        # TODO: Handle case where attachments are present
        predicted_schedules, default_schedule = model.predict(text, 'document', prediction_metadata, has_capstone, keywords, subjects, attachments=[])
        predicted_title = mock_prediction_with_explanation
        predicted_description = mock_prediction_with_explanation
        if prediction_metadata.file_name.split('.')[-1] in set(['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'pdf']):
            cui_categories = get_cui_categories(file_obj, c)
        else:
            cui_categories = []
        prediction = MetadataPrediction(
            predicted_schedules=predicted_schedules, 
            title=predicted_title, 
            description=predicted_description, 
            default_schedule=default_schedule, 
            subjects=subjects, 
            identifiers=identifiers,
            cui_categories=cui_categories
            )
        return Response(prediction.to_json(), status=200, mimetype='application/json')
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
    # TODO: Handle case where attachments are present
    predicted_schedules, default_schedule = model.predict(req.text, 'document', req.prediction_metadata, has_capstone, keywords, subjects, attachments=[])
    
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule, subjects=subjects, identifiers=identifiers)
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
    eml_file = get_eml_file(req.email_id, "default_file_name", emailsource, req.mailbox, g.access_token, c)
    if eml_file is None:
        return Response(StatusResponse(status='Failed', reason="Could not retrieve eml file.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    success, text, response = tika(eml_file, c, extraction_type='text')
    if not success:
        return response
    if 'Content-Type: application/pkcs7-mime' in str(eml_file):
        is_encrypted = True
    else:
        print(text)
        is_encrypted = False
    schedules = schedule_cache.get_schedules().schedules
    valid_schedules = list(filter(lambda x: x.ten_year, schedules))
    valid_schedules = ["{fn}-{sn}-{dn}".format(fn=x.function_number, sn=x.schedule_number, dn=x.disposition_number) for x in valid_schedules]
    keyword_weights = keyword_extractor.extract_keywords(text)
    keywords = [x[0] for x in sorted(keyword_weights.items(), key=lambda y: y[1], reverse=True)][:5]
    subjects=keyword_extractor.extract_subjects(text, keyword_weights)
    has_capstone=capstone_detector.detect_capstone_text(text)
    identifiers=identifier_extractor.extract_identifiers(text)
    # TODO: Handle case where attachments are present
    predicted_schedules, default_schedule = model.predict(text, 'email', PredictionMetadata(req.file_name, req.department), has_capstone, keywords, subjects, attachments=[], valid_schedules=valid_schedules)
    
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule, subjects=subjects, identifiers=identifiers, is_encrypted=is_encrypted)
    return Response(prediction.to_json(), status=200, mimetype='application/json')

@app.route('/email_metadata_prediction/', methods=['GET'])
def email_metadata_prediction():
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason='X-Access-Token is required.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.args
    try:
        req = EmailPredictionRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason='Missing required parameters.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    eml_file = get_eml_file(req.email_id, "default_file_name", 'archive', None, g.access_token, c)
    if eml_file is None:
        return Response(StatusResponse(status='Failed', reason="Could not retrieve eml file.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    success, text, response = tika(eml_file, c, extraction_type='text')
    if not success:
        return response
    schedules = schedule_cache.get_schedules().schedules
    valid_schedules = list(filter(lambda x: x.ten_year, schedules))
    valid_schedules = ["{fn}-{sn}-{dn}".format(fn=x.function_number, sn=x.schedule_number, dn=x.disposition_number) for x in valid_schedules]
    keyword_weights = keyword_extractor.extract_keywords(text)
    keywords = [x[0] for x in sorted(keyword_weights.items(), key=lambda y: y[1], reverse=True)][:5]
    subjects=keyword_extractor.extract_subjects(text, keyword_weights)
    has_capstone=capstone_detector.detect_capstone_text(text)
    identifiers=identifier_extractor.extract_identifiers(text)
    # TODO: Handle case where attachments are present
    predicted_schedules, default_schedule = model.predict(text, 'email', PredictionMetadata(req.file_name, req.department), has_capstone, keywords, subjects, attachments=[], valid_schedules=valid_schedules)
    
    predicted_title = mock_prediction_with_explanation
    predicted_description = mock_prediction_with_explanation
    prediction = MetadataPrediction(predicted_schedules=predicted_schedules, title=predicted_title, description=predicted_description, default_schedule=default_schedule, subjects=subjects, identifiers=identifiers)
    return Response(prediction.to_json(), status=200, mimetype='application/json')

@app.route('/upload_file', methods=['POST'])
def upload_file():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    file = request.files.get('file')
    try:
        metadata = ECMSMetadata.from_json(request.form['metadata'])
    except:
        return Response(StatusResponse(status='Failed', reason="Metadata is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    try:
        user_activity = SubmissionAnalyticsMetadata.from_json(request.form['user_activity'])
    except:
        return Response(StatusResponse(status='Failed', reason="User activity data is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    # Default to dev environment
    env = request.form.get('documentum_env', 'dev')
    if metadata.custodian != user_info.lan_id:
        return Response(StatusResponse(status='Failed', reason="Custodian must match authorized user's lan_id.", request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    if file is None:
        return Response(StatusResponse(status='Failed', reason="No file found.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype="application/json")
    # This is where we need to upload record to ARMS
    
    # Add submission analytics
    # success, response = add_submission_analytics(user_activity, metadata.record_schedule, user_info.lan_id, r_object_id, None)
    # if not success:
    #     return response
    # else:
    #     log_upload_activity(user_info, user_activity, metadata, c)
    #     return Response(StatusResponse(status='OK', reason='File successfully uploaded.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')
    return Response(StatusResponse(status='OK', reason='File successfully uploaded.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')   

@app.route('/upload_file/v2', methods=['POST'])
def upload_file_v2():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    file = request.files.get('file')
    try:
        metadata = ECMSMetadata.from_json(request.form['metadata'])
    except:
        return Response(StatusResponse(status='Failed', reason="Metadata is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    try:
        user_activity = SubmissionAnalyticsMetadata.from_json(request.form['user_activity'])
    except:
        return Response(StatusResponse(status='Failed', reason="User activity data is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    # Default to dev environment
    env = request.form.get('nuxeo_env', 'dev')
    if metadata.custodian != user_info.lan_id:
        return Response(StatusResponse(status='Failed', reason="Custodian must match authorized user's lan_id.", request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    if file is None:
        return Response(StatusResponse(status='Failed', reason="No file found.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype="application/json")
    # This is where we need to upload record to ARMS
    file.stream.seek(0)
    data = file.read()
    success, error, uid = submit_nuxeo_file(c, data, user_info, metadata, env)
    if not success:
        return Response(StatusResponse(status='Failed', reason=error, request_id=g.get('request_id', None)).to_json(), status=500, mimetype="application/json")

    # Add submission analytics
    success, response = add_submission_analytics(user_activity, metadata.record_schedule, user_info.lan_id, None, uid)
    if not success:
        return response
    else:
        log_upload_activity(user_info, user_activity, metadata, c)
        return Response(StatusResponse(status='OK', reason='File successfully uploaded.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')

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

@app.route('/get_emails', methods=['GET'])
def get_emails():
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = dict(request.args)
    if 'items_per_page' not in req:
        req['items_per_page'] = req.pop('count', 10)
    if 'page_number' not in req:
        req['page_number'] = 1
    req = GetEmailRequest(items_per_page=int(req['items_per_page']), page_number=int(req['page_number']), mailbox=req['mailbox'], emailsource=None)
    if not mailbox_manager.validate_mailbox(g.token_data['email'], req.mailbox):
        return Response(StatusResponse(status='Failed', reason="User is not authorized to access selected mailbox.", request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    return list_email_metadata(req, g.token_data['email'], g.access_token, c)

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
    if not mailbox_manager.validate_mailbox(g.token_data['email'], req.mailbox):
        return Response(StatusResponse(status='Failed', reason="User is not authorized to access selected mailbox.", request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    return list_email_metadata_graph(req, g.token_data['email'], g.access_token, c)

@app.route('/upload_email', methods=['POST'])
def upload_email():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.json
    try:
        req = UploadEmailRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    # TODO: Improve custodian validation based on role
    if req.metadata.custodian != user_info.lan_id:
        return Response(StatusResponse(status='Failed', reason="Custodian must match authorized user's lan_id.", request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    return Response(StatusResponse(status='OK', reason='Email successfully uploaded.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')   

@app.route('/upload_email/v2/<emailsource>', methods=['POST'])
def upload_email_v2(emailsource):
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.json
    try:
        req = UploadEmailRequestV2.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    # TODO: Improve custodian validation based on role
    if req.metadata.custodian != user_info.lan_id:
        return Response(StatusResponse(status='Failed', reason="Custodian must match authorized user's lan_id.", request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    
    return upload_nuxeo_email(c, req, emailsource, user_info)

@app.route('/download_email', methods=['GET'])
def download_email():
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.args
    try:
        req = DownloadEmailRequest.from_dict(req)
    except:
        Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    content = get_eml_file(req.email_id, req.file_name, g.access_token, c)
    if content is None:
        Response(StatusResponse(status='Failed', reason="File download failed. Ensure that email_id is valid.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    return send_file(BytesIO(content), attachment_filename=req.file_name, as_attachment=True)

#mark and untag email
@app.route('/mark_email_saved/', methods=['POST'])
def mark_email_saved():
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.json
    try:
        req = MarkSavedRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return mark_saved(req, g.access_token, 'archive', c)

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
    return mark_saved(req, g.access_token, emailsource, c)

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

@app.route('/untag_email', methods=['POST'])
def untag_email():
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.json
    try:
        req = UntagRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return untag(req, g.access_token, c, 'archive')

@app.route('/untag_email/<emailsource>', methods=['POST'])
def untag_email_graph(emailsource):
    if g.access_token is None:
        return Response(StatusResponse(status='Failed', reason="X-Access-Token is required.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req = request.json
    try:
        req = UntagRequestGraph.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return untag(req, g.access_token, c, emailsource)

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

@app.route('/my_records', methods=['GET'])
def my_records():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    req = dict(request.args)
    if 'items_per_page' not in req:
        req['items_per_page'] = 10
    else:
        req['items_per_page'] = int(req['items_per_page'])
    if 'page_number' not in req:
        req['page_number'] = 1
    else:
        req['page_number'] = int(req['page_number'])
    try:
        req = MyRecordsRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if user_info.lan_id != req.lan_id:
        return Response(StatusResponse(status='Failed', reason='User is not authorized to download records for this lan_id.', request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    if req.documentum_env not in ['dev', 'prod']:
        return Response(StatusResponse(status='Failed', reason='Invalid documentum_env.', request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return get_documentum_records(c, user_info.lan_id, int(req.items_per_page), int(req.page_number), req.query, req.documentum_env)

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
            return Response(StatusResponse(status="OK", reason="Preferred system updated.", request_id=g.get('request_id', None)).to_json(), status=200, mimetype="application/json")
        except:
            return Response(StatusResponse(status='Failed', reason="Error committing updates.", request_id=g.get('request_id', None)).to_json(), status=500, mimetype="application/json")
    return Response(user_info.to_json(), status=200, mimetype='application/json')

@app.route('/my_records_download', methods=['GET'])
def my_records_download():
    success, message, user_info = get_user_info(c, g.token_data)
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    req = dict(request.args)
    if 'object_ids' not in req:
        return Response(StatusResponse(status='Failed', reason="object_ids field is required", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    req['object_ids'] = req['object_ids'].split(',')
    try:
        req = RecordDownloadRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if user_info.lan_id != req.lan_id:
        return Response(StatusResponse(status='Failed', reason='User is not authorized to download records for this lan_id.', request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    return download_documentum_record(c, user_info, req.object_ids, req.documentum_env)

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

@app.route('/upload_sharepoint_record', methods=['POST'])
def sharepoint_upload():
    req = request.json
    try:
        req = SharepointUploadRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if req.metadata.custodian != user_info.lan_id:
        return Response(StatusResponse(status='Failed', reason="Custodian must match authorized user's lan_id.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    return Response(StatusResponse(status='OK', reason='Sharepoint file successfully uploaded.', request_id=g.get('request_id', None)).to_json(), status=200, mimetype='application/json')   

@app.route('/upload_sharepoint_record/v2', methods=['POST'])
def sharepoint_upload_v2():
    req = request.json
    try:
        req = SharepointUploadRequestV2.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    if req.metadata.custodian != user_info.lan_id:
        return Response(StatusResponse(status='Failed', reason="Custodian must match authorized user's lan_id.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    return upload_sharepoint_record_v2(req, g.access_token, user_info, c)   

@app.route('/upload_sharepoint_batch', methods=['POST'])
def sharepoint_batch_upload():
    req = request.json
    try:
        req = SharepointBatchUploadRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    success, message, user_info = get_user_info(c, g.token_data)
    for item in req.sharepoint_items:
        if item.metadata.custodian != user_info.lan_id:
            return Response(StatusResponse(status='Failed', reason="Custodian must match authorized user's lan_id.", request_id=g.get('request_id', None)).to_json(), status=401, mimetype='application/json')
    if not success:
        return Response(StatusResponse(status='Failed', reason=message, request_id=g.get('request_id', None)).to_json(), status=500, mimetype='application/json')
    return upload_sharepoint_batch(req, user_info, c, g.access_token)

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

@app.route('/submit_sems_email', methods=['POST'])
def submit_email_sems():
    req = request.json
    try:
        req = SEMSEmailUploadRequest.from_dict(req)
    except:
        return Response(StatusResponse(status='Failed', reason="Request is not formatted correctly.", request_id=g.get('request_id', None)).to_json(), status=400, mimetype='application/json')
    return submit_sems_email(req, c)

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