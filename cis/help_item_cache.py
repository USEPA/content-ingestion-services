from .data_classes import HelpItem, HelpId
import json
from datetime import datetime
import threading
import requests 

class HelpItemCache:
    def __init__(self, config,  logger):
        self.config = config
        self.logger = logger
        with open(help_id_path, 'r') as f:
            self.help_item_ids = json.loads(f.read())
            self.help_item_ids = [HelpId(**x) for x in self.help_item_ids]
        self.help_items = fetch_help_items(config, self.help_item_ids, self.logger)
        if self.help_items is None:
          self.logger.info('Failed to load help items on startup.')
        self.update_ts = datetime.now()
        self.lock = threading.Lock()

    def get_help_items(self):
        diff = datetime.now() - self.update_ts
        with self.lock:
          if diff.total_seconds() > 60 * 60 or self.help_items is None:
            updated_items = fetch_help_items(self.config, self.help_item_ids, self.logger)
            if updated_items is None:
                self.logger.info('Failed to fetch help items.')
            else:
                self.help_items = updated_items
            self.update_ts = datetime.now()
          return self.help_items


def fetch_help_items(config, help_ids, logger):
    try:
        help_items = []
        for help_id in help_ids:
            r = requests.get("https://" + config.patt_host + "/app/helptext/?pages/" + help_id.name +  "&output=json", timeout=30)
            if r.status_code != 200:
                if r.status_code == 404:
                    logger.error('Page not found for help_id = ' + help_id.name)
                    continue
                else:
                    logger.error('Help content request failed for help_id = ' + help_id.name)
                    continue
            content = r.json()
            html_content = content.get('content', None)
            markdown_content = content.get('raw_content', None)
            response = HelpItem(name=help_id.name, html_content=html_content, markdown_content=markdown_content, is_faq=help_id.is_faq)
            help_items.append(response)
        if len(help_items) == 0:
            return None
        else:
            return help_items
    except:
        return None

def fetch_help_item_list(config, logger):
    try:
        help_item_list = []
        r = requests.get("https://" + config.patt_host + "/app/plugins/markdown-editor/scripts/json.php", timeout=30)
        if r.status_code != 200:
            logger.error('Help list request failed.')
            return None
        files = r.json()['files']
        for f in files:
            name = f['file']
            # determine whether the file is an FAQ. If it is, find both the question and answer for that FAQ.
            if name[:3] == 'faq':
                prefix = 
        help_items.append(response)
        if len(help_items) == 0:
            return None
        else:
            return help_items
    except:
        return None
    