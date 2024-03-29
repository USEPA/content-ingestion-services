from dataclasses import dataclass, field
from re import S
from dataclasses_json import dataclass_json
from typing import Optional, Dict
import datetime

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
class KeywordExtractionRequest:
    text: str 

@dataclass_json
@dataclass 
class OfficeLeaderBoardRequest:
    parent_org_code: str

@dataclass_json
@dataclass 
class KeywordExtractionResponse:
    keywords: list[str]
    subjects: list[str]
    identifiers: Dict[str, str] 

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
    ten_year: bool
    reserved_flag: bool
    superseded_flag: bool
    deleted_flag: bool
    draft_flag: bool
    system_flag: bool
    calendar_year_flag: bool
    fiscal_year_flag: bool
    retention_year: int
    retention_month: int
    retention_day: int
    epa_approval: str
    nara_approval: str
    previous_nara_disposal_authority: str
    status: str
    custodians: str
    reasons_for_disposition: str
    related_schedules: str
    entry_date: str
    revised_date: str
    action: str
    keywords_title: str
    keywords_subject: str
    keywords_org: str
    related_terms: str
    dnul_flag: bool
    last_modified_flag: bool

@dataclass_json
@dataclass 
class RecordScheduleList:
    schedules: list[RecordScheduleInformation]

@dataclass_json
@dataclass 
class Recommendation:
    schedule: RecordSchedule 
    probability: float 

@dataclass_json
@dataclass
class PredictionMetadata:
    file_name: Optional[str]
    department: Optional[str]
    file_path: Optional[str] = None

@dataclass_json
@dataclass 
class PredictionWithExplanation:
    value: str 
    prediction_type: str

mock_prediction_with_explanation = PredictionWithExplanation(value="", prediction_type="")

@dataclass_json
@dataclass
class SubmissionAnalyticsMetadata:
    predicted_schedules: list[Recommendation]
    used_modal_form: bool
    used_recommended_schedule: bool
    used_schedule_dropdown: bool
    used_default_schedule: bool
    used_favorite_schedule: bool
    default_schedule: Optional[RecordSchedule] = None

@dataclass_json
@dataclass
class ECMSMetadata:
    file_path: str
    custodian: str
    title: str
    record_schedule: RecordSchedule
    sensitivity: str
    description: Optional[str] = ''
    creator: Optional[str] = ''
    creation_date: Optional[str] = None
    close_date: Optional[str] = None
    disposition_date: Optional[str] = None
    rights: Optional[list[str]] = field(default_factory=list)
    coverage: Optional[list[str]] = field(default_factory=list)
    relationships: Optional[list[str]] = field(default_factory=list)
    tags: Optional[list[str]] = field(default_factory=list)
    identifiers: Optional[Dict[str, list[str]]] = None
    record_id: Optional[str] = None

    def __hash__(self):
        return hash((self.custodian, self.file_path))

@dataclass_json
@dataclass
class ECMSMetadataV2:
    file_path: str
    ## Remove creator field once FE does
    ## TODO: We are not using this field for now - we will use it when the FE implements the ability to change the custodian
    custodian: str
    title: str
    record_schedule: RecordSchedule
    sensitivity: str
    access_restriction_status: str
    use_restriction_status: str
    essential_records: str
    rights_holder: Optional[list[str]] = field(default_factory=list)
    specific_access_restriction: Optional[list[str]] = field(default_factory=list)
    specific_use_restriction: Optional[list[str]] = field(default_factory=list)
    description: Optional[str] = ''
    close_date: Optional[str] = None
    disposition_date: Optional[str] = None
    epa_contacts: Optional[list[str]] = field(default_factory=list)
    cui_pii_categories: Optional[list[str]] = field(default_factory=list)
    creators: Optional[list[str]] = field(default_factory=list)
    subjects: Optional[list[str]] = field(default_factory=list)
    spatial_extent: Optional[list[str]] = field(default_factory=list)
    temporal_extent: Optional[list[str]] = field(default_factory=list)
    tags: Optional[list[str]] = field(default_factory=list)
    identifiers: Optional[Dict[str, list[str]]] = None
    record_id: Optional[str] = None

    def __hash__(self):
        return hash((self.custodian, self.file_path))

## Example metadata:
## {"file_path":"", "custodian":"", "title":"", "record_schedule":{"function_number":"401","schedule_number":"1006","disposition_number":"b"}, "sensitivity":"shared"}

