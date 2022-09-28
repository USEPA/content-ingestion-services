from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, upgrade
from yaml import Loader, load
from flask_swagger_ui import get_swaggerui_blueprint
from .validation import PublicKeyCache
from .record_schedule_cache import RecordScheduleCache
from .hf_model import HuggingFaceModel
from .app_config import config_from_file
import logging
from .shared_mailbox_manager import SharedMailboxManager
from .help_item_cache import HelpItemCache
from .secrets_manager import load_all_secrets
from .keyword_extractor import IdentifierExtractor, KeywordExtractor, CapstoneDetector

logging.basicConfig(level=logging.INFO, format = '[%(asctime)s] %(levelname)s in %(module)s: %(message)s')

db = SQLAlchemy()
migrate = Migrate()
key_cache = PublicKeyCache()
schedule_cache = None
help_item_cache = None
identifier_extractor = None
capstone_detector = None
c = None
model = None
mailbox_manager = None
SWAGGER_URL = ''  # URL for exposing Swagger UI
SWAGGER_PATH = 'swagger.yaml'
swagger_yml = load(open(SWAGGER_PATH, 'r'), Loader=Loader)


def create_app(env, region_name, model_path, capstone_path, label_mapping_path, office_info_mapping_path, config_path, mailbox_data_path, vocab_path, keyword_idf_path, database_uri, documentum_prod_username, documentum_prod_password, wam_username, wam_password, bucket_name, priority_categories_path, db_schema_change=False, tika_server=None, cis_server=None, ezemail_server=None, upgrade_db=False, documentum_prod_url=None, wam_host=None):
    """Construct the core application."""
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object("flask_config.Config")
    global model, c, mailbox_manager, schedule_cache, keyword_extractor, identifier_extractor, help_item_cache, capstone_detector
    c = config_from_file(config_path)
    if env == 'cloud':
        load_all_secrets(c, region_name, app.logger)
        app.logger.info('Secrets loaded.')
    if not db_schema_change:
        keyword_extractor = KeywordExtractor(vocab_path, priority_categories_path, keyword_idf_path)
        identifier_extractor = IdentifierExtractor()
        capstone_detector = CapstoneDetector(capstone_path)
        app.logger.info('Keyword extractor initialized.')
        mailbox_manager = SharedMailboxManager(mailbox_data_path)
        app.logger.info('Mailboxes loaded.')
        app.logger.info('Config loaded.')
        app.logger.info('Loading help items.')
        help_item_cache = HelpItemCache(c, app.logger)
        app.logger.info('Help items loaded.')
        schedule_cache = RecordScheduleCache(c, app.logger)
        app.logger.info('Record schedule cache loaded.')
        if tika_server:
            c.tika_server = tika_server
        if cis_server:
            c.cis_server = cis_server
        if ezemail_server:
            c.ezemail_server = ezemail_server
        if database_uri:
            c.database_uri = database_uri
        if documentum_prod_username:
            c.documentum_prod_username = documentum_prod_username
        if documentum_prod_password:
            c.documentum_prod_password = documentum_prod_password
        if documentum_prod_url:
            c.documentum_prod_url = documentum_prod_url
        if wam_username:
            c.wam_username = wam_username
        if wam_password:
            c.wam_password = wam_password
        if wam_host:
            c.wam_host = wam_host
        if bucket_name:
            c.bucket_name = bucket_name
        
        
        app.app_context().push()
        model = HuggingFaceModel(model_path, label_mapping_path, office_info_mapping_path)
        app.logger.info('Model loaded.')
        swagger_yml['host'] = c.cis_server
        blueprint = get_swaggerui_blueprint(SWAGGER_URL, SWAGGER_PATH, config={'spec': swagger_yml})
        app.register_blueprint(blueprint)
    app.config['SQLALCHEMY_DATABASE_URI'] = c.database_uri
    db.init_app(app)
    migrate.init_app(app, db)
    app.logger.info('Database initialized.')
    with app.app_context():
        from . import routes  # Import routes
        app.logger.info(db.engine)
        if upgrade_db:
            upgrade()

        return app