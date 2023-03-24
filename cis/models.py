from . import db
import enum
from sqlalchemy.dialects.mysql import JSON

class BatchUploadStatus(enum.Enum):
    COMPLETE = 1
    PENDING = 2
    ERROR = 3

class BatchRecordStatus(enum.Enum):
  COMPLETE = 1
  FAILED_TO_DOWNLOAD_CONTENT = 2
  NUXEO_UPLOAD_FAILED = 3
  FAILED_TO_UPDATE_SHAREPOINT = 4
  UNKNOWN_ERROR = 5

class BatchUploadSource(enum.Enum):
    ONEDRIVE = 1
    OUTLOOK = 2

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    lan_id = db.Column(db.String(50), unique=True, index=True)
    favorites = db.relationship("Favorite", backref="user")
    submissions = db.relationship("RecordSubmission", backref="user")
    user_settings = db.relationship("AppSettings", backref="user")
    batch_uploads = db.relationship("BatchUpload", backref="user")

class Favorite(db.Model):
    __tablename__ = 'favorite'
    id = db.Column(db.Integer, primary_key=True)
    function_number = db.Column(db.String(10))
    schedule_number = db.Column(db.String(10))
    disposition_number = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    __table_args__ = (db.UniqueConstraint('user_id', 'function_number', 'disposition_number', 'schedule_number', name='_user_favorites_uc'),)

class BatchUpload(db.Model):
    __tablename__ = 'batch_upload'
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.Enum(BatchUploadStatus))
    source = db.Column(db.Enum(BatchUploadSource))
    system = db.Column(db.String(50), nullable=True)
    employee_number = db.Column(db.String(200))
    program_office = db.Column(db.String(200))
    aa_ship = db.Column(db.String(200))
    email = db.Column(db.String(200))
    email_source = db.Column(db.String(200))
    mailbox = db.Column(db.String(200))
    completion_date = db.Column(db.DateTime(), nullable=True)
    upload_metadata = db.Column(JSON, nullable=True)
    sems_metadata = db.Column(JSON, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    records = db.relationship("BatchUploadRecords", backref="batch")

class BatchUploadRecords(db.Model):
    __tablename__ = 'batch_upload_records'
    id = db.Column(db.Integer, primary_key=True)
    drive_item_id = db.Column(db.String(200), nullable=True)
    email_id = db.Column(db.String(200), nullable=True)
    nuxeo_id = db.Column(db.String(200), nullable=True)
    sems_id = db.Column(db.String(200), nullable=True)
    upload_date = db.Column(db.DateTime(), nullable=True)
    status = db.Column(db.Enum(BatchRecordStatus))
    batch_upload_id = db.Column(db.Integer, db.ForeignKey('batch_upload.id'), index=True)

class RecordSubmission(db.Model):
    __tablename__ = 'record_submission'
    id = db.Column(db.Integer, primary_key=True)
    arms_documentum_id = db.Column(db.String(30))
    arms_nuxeo_id = db.Column(db.String(100))
    predicted_schedule_one = db.Column(db.String(30))
    predicted_schedule_one_probability = db.Column(db.Float)
    predicted_schedule_two = db.Column(db.String(30))
    predicted_schedule_two_probability = db.Column(db.Float)
    predicted_schedule_three = db.Column(db.String(30))
    predicted_schedule_three_probability = db.Column(db.Float)
    default_schedule = db.Column(db.String(30))
    selected_schedule = db.Column(db.String(30))
    used_modal_form = db.Column(db.Boolean)
    used_recommended_schedule = db.Column(db.Boolean)
    used_schedule_dropdown = db.Column(db.Boolean)
    used_default_schedule = db.Column(db.Boolean)
    used_favorite_schedule = db.Column(db.Boolean)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)

class AppSettings(db.Model):
    __tablename__ = 'user_settings'
    id = db.Column(db.Integer, primary_key=True)
    system = db.Column(db.String(10))
    default_edit_mode = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    __table_args__ = (db.UniqueConstraint('user_id', name='_user_settings_uc'),)