@dataclass_json
@dataclass 
class NuxeoDocInfo:
    sensitivity: str
    uid: str
    name: str
    size: float
    custodian: str
    upload_date: str
    metadata: Optional[ECMSMetadata] = None

@dataclass_json
@dataclass 
class NuxeoRecordList:
    records: list[NuxeoDocInfo]
    total: int
    
@dataclass_json
@dataclass 
class MyRecordsRequestV2:
    items_per_page: int = 10
    page_number: int = 0
    query: Optional[str] = None
    nuxeo_env: Optional[str] = "dev"
    shared_private_filter: Optional[str] = 'NONE'

@dataclass_json
@dataclass 
class RecordDownloadRequestV2:
    name: str
    uid: str
    nuxeo_env: Optional[str] = "dev"

@dataclass_json
@dataclass 
class MetadataPrediction:
    predicted_schedules: list[Recommendation]
    default_schedule: Optional[RecordSchedule]
    title: PredictionWithExplanation
    description: PredictionWithExplanation
    subjects: list[str]
    identifiers: Dict[str, str]
    cui_categories: Optional[list[str]] = None
    is_encrypted: bool = False
    spatial_extent: Optional[list[str]] = None
    temporal_extent: Optional[list[str]] = None

mock_predicted_schedules = [
    Recommendation(**{"schedule": RecordSchedule(**{"function_number": "404", "schedule_number": "1012", "disposition_number": "e"}), "probability": 0.6403017640113831}), 
    Recommendation(**{"schedule": RecordSchedule(**{"function_number": "404", "schedule_number": "1012", "disposition_number": "b"}), "probability": 0.19178320467472076}), 
    Recommendation(**{"schedule": RecordSchedule(**{"function_number": "401", "schedule_number": "1006", "disposition_number": "b"}), "probability": 0.0495888851583004})]
mock_metadata_prediction = MetadataPrediction(predicted_schedules=mock_predicted_schedules, title=mock_prediction_with_explanation, description=mock_prediction_with_explanation, default_schedule=mock_predicted_schedules[0].schedule, subjects=[], identifiers={})

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
    request_id: Optional[str] = None

mock_status_response = StatusResponse("OK", "This is a mock.")

@dataclass_json
@dataclass 
class TextPredictionRequest:
    text: str
    prediction_metadata: Optional[PredictionMetadata]

@dataclass_json
@dataclass 
class EmailPredictionRequestGraph:
    email_id: str
    mailbox: str
    file_name: Optional[str] = None
    department: Optional[str] = None

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
    cc: str
    subject: str
    sent: str
    received: str
    attachments: list[EmailAttachment]
    mailbox_source: str
    categories: list[str] = field(default_factory=list)

@dataclass_json
@dataclass 
class SemsProgramType:
    acronym: str
    id: str

@dataclass_json
@dataclass 
class SemsOperableUnit:
    name: str
    id: str
    sequence: str

@dataclass_json
@dataclass 
class SemsSite:
    id: str
    region: str
    epaId: str
    siteName: str 
    programType: SemsProgramType
    operableUnits: Optional[list[SemsOperableUnit]] = field(default_factory=list)
    ssIds: Optional[list[str]] = field(default_factory=list)
    programId: Optional[str] = None

@dataclass_json
@dataclass 
class NuxeoBlob:
    filename: str
    mimetype: str
    digest: str
    length: int

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
class SemsSiteRequest:
    region_id: list[str]
    search_term: Optional[str] = None
    program_type: Optional[list[str]] = None
    page_size: Optional[int] = None
    page_start: Optional[int] = None

@dataclass_json
@dataclass 
class SemsPagination:
    pageSize: Optional[int]
    pageStart: Optional[int]
    totalRecords: int

@dataclass_json
@dataclass 
class SemsSiteResponse:
    pagination: SemsPagination
    sites: list[SemsSite]

@dataclass_json
@dataclass 
class GetCloseDate:
    close_date: str
    record_schedule: str

@dataclass_json
@dataclass 
class DispositionDate:
    disposition_date: str

@dataclass_json
@dataclass 
class BadgeInfo:
    id: str
    name: str
    description: str
    image_url: str

@dataclass_json
@dataclass 
class ProfileInfo:
    points: str
    level: str
    office_rank: str
    overall_rank: str

@dataclass_json
@dataclass 
class UserSettings:
    preferred_system: str
    default_edit_mode: str

default_settings = UserSettings('ARMS', 'basic')

