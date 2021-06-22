from .data_classes import SemsSite
from datetime import datetime
import threading
import requests 

class SemsSiteCache:
    def __init__(self, config):
        self.config = config
        self.sites = get_sems_sites(config)
        self.update_ts = datetime.now()
        self.lock = threading.Lock()

    def get_sites(self, region):
        diff = datetime.now() - self.update_ts
        with self.lock:
          if diff.total_seconds() > 24 * 60 * 60:
            self.sites = get_sems_sites(self.config, self.dnu_items)
            self.update_ts = datetime.now()
          return self.sites[region]


def get_sems_sites(config):
    sites = requests.get('http://' + config.sems_host + '/sems-ws/outlook/getSites')
    site_objects = [SemsSite(_id=site['id'], region=site['region'], epaid=site.get('epaid', ''), sitename=site['sitename']) for site in sites.json()]
    grouped_by_region = {}
    for site in site_objects:
      if site.region not in grouped_by_region:
        grouped_by_region[site.region] = [site]
      else:
        grouped_by_region[site.region].append(site)
    return grouped_by_region
    