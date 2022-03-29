from .data_classes import HelpItem, HelpId
import json
from datetime import datetime
import threading
import requests 

class HelpItemCache:
    def __init__(self, config,  logger):
        self.config = config
        self.logger = logger
        self.help_item_ids = fetch_help_item_list(config, logger)
        self.help_items = fetch_help_items(config, self.help_item_ids, self.logger)
        if self.help_items is None:
          self.logger.info('Failed to load help items on startup.')
        self.update_ts = datetime.now()
        self.lock = threading.Lock()

    def get_help_items(self):
        diff = datetime.now() - self.update_ts
        with self.lock:
            if diff.total_seconds() > 60 * 60 or self.help_items is None:
                self.help_item_ids = fetch_help_item_list(self.config, self.logger)
                updated_items = fetch_help_items(self.config, self.help_item_ids, self.logger)
                if updated_items is None:
                    self.logger.info('Failed to fetch help items.')
                else:
                    self.logger.info('Updated help items.')
                    self.help_items = updated_items
                self.update_ts = datetime.now()
        return self.help_items
    
    def update_help_items(self):
        with self.lock:
            self.help_item_ids = fetch_help_item_list(self.config, self.logger)
            updated_items = fetch_help_items(self.config, self.help_item_ids, self.logger)
            if updated_items is None:
                self.logger.info('Failed to fetch help items.')
            else:
                self.logger.info('Updated help items.')
                self.help_items = updated_items
            self.update_ts = datetime.now()

def query_help_id(config, name, logger):
    r = requests.get("https://" + config.patt_host + "/app/helptext/?pages/" + name +  "&output=json", timeout=30)
    if r.status_code != 200:
        if r.status_code == 404:
            logger.error('Page not found for help_id = ' + name)
            return None, None
        else:
            logger.error('Help content request failed for help_id = ' + name)
            return None, None
    content = r.json()
    html_content = content.get('content', None)
    markdown_content = content.get('raw_content', None)
    return html_content, markdown_content

def fetch_help_items(config, help_item_ids, logger):
    try:
        help_items = []
        for prefix, item in help_item_ids.items():
            if item['is_faq']:
                _, question = query_help_id(config, item['question_index'], logger)
                html_content, markdown_content = query_help_id(config, item['content_index'], logger)
                if question is None or html_content is None or markdown_content is None:
                    logger.info('Failed to load non-FAQ item with name ' + prefix)
                else:
                    help_items.append(HelpItem(name=prefix, html_content=html_content, markdown_content=markdown_content, is_faq=True, question=question))
            else:
                html_content, markdown_content = query_help_id(config, prefix, logger)
                if html_content is None or markdown_content is None:
                    logger.info('Failed to load non-FAQ item with name ' + prefix)
                else:
                    help_items.append(HelpItem(name=prefix, html_content=html_content, markdown_content=markdown_content, is_faq=False, question=None))
        if len(help_items) == 0:
            return None
        else:
            return help_items
    except:
        return None

def fetch_help_item_list(config, logger):
    try:
        help_item_list = {}
        r = requests.get("https://" + config.patt_host + "/app/plugins/markdown-editor/scripts/json.php", timeout=30)
        if r.status_code != 200:
            logger.error('Help list request failed.')
            return None
        files = r.json()['files']
        for f in files:
            name = f['file']
            # determine whether the file is an FAQ. If it is, find both the question and answer for that FAQ.
            if name[:3] == 'faq':
                split = name.split('-')
                question_answer = split[-1]
                prefix = '-'.join(split[:-1])
                if prefix not in help_item_list:
                    help_item_list[prefix] = {
                        'is_faq':True, 
                        'content_index': None, 
                        'question_index': None
                        }
                if question_answer == 'question':
                    help_item_list[prefix]['question_index'] = name 
                else:
                    help_item_list[prefix]['content_index'] = name
            else:
                help_item_list[name] = {
                    'content_index': name,
                    'is_faq': False,
                    'question_index': None
                }
        return help_item_list
    except:
        return None
    