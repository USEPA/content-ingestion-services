"""App entry point."""
from cis import create_app
from waitress import serve
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='The CIS backend server provides APIs which power the EZDesktop application.')
    parser.add_argument('--model_path', 
                    help='Path to HuggingFace classifier model.')
    parser.add_argument('--label_mapping_path', 
                    help='Path to mapping between prediction indices and corresponding record schedules.')
    parser.add_argument('--config_path', default='dev_config.json',
                    help='Path to config file with environment dependent variables.')
    parser.add_argument('--tika_server', default=None,
                    help='Host for tika service.')
    parser.add_argument('--cis_server', default=None,
                    help='Host for this (CIS) service.')
    parser.add_argument('--ezemail_server', default=None,
                    help='Host for ezemail service.')
    parser.add_argument('--database_uri', default=None,
                    help='Host for ezemail service.')
    parser.add_argument('--upgrade_db', default=False, action="store_true", 
                    help='Whether to upgrade the db.')
    args = parser.parse_args()
    app = create_app(**vars(args))
    serve(app, host='0.0.0.0', port=8000)