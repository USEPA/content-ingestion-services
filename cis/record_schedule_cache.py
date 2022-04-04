import json
from .data_classes import RecordScheduleInformation, RecordScheduleList, RecordSchedule
from datetime import datetime
import threading
import requests

class RecordScheduleCache:
    def __init__(self, config, dnul_path, logger):
      self.logger = logger
      dnu_items = []
      with open(dnul_path, 'r') as f:
        for line in f:
          csv = line.split(',')
          dnu_items.append(csv[1])
      self.dnu_items = dnu_items
      self.config = config
      _, self.schedules, self.schedule_mapping = get_record_schedules(config, self.dnu_items, self.logger)
      self.update_ts = datetime.now()
      self.lock = threading.Lock()

    def get_schedules(self):
      with self.lock:
        diff = datetime.now() - self.update_ts
        if diff.total_seconds() > 24 * 60 * 60:
          request_success, schedules, schedule_mapping = get_record_schedules(self.config, self.dnu_items, self.logger)
          if not request_success:
            self.logger.info('Record schedule refresh failed and no data is cached. Defaulting to local data.')
          self.schedules = schedules
          self.schedule_mapping = schedule_mapping
          self.update_ts = datetime.now()
        return self.schedules
    
    def get_schedule_mapping(self):
      with self.lock:
        return self.schedule_mapping
    
def process_schedule_data(schedule_dict):
  return RecordScheduleInformation(
      function_number=str(schedule_dict['function_code'])[:3],
      schedule_number=schedule_dict['schedule_number'],
      disposition_number=schedule_dict['item_number'],
      display_name=schedule_dict['schedule_item_number'],
      schedule_title=schedule_dict['schedule_title'],
      disposition_title=schedule_dict['item_title'],
      disposition_instructions=schedule_dict['disposition_instructions'],
      cutoff_instructions=schedule_dict['cutoff_instructions'],
      function_title=schedule_dict['function_title'],
      program=schedule_dict['program'],
      applicability=schedule_dict['applicability'],
      nara_disposal_authority_item_level=schedule_dict['nara_disposal_authority_item_level'],
      nara_disposal_authority_schedule_level=schedule_dict['nara_disposal_authority_record_schedule_level'],
      final_disposition=schedule_dict['final_disposition'],
      disposition_summary=schedule_dict['disposition_summary'],
      description=schedule_dict['schedule_description'],
      guidance=schedule_dict['guidance'],
      keywords=schedule_dict['keywords'],
      ten_year=int(schedule_dict['ten_year']) == 1
  )

def get_record_schedules(config, dnu_items, logger):
  # If API request fails, fall back to local data.
  try:
    data = {"query": "{ ecms__record_Schedule (orderBy: {id: \"asc\"}) {  __all_columns__  }}"}
    r = requests.post('https://' + config.record_schedules_server + '/dmapservice/query', data=data, timeout=10)
    result = r.json()['data']['ecms__record_schedule']
    request_success = True
  except:
    logger.info('Failed to fetch record schedule data. Defaulting to local data.')
    with open('record_schedule_data.json', 'r') as f:
      result = json.loads(f.read())
    request_success = False
  filtered_results = list(filter(lambda x: x['schedule_item_number'] not in dnu_items, result))
  schedule_list = RecordScheduleList([process_schedule_data(x) for x in filtered_results])
  schedule_mapping = {
    (sched.display_name):RecordSchedule(sched.function_number, sched.schedule_number, sched.disposition_number) 
    for sched in schedule_list.schedules}
  return request_success, schedule_list, schedule_mapping