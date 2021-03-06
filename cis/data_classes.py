from dataclasses import dataclass
from dataclasses_json import dataclass_json
from typing import Optional


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
class RecordScheduleInformation:
    function_number: str 
    schedule_number: str 
    disposition_number: str 
    display_name: str
    schedule_title: str 
    disposition_title: str 
    disposition_instructions: str 
    cutoff_instructions: str
    function_title: str
    program: str 
    applicability: str
    nara_disposal_authority_item_level: str
    nara_disposal_authority_schedule_level: str
    final_disposition: str 
    disposition_summary: str
    description: str
    guidance: str
    keywords: str

@dataclass_json
@dataclass 
class RecordScheduleList:
    schedules: list[RecordScheduleInformation]

@dataclass_json
@dataclass 
class DocumentumDocInfo:
    title: str
    doc_type: str
    date: str
    sensitivity: str
    doc_id: str
    object_ids: list[str]
    size: float
    custodian: str

@dataclass_json
@dataclass 
class DocumentumRecordList:
    records: list[DocumentumDocInfo]
    total: int
    
@dataclass_json
@dataclass 
class MyRecordsRequest:
    lan_id: str
    items_per_page: int
    page_number: int
    query: Optional[str] = None

@dataclass_json
@dataclass 
class RecordDownloadRequest:
    lan_id: str
    object_ids: list[str]

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
    file_path: str
    custodian: str
    title: str
    description: Optional[str]
    record_schedule: RecordSchedule 
    creator: Optional[str] 
    creation_date: Optional[str]
    close_date: Optional[str]
    sensitivity: str 
    rights: Optional[list[str]]
    coverage: Optional[list[str]]
    relationships: Optional[list[str]]
    tags: Optional[list[str]]

# Dates must be formatted as %Y-%m-%dT%H:%M:%S
@dataclass_json
@dataclass
class DocumentumMetadata:
    r_object_type: str
    object_name: str
    a_application_type: str
    erma_content_title: str
    erma_content_unid: str
    erma_content_date: str
    erma_content_schedule: str
    erma_content_eventdate: str
    erma_sensitivity_id: str
    erma_custodian: str
    erma_folder_path: str
    erma_content_description: Optional[str]
    erma_content_creator: Optional[str]
    erma_content_creation_date: Optional[str]
    erma_content_close_date: Optional[str]
    erma_content_rights: Optional[list[str]]
    erma_content_coverage: Optional[list[str]]
    erma_content_relation: Optional[list[str]]
    erma_content_tags: Optional[list[str]]



@dataclass_json
@dataclass 
class AddFavoritesRequest:
    record_schedules: list[RecordSchedule]

@dataclass_json
@dataclass 
class RemoveFavoritesRequest:
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
class EmailAttachment:
    name: str
    attachment_id: str

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
    attachments: list[EmailAttachment]
    mailbox_source: str

@dataclass_json
@dataclass 
class SemsSite:
    _id: str
    region: str
    epaid: str
    sitename: str

@dataclass_json
@dataclass 
class GetSitesResponse:
    sites: list[SemsSite]

@dataclass_json
@dataclass 
class SemsSpecialProcessing:
    description: str
    code: str

@dataclass_json
@dataclass 
class GetSpecialProcessingResponse:
    special_processing: list[SemsSpecialProcessing]

@dataclass_json
@dataclass 
class UserInfo:
    email: str
    display_name: str
    lan_id: str
    department: str

mock_email_metadata = EmailMetadata(**{
    'unid': '<DM6PR09MB549690B3AC3ED29A07A4B0B0B78D9@DM6PR09MB5496.namprd09.prod.outlook.com>',
    'subject': 'Test Subject',
    'email_id': 'AAMkADc3MTVlN2YwLWI4ZTMtNDZkMS04OGI2LTk3MzBkMmQxMDNhMwBGAAAAAABq49v7gFnsRqMkXEzRx+O2BwD/n/+gsFwRQaN01L30xNjJAAAAAAENAAD/n/+gsFwRQaN01L30xNjJAAZdx/btAAA=',
    'received': 'Wed Feb 10 17:13:32 UTC 2021',
    '_from': 'ECMS3 Test <ECMS3Test@testusepa.onmicrosoft.com>',
    'to': 'ECMS3Test@testusepa.onmicrosoft.com',
    'sent': 'Wed Feb 10 17:13:31 UTC 2021',
    'attachments': [],
    'mailbox_source': 'regular'
    })

@dataclass_json
@dataclass 
class DownloadAttachmentRequest:
    file_name: str
    attachment_id: str

@dataclass_json
@dataclass 
class GetEmailResponse:
    total_count: int 
    page_number: int
    items_per_page: int
    emails: list[EmailMetadata]

mock_get_email_response = GetEmailResponse(total_count=2, page_number=1, items_per_page=10, emails=[mock_email_metadata, mock_email_metadata])

@dataclass_json
@dataclass 
class GetSitesRequest:
    region: str

@dataclass_json
@dataclass 
class GetSpecialProcessingRequest:
    region: str

@dataclass_json
@dataclass 
class GetEmailRequest:
    items_per_page: int 
    page_number: int
    mailbox: str

@dataclass_json
@dataclass 
class GetEmailBodyRequest:
    email_id: int 

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
    email_unid: str
    documentum_env: str

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
class RecordCountResponse:
    count: int

@dataclass_json
@dataclass 
class GetFavoritesResponse:
    favorites: list[RecordSchedule]

mock_get_favorites_response = GetFavoritesResponse(favorites = mock_schedules)