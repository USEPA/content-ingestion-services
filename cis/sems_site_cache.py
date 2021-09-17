from .data_classes import SemsSite
from datetime import datetime
import threading
import requests 

class SemsSiteCache:
    def __init__(self, config):
        self.config = config
        self.sites = get_sems_sites(config)
        if self.sites is None:
          print('Failed to load SEMS sites on startup.')
        self.update_ts = datetime.now()
        self.lock = threading.Lock()

    def get_sites(self, region):
        diff = datetime.now() - self.update_ts
        with self.lock:
          if diff.total_seconds() > 24 * 60 * 60:
            updated_sites = get_sems_sites(self.config)
            if updated_sites is None:
                print('Failed to get site information.')
            else:
              self.sites = updated_sites
            self.update_ts = datetime.now()
          if self.sites is None:
            updated_sites = get_sems_sites(self.config)
            if updated_sites is not None:
              self.sites = updated_sites
            else:
              print('Failed to retrieve sites on demand.')
              return None
          return self.sites[region]


def get_sems_sites(config):
  try:
    sites = requests.get('http://' + config.sems_host + '/sems-ws/outlook/getSites')
    if sites.status_code != 200:
      return None
    site_objects = [SemsSite(_id=site['id'], region=site['region'], epaid=site.get('epaid', ''), sitename=site['sitename'], ssid=site['ssid'], ou=site['operable_unit']) for site in sites.json()]
    grouped_by_region = {}
    for site in site_objects:
      if site.region not in grouped_by_region:
        grouped_by_region[site.region] = [site]
      else:
        grouped_by_region[site.region].append(site)
    return grouped_by_region
  except:
    return {}
    