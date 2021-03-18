"""Initialize Flask app."""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from yaml import Loader, load
from flask_swagger_ui import get_swaggerui_blueprint
from .validation import PublicKeyCache
from .hf_model import HuggingFaceModel
from .app_config import config_from_file

db = SQLAlchemy()
migrate = Migrate()
key_cache = PublicKeyCache()
c = None
model = None
SWAGGER_URL = ''  # URL for exposing Swagger UI
SWAGGER_PATH = 'swagger.yaml'
swagger_yml = load(open(SWAGGER_PATH, 'r'), Loader=Loader)

def create_app(model_path, label_mapping_path, config_path, tika_server=None, cis_server=None, ezemail_server=None):
    """Construct the core application."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object("flask_config.Config")

    db.init_app(app)
    migrate.init_app(app, db)
    global model, c
    model = HuggingFaceModel(model_path, label_mapping_path)
    c = config_from_file(config_path)
    if tika_server:
        c.tika_server = tika_server
    if cis_server:
        c.cis_server = cis_server
    if ezemail_server:
        c.ezemail_server = ezemail_server
    swagger_yml['host'] = c.cis_server
    blueprint = get_swaggerui_blueprint(SWAGGER_URL, SWAGGER_PATH, config={'spec': swagger_yml})
    app.register_blueprint(blueprint)

    with app.app_context():
        from . import routes  # Import routes
        
        #db.create_all()  # Create database tables for our data models

        return app