from dataclasses import dataclass
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass 
class RecordSchedule:
    function_number: str 
    schedule_number: str 
    disposition_number: str 

mock_schedules = [
    RecordSchedule(**{"function_number": "404", "schedule_number": "1012", "disposition_number": "e"}), 
    RecordSchedule(**{"function_number": "404", "schedule_number": "1012", "disposition_number": "b"}),
    RecordSchedule(**{"function_number": "401", "schedule_number": "1006", "disposition_number": "b"})]

@dataclass_json
@dataclass 
class Recommendation:
    schedule: RecordSchedule 
    probability: float 

@dataclass_json
@dataclass 
class PredictionWithExplanation:
    value: str 
    prediction_type: str

mock_prediction_with_explanation = PredictionWithExplanation(value="None", prediction_type="None")

@dataclass_json
@dataclass 
class MetadataPrediction:
    predicted_schedules: list[Recommendation] 
    title: PredictionWithExplanation
    description: PredictionWithExplanation

mock_predicted_schedules = [
    Recommendation(**{"schedule": RecordSchedule(**{"function_number": "404", "schedule_number": "1012", "disposition_number": "e"}), "probability": 0.6403017640113831}), 
    Recommendation(**{"schedule": RecordSchedule(**{"function_number": "404", "schedule_number": "1012", "disposition_number": "b"}), "probability": 0.19178320467472076}), 
    Recommendation(**{"schedule": RecordSchedule(**{"function_number": "401", "schedule_number": "1006", "disposition_number": "b"}), "probability": 0.0495888851583004})]
mock_metadata_prediction = MetadataPrediction(predicted_schedules=mock_predicted_schedules, title=mock_prediction_with_explanation, description=mock_prediction_with_explanation)

@dataclass_json
@dataclass
class ECMSMetadata:
    title: str
    description: str
    record_schedule: RecordSchedule 
    creator: str 
    creation_date: str
    sensitivity: str 
    rights: str
    coverage: str 

@dataclass_json
@dataclass 
class GetFavoritesRequest:
    lan_id: str 

@dataclass_json
@dataclass 
class AddFavoritesRequest:
    lan_id: str 
    record_schedules: list[RecordSchedule]

@dataclass_json
@dataclass 
class RemoveFavoritesRequest:
    lan_id: str 
    record_schedules: list[RecordSchedule]

@dataclass_json
@dataclass 
class StatusResponse:
    status: str 
    reason: str

mock_status_response = StatusResponse("OK", "This is a mock.")

@dataclass_json
@dataclass 
class TextPredictionRequest:
    text: str

@dataclass_json
@dataclass 
class EmailPredictionRequest:
    email_id: str

@dataclass_json
@dataclass 
class GetMailboxesResponse:
    mailboxes: list[str]

mock_get_mailboxes_response = GetMailboxesResponse(["Yuen.Andrew@epa.gov", "ecms@epa.gov"])

@dataclass_json
@dataclass 
class EmailMetadata:
    unid: str
    email_id: str
    _from: str
    to: str
    subject: str
    sent: str
    received: str

mock_email_metadata = EmailMetadata(**{
    'unid': '<DM6PR09MB549690B3AC3ED29A07A4B0B0B78D9@DM6PR09MB5496.namprd09.prod.outlook.com>',
    'subject': 'Test Subject',
    'email_id': 'AAMkADc3MTVlN2YwLWI4ZTMtNDZkMS04OGI2LTk3MzBkMmQxMDNhMwBGAAAAAABq49v7gFnsRqMkXEzRx+O2BwD/n/+gsFwRQaN01L30xNjJAAAAAAENAAD/n/+gsFwRQaN01L30xNjJAAZdx/btAAA=',
    'received': 'Wed Feb 10 17:13:32 UTC 2021',
    '_from': 'ECMS3 Test <ECMS3Test@testusepa.onmicrosoft.com>',
    'to': 'ECMS3Test@testusepa.onmicrosoft.com',
    'sent': 'Wed Feb 10 17:13:31 UTC 2021'
    })

@dataclass_json
@dataclass 
class GetEmailResponse:
    total_count: int 
    emails: list[EmailMetadata]

mock_get_email_response = GetEmailResponse(total_count=2, emails=[mock_email_metadata, mock_email_metadata])

@dataclass_json
@dataclass 
class GetEmailRequest:
    count: int 
    mailbox: str

@dataclass_json
@dataclass 
class DownloadEmailRequest:
    file_name: str 
    email_id: str

@dataclass_json
@dataclass 
class DescribeEmailRequest:
    email_id: str

@dataclass_json
@dataclass 
class DescribeEmailResponse:
    email_id: str
    _from: str
    to: str
    cc: str
    subject: str
    date: str
    body: str 
    attachments: list[str]

@dataclass_json
@dataclass 
class UploadEmailRequest:
    metadata: ECMSMetadata 
    email_id: str

@dataclass_json
@dataclass 
class MarkSavedRequest:
    sensitivity: str 
    email_id: str

@dataclass_json
@dataclass 
class UntagRequest:
    email_id: str

@dataclass_json
@dataclass 
class UntagRequest:
    email_id: str

@dataclass_json
@dataclass 
class GetFavoritesResponse:
    favorites: list[RecordSchedule]

mock_get_favorites_response = GetFavoritesResponse(favorites = mock_schedules)