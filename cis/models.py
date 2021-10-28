from . import db

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    lan_id = db.Column(db.String(50), unique=True, index=True)
    favorites = db.relationship("Favorite", backref="user")
    submissions = db.relationship("RecordSubmission", backref="user")

class Favorite(db.Model):
    __tablename__ = 'favorite'
    id = db.Column(db.Integer, primary_key=True)
    function_number = db.Column(db.String(10))
    schedule_number = db.Column(db.String(10))
    disposition_number = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    __table_args__ = (db.UniqueConstraint('user_id', 'function_number', 'disposition_number', 'schedule_number', name='_user_favorites_uc'),)

class RecordSubmission(db.Model):
    __tablename__ = 'record_submission'
    id = db.Column(db.Integer, primary_key=True)
    arms_documentum_id = db.Column(db.String(30))
    arms_nuxeo_id = db.Column(db.String(30))
    predicted_schedule_one = db.Column(db.String(30))
    predicted_schedule_one_probability = db.Column(db.Float)
    predicted_schedule_two = db.Column(db.String(30))
    predicted_schedule_two_probability = db.Column(db.Float)
    predicted_schedule_three = db.Column(db.String(30))
    predicted_schedule_three_probability = db.Column(db.Float)
    default_schedule = db.Column(db.String(30))
    used_modal_form = db.Column(db.Boolean)
    used_recommended_schedule = db.Column(db.Boolean)
    used_schedule_dropdown = db.Column(db.Boolean)
    used_default_schedule = db.Column(db.Boolean)
    used_favorite_schedule = db.Column(db.Boolean)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)