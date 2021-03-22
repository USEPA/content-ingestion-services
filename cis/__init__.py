from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, upgrade
from yaml import Loader, load
from flask_swagger_ui import get_swaggerui_blueprint
from .validation import PublicKeyCache
from .hf_model import HuggingFaceModel
from .app_config import config_from_file
from logging.config import dictConfig

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        'datefmt':"%m/%d/%Y %I:%M:%S %p %Z"
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': 'INFO',
        'handlers': ['wsgi']
    }
})

db = SQLAlchemy()
migrate = Migrate()
key_cache = PublicKeyCache()
c = None
model = None
SWAGGER_URL = ''  # URL for exposing Swagger UI
SWAGGER_PATH = 'swagger.yaml'
swagger_yml = load(open(SWAGGER_PATH, 'r'), Loader=Loader)

def create_app(model_path, label_mapping_path, config_path, tika_server=None, cis_server=None, ezemail_server=None, database_uri=None, upgrade_db=False):

    
    """Construct the core application."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object("flask_config.Config")

    global model, c
    
    c = config_from_file(config_path)
    if tika_server:
        c.tika_server = tika_server
    if cis_server:
        c.cis_server = cis_server
    if ezemail_server:
        c.ezemail_server = ezemail_server
    if database_uri:
        c.database_uri = database_uri
    app.config['SQLALCHEMY_DATABASE_URI'] = c.database_uri
    app.app_context().push()
    db.init_app(app)
    migrate.init_app(app, db)
    model = HuggingFaceModel(model_path, label_mapping_path)
    swagger_yml['host'] = c.cis_server
    blueprint = get_swaggerui_blueprint(SWAGGER_URL, SWAGGER_PATH, config={'spec': swagger_yml})
    app.register_blueprint(blueprint)

    with app.app_context():
        from . import routes  # Import routes
        app.logger.info(db.engine)
        #upgrade()
        #db.create_all()  # Create database tables for our data models

        return app