from context import cis
from cis import cis_requests, app_config, data_classes

# def test_object_id_validation():
#     config = app_config.config_from_file('dev_config.json')
#     assert not cis_requests.object_id_is_valid(config, '12345') 

def test_model_output(hf_model):
    text = "this is a test"
    doc_type = "Document" 
    prediction_metadata = None 
    has_capstone = False 
    keywords = [] 
    subjects = [] 
    attachments = []

    predictions, default_schedule = hf_model.predict(text=text, doc_type=doc_type, prediction_metadata=prediction_metadata, has_capstone=has_capstone, keywords=keywords, subjects=subjects, attachments=attachments)
    assert len(predictions) == 3
    assert predictions[0].schedule == data_classes.RecordSchedule(function_number='301', schedule_number='1016', disposition_number='c')
    assert abs(predictions[0].probability - 0.45385774970054626) < 0.0001
    assert predictions[1].schedule == data_classes.RecordSchedule(function_number='306', schedule_number='1023', disposition_number='c')
    assert abs(predictions[1].probability - 0.1347094178199768) < 0.0001
    assert predictions[2].schedule == data_classes.RecordSchedule(function_number='108', schedule_number='1044', disposition_number='d')
    assert abs(predictions[2].probability - 0.11839142441749573) < 0.0001
    assert default_schedule == None
