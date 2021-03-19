class Config:
    """Set Flask configuration from .env file."""

    # General Config
    SECRET_KEY = "test"
    FLASK_ENV = "dev"

    # Database
    #SQLALCHEMY_DATABASE_URI = r'test.db'
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False