@dataclass_json
@dataclass 
class UserInfo:
    email: str
    display_name: str
    lan_id: str
    department: str
    parent_org_code: str
    manager_department: Optional[str]
    manager_parent_org_code: Optional[str]
    employee_number: str
    badges: list[BadgeInfo]
    profile: Optional[ProfileInfo]
    user_settings: UserSettings
    direct_reports: list[str]
    first_name: Optional[str]
    last_name: Optional[str]

@dataclass_json
@dataclass 
class GamificationDataRequest:
    employee_number: str
    
@dataclass_json
@dataclass 
class GamificationDataResponse:
    badges: list[BadgeInfo]
    profile: Optional[ProfileInfo]

mock_email_metadata = EmailMetadata(**{
    'unid': '<DM6PR09MB549690B3AC3ED29A07A4B0B0B78D9@DM6PR09MB5496.namprd09.prod.outlook.com>',
    'subject': 'Test Subject',
    'email_id': 'AAMkADc3MTVlN2YwLWI4ZTMtNDZkMS04OGI2LTk3MzBkMmQxMDNhMwBGAAAAAABq49v7gFnsRqMkXEzRx+O2BwD/n/+gsFwRQaN01L30xNjJAAAAAAENAAD/n/+gsFwRQaN01L30xNjJAAZdx/btAAA=',
    'received': 'Wed Feb 10 17:13:32 UTC 2021',
    '_from': 'ECMS3 Test <ECMS3Test@testusepa.onmicrosoft.com>',
    'to': 'ECMS3Test@testusepa.onmicrosoft.com',
    'cc': '',
    'sent': 'Wed Feb 10 17:13:31 UTC 2021',
    'attachments': [],
    'mailbox_source': 'regular'
    })

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
class TikaResult:
    text: str
    is_encrypted: bool
    cui_categories: list[str]

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
    emailsource: str

@dataclass_json
@dataclass 
class AttachmentSchedule:
    name: str
    schedule: RecordSchedule
    close_date: Optional[str] = None
    disposition_date: Optional[str] = None

@dataclass_json
@dataclass 
class UploadEmailRequestV3:
    metadata: ECMSMetadataV2
    mailbox: str
    email_id: str
    email_unid: str
    user_activity: SubmissionAnalyticsMetadata
    nuxeo_env: Optional[str] = 'dev'
    attachment_schedules: Optional[list[AttachmentSchedule]] = field(default_factory=list)

@dataclass_json
@dataclass 
class SEMSAttachmentInfo:
    sems_uid: str
    name: str
    attachment_id: str
    record_schedule: RecordSchedule

@dataclass_json
@dataclass 
class SEMSMetadata:
    sems_uid: str
    region: str
    program_type: str
    sites: list[str]
    ous: list[str]
    ssids: list[str]
    record_schedule: RecordSchedule
    access_control: list[str]
    program_areas: list[str]
    special_processing: list[str]
    processing_comments: str
    description: str
    tags: list[str]
    file_name: str

@dataclass_json
@dataclass 
class BatchUploadData:
    id: str
    status: str
    source: str
    email: str
    user_id: str
    sems_metadata: Optional[SEMSMetadata] = None
    upload_metadata: Optional[ECMSMetadataV2] = None
    mailbox: Optional[str] = None
    completion_date: Optional[str] = None

@dataclass_json
@dataclass 
class BatchUploadResponse:
    batches: list[BatchUploadData]
    
@dataclass_json
@dataclass 
class EmailInfo:
    to: list[str]
    cc: list[str]
    _from: str
    date: str
    subject: str

@dataclass_json
@dataclass 
class UploadSEMSEmail:
    metadata: SEMSMetadata
    email_info: EmailInfo
    mailbox: str
    email_id: str
    record_id: str
    email_unid: str
    attachment_info: list[SEMSAttachmentInfo]
    nuxeo_env: Optional[str] = 'dev'

@dataclass_json
@dataclass 
class UploadResponse:
    record_id: str
    uid: str

@dataclass_json
@dataclass 
class AddParentChildRequest:
    parent_id: str
    child_ids: list[str]
    nuxeo_env: Optional[str] = 'dev'

@dataclass_json
@dataclass 
class MarkSavedRequestGraph:
    sensitivity: str 
    email_id: str
    mailbox: str

@dataclass_json
@dataclass 
class GetFavoritesResponse:
    favorites: list[RecordSchedule]

mock_get_favorites_response = GetFavoritesResponse(favorites = mock_schedules)

@dataclass_json
@dataclass 
class SharepointIdsResponse:
    site_id: str
    list_id: str
    shared_drive_id: str
    private_drive_id: str

@dataclass_json
@dataclass 
class SharepointRecord:
    web_url: str
    sensitivity: str
    name: str
    drive_item_id: str
    created_date: str
    last_modified_date: str
    size: int
    path_tags: list[str]
    detected_schedule: Optional[RecordSchedule]

@dataclass_json
@dataclass 
class CreateDelegationRequest:
    target_employee_number: str
    
@dataclass_json
@dataclass 
class SearchUsersRequest:
    prefix: str
    count: int

@dataclass_json
@dataclass 
class WAMUserInfo:
    employee_number: str
    email: str
    display_name: str

@dataclass_json
@dataclass 
class UserSearchResponse:
    users: list[WAMUserInfo]

@dataclass_json
@dataclass 
class SharepointListResponse:
    records: list[SharepointRecord]
    total_count: int

@dataclass_json
@dataclass 
class GetSharepointRecordsRequest:
    page_number: Optional[int] = 1
    items_per_page: Optional[int] = 10
    filter_type: Optional[str] = 'ready_for_submission'

@dataclass_json
@dataclass 
class SharepointPredictionRequest:
    drive_item_id: str
    file_name: Optional[str] = None
    department: Optional[str] = None

@dataclass_json
@dataclass 
class SharepointUploadRequestV2:
    drive_item_id: str
    metadata: ECMSMetadata
    user_activity: SubmissionAnalyticsMetadata
    nuxeo_env: Optional[str] = 'dev'

@dataclass_json
@dataclass 
class SharepointUploadRequestV3:
    drive_item_id: str
    metadata: ECMSMetadataV2
    user_activity: SubmissionAnalyticsMetadata
    nuxeo_env: Optional[str] = 'dev'

@dataclass_json
@dataclass 
class BatchUploadRequest:
    source: str
    system: Optional[str] = 'ARMS'
    metadata: Optional[ECMSMetadataV2] = None
    sems_metadata: Optional[SEMSMetadata] = None
    email_source: Optional[str] = 'regular'
    mailbox: Optional[str] = None

@dataclass_json
@dataclass 
class GetHelpItemRequest:
    name: str

@dataclass_json
@dataclass 
class HelpItem:
    name: str
    html_content: str
    markdown_content: str
    is_faq: str
    question: Optional[str]

@dataclass_json
@dataclass 
class AllHelpItemsResponse:
    help_items: list[HelpItem]

@dataclass_json
@dataclass 
class HelpId:
    name: str
    is_faq: bool

@dataclass_json
@dataclass
class SEMSEmailUploadRequest:
    tags: list[str]
    title: str
    creation_date: str
    region: str
    program_type: str
    site: str
    access_control: str
    program_area: str
    special_processing: str
    comments: str
    description: str
    email_uid: str

@dataclass_json
@dataclass
class LogActivityRequest:
    employee_id: str
    lan_id: str
    office_code: str
    event_id: str
    bulk_number: Optional[int] = 1

@dataclass_json
@dataclass
class UpdatePreferredSystemRequest:
    preferred_system: str

@dataclass_json
@dataclass
class UpdateEditModeRequest:
    default_edit_mode: str

@dataclass_json
@dataclass
class DelegationRequestData:
    request_id: str
    requesting_user_employee_number: str
    requesting_user_display_name: str
    target_user_employee_number: str
    target_user_display_name: str
    date_sent: str
    request_status: str
    status_date: Optional[str]
    expiration_email_sent: bool

@dataclass_json
@dataclass
class ListDelegationRequestResponse:
    delegation_requests: list[DelegationRequestData]
    incoming_requests: list[DelegationRequestData]

@dataclass_json
@dataclass
class DelegationResponse:
    request_id: str
    is_accepted: bool

@dataclass_json
@dataclass
class DelegationRuleData:
    rule_id: int
    submitting_user_employee_number: str
    submitting_user_display_name: str
    target_user_employee_number: str
    target_user_display_name: str

@dataclass_json
@dataclass
class DelegationRuleResponse:
    submitting_rules: list[DelegationRuleData]
    target_rules: list[DelegationRuleData]

@dataclass_json
@dataclass
class DeleteDelegationRuleRequest:
    rule_id: int

