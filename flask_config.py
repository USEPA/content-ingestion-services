class Config:
    """Set Flask configuration from .env file."""
    # Database
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False