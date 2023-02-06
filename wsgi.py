"""App entry point."""
from cis import create_app
from waitress import serve
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='The CIS backend server provides APIs which power the EZDesktop application.')
    parser.add_argument('--env', default='local',
                    help='Environment where application is running. Options are local and cloud.')
    parser.add_argument('--region_name', default=None,
                    help='Region for cloud environment.')
    parser.add_argument('--model_path', default='/home/models/trained_model',
                    help='Path to HuggingFace classifier model.')
    parser.add_argument('--capstone_path', default='/home/models/capstone_officials.csv',
                    help='Path to list of Capstone officials.')
    parser.add_argument('--label_mapping_path', default='/home/models/label_mapping.json',
                    help='Path to mapping between prediction indices and corresponding record schedules.')
    parser.add_argument('--office_info_mapping_path', default='/home/models/office_info_mapping.json',
                    help='Path to mapping between office acronym and office description.')
    parser.add_argument('--config_path', default='dev_config.json',
                    help='Path to config file with environment dependent variables.')
    parser.add_argument('--patt_host', default=None,
                    help='Host for PATT service.')
    parser.add_argument('--patt_api_key', default=None,
                    help='API key for PATT service.')
    parser.add_argument('--tika_server', default=None,
                    help='Host for tika service.')
    parser.add_argument('--cis_server', default=None,
                    help='Host for this (CIS) service.')
    parser.add_argument('--ezemail_server', default=None,
                    help='Host for ezemail service.')
    parser.add_argument('--database_uri', default=None,
                    help='Database connection string.')
    parser.add_argument('--upgrade_db', default=False, action="store_true", 
                    help='Whether to upgrade the db.')
    parser.add_argument('--mailbox_data_path', default='shared_mailboxes_by_user.json', 
                    help='Path to dictionary of shared mailboxes.')
    parser.add_argument('--vocab_path', default='keyword_category.csv', 
                    help='EPA enterprise vocabulary.')
    parser.add_argument('--keyword_idf_path', default='keyword_idf.json', 
                    help='Inverse document frequency values for keywords.')
    parser.add_argument('--water_bodies_path', default='/home/water_bodies.csv', 
                    help='Path to list of water bodies.')
    parser.add_argument('--cities_path', default='/home/uscities.csv', 
                    help='Path to list of cities.')
    parser.add_argument('--priority_categories_path', default='rscategories.txt', 
                    help='EPA enterprise vocabulary.')
    parser.add_argument('--wam_host', default=None, 
                    help='Host for WAM service.')
    parser.add_argument('--wam_username', default=None, 
                    help='Username for WAM service.')
    parser.add_argument('--wam_password', default=None, 
                    help='Password for WAM service.')
    parser.add_argument('--bucket_name', help='Bucket name for uploads.')
    args = parser.parse_args()
    app = create_app(**vars(args))
    serve(app, host='0.0.0.0', port=8000)