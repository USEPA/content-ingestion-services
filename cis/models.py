from . import db

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    lan_id = db.Column(db.String(50), unique=True, index=True)
    favorites = db.relationship("Favorite", backref="user")

class Favorite(db.Model):
    __tablename__ = 'favorite'
    id = db.Column(db.Integer, primary_key=True)
    function_number = db.Column(db.String(10))
    schedule_number = db.Column(db.String(10))
    disposition_number = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    __table_args__ = (db.UniqueConstraint('user_id', 'function_number', 'disposition_number', 'schedule_number', name='_user_favorites_uc'),)
    