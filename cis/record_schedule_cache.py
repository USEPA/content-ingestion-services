import json
from .data_classes import RecordScheduleInformation, RecordScheduleList, RecordSchedule
from datetime import datetime
import threading
import requests

class RecordScheduleCache:
    def __init__(self, config, logger):
      self.logger = logger  
      self.config = config
      _, self.schedules, self.schedule_mapping = get_record_schedules(config, self.logger)
      self.update_ts = datetime.now()
      self.lock = threading.Lock()

    def get_schedules(self):
      with self.lock:
        diff = datetime.now() - self.update_ts
        if diff.total_seconds() > 24 * 60 * 60:
          request_success, schedules, schedule_mapping = get_record_schedules(self.config, self.logger)
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
      display_name=schedule_dict['schedule_item_number'],
      schedule_number=schedule_dict['schedule_number'],
      schedule_title=schedule_dict['schedule_title'],
      disposition_number=schedule_dict['item_number'],
      disposition_title=schedule_dict['item_title'],
      function_number=str(schedule_dict['function_code']),
      function_title=schedule_dict['function_title'],
      program=schedule_dict['program'],
      applicability=schedule_dict['applicability'],
      nara_disposal_authority_schedule_level=schedule_dict['nara_disposal_authority_record_schedule_level'],
      nara_disposal_authority_item_level=schedule_dict['nara_disposal_authority_item_level'],
      final_disposition=schedule_dict['final_disposition'],
      cutoff_instructions=schedule_dict['cutoff_instructions'],
      disposition_instructions=schedule_dict['disposition_instructions'],
      description=schedule_dict['schedule_description'],
      reserved_flag=int(schedule_dict['reserved_flag']) == 1,
      superseded_flag=int(schedule_dict['superseded_flag']) == 1,      
      deleted_flag=int(schedule_dict['deleted_flag']) == 1,    
      draft_flag=int(schedule_dict['draft_flag']) == 1,        
      system_flag=int(schedule_dict['system_flag']) == 1,     
      calendar_year_flag=int(schedule_dict['calendar_year_flag']) == 1, 
      fiscal_year_flag=int(schedule_dict['fiscal_year_flag']) == 1,
      disposition_summary=schedule_dict['disposition_summary'],
      guidance=schedule_dict['guidance'],
      retention_year=int(schedule_dict['retention_year'] or 0),
      retention_month=int(schedule_dict['retention_month'] or 0),
      retention_day=int(schedule_dict['retention_day'] or 0),
      ten_year=int(schedule_dict['ten_year']) == 1,
      epa_approval=schedule_dict['epa_approval'],
      nara_approval=schedule_dict['nara_approval'],
      previous_nara_disposal_authority=schedule_dict['previous_nara_disposal_authority'],
      status=schedule_dict['status'],
      custodians=schedule_dict['custodians'],
      reasons_for_disposition=schedule_dict['reasons_for_disposition'],
      related_schedules=schedule_dict['related_schedules'],
      entry_date=schedule_dict['entry_date'],
      revised_date=schedule_dict['revised_date'],
      action=schedule_dict['action'],
      keywords=schedule_dict['keywords'],
      keywords_title=schedule_dict['keywords_title'],
      keywords_subject=schedule_dict['keywords_subject'],
      keywords_org=schedule_dict['keywords_org'],
      related_terms=schedule_dict['related_terms'],
      dnul_flag=int(schedule_dict['dnul_flag']) == 1,
      last_modified_flag=int(schedule_dict['last_modified_flag']) == 1
  )

def get_record_schedules(config, logger):
  # If API request fails, fall back to local data.
  try:
    data = {"query": "{ ecms__record_Schedule (orderBy: {id: \"asc\"}) {  __all_columns__  }}"}
    r = requests.post('https://' + config.record_schedules_server + '/dmapservice/gateway-query', data=data, timeout=10)
    result = r.json()['data']['ecms__record_schedule']
    request_success = True
  except:
    logger.info('Failed to fetch record schedule data. Defaulting to local data.')
    with open('record_schedule_data.json', 'r') as f:
      result = json.loads(f.read())
    request_success = False
  filtered_results = list(filter(lambda x: not x.get('dnul_flag', False), result))
  schedule_list = RecordScheduleList([process_schedule_data(x) for x in filtered_results])
  schedule_mapping = {
    (sched.display_name):RecordSchedule(sched.function_number, sched.schedule_number, sched.disposition_number) 
    for sched in schedule_list.schedules}
  return request_success, schedule_list, schedule_mapping
