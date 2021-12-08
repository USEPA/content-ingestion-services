from .data_classes import SemsSite
from datetime import datetime
import threading
import requests 

class SemsSiteCache:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.sites = get_sems_sites(config, logger)
        if self.sites is None:
          self.logger.info('Failed to load SEMS sites on startup.')
        self.update_ts = datetime.now()
        self.lock = threading.Lock()

    def get_sites(self, region):
        diff = datetime.now() - self.update_ts
        with self.lock:
          if diff.total_seconds() > 24 * 60 * 60:
            updated_sites = get_sems_sites(self.config, self.logger)
            if updated_sites is None:
                self.logger.info('Failed to get site information.')
            else:
              self.sites = updated_sites
            self.update_ts = datetime.now()
          if self.sites is None:
            updated_sites = get_sems_sites(self.config, self.logger)
            if updated_sites is not None:
              self.sites = updated_sites
            else:
              self.logger.info('Failed to retrieve sites on demand.')
              return None
          return self.sites[region]


def get_sems_sites(config, logger):
  grouped_by_region = {}
  regions = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11']
  try:
    for region in regions:
      logger.info('Loading region ' + region)
      regional_sites = requests.get('http://' + config.sems_host + '/sems-ws/outlook/getSites?region_id=' + region, timeout=60)
      site_objects = [
        SemsSite(
          _id=site['id'], 
          region=site['region'], 
          epaid=site.get('epaId', None), 
          sitename=site.get('siteName', None), 
          program_id=site.get('programId', None),
          operable_units=site.get('operableUnits', None),
          ssids=site.get('ssIds', None)
          ) 
        for site in regional_sites.json()['sites']]
      grouped_by_region[region] = site_objects
    return grouped_by_region
  except:
    return None

    