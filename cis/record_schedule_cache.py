import json
import pandas as pd
from .data_classes import RecordScheduleInformation, RecordScheduleList
from datetime import datetime
import threading
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport

class RecordScheduleCache:
    def __init__(self, config, dnul_path):
        dnul = pd.read_csv(dnul_path)
        self.config = config
        self.dnu_items = list(dnul['Disposition Item '])
        self.schedules = get_record_schedules(config, self.dnu_items)
        self.update_ts = datetime.now()
        self.lock = threading.Lock()

    def get_schedules(self):
        diff = datetime.now() - self.update_ts
        with self.lock:
          if diff.total_seconds() > 30 * 60:
            self.schedules = get_record_schedules(self.config, self.dnu_items)
            self.update_ts = datetime.now()
          return self.schedules
    
def process_schedule_data(schedule_dict):
    try:
        function_number = str(int(float(schedule_dict['functionCode'])))
    except:
        function_number = schedule_dict['functionCode']
    return RecordScheduleInformation(
        function_number=function_number,
        schedule_number=schedule_dict['scheduleNumber'],
        disposition_number=schedule_dict['itemNumber'],
        display_name=schedule_dict['scheduleItemNumber'],
        schedule_title=schedule_dict['scheduleTitle'],
        disposition_title=schedule_dict['itemTitle'],
        disposition_instructions=schedule_dict['dispositionInstructions'],
        cutoff_instructions=schedule_dict['cutoffInstructions'],
        function_title=schedule_dict['functionTitle'],
        program=schedule_dict['program'],
        applicability=schedule_dict['applicability'],
        nara_disposal_authority_item_level=schedule_dict['naraDisposalAuthorityItemLevel'],
        nara_disposal_authority_schedule_level=schedule_dict['naraDisposalAuthorityRecordScheduleLevel'],
        final_disposition=schedule_dict['finalDisposition'],
        disposition_summary=schedule_dict['dispositionSummary'],
        description=schedule_dict['scheduleDescription'],
        guidance=schedule_dict['guidance'],
        keywords=schedule_dict['keywords']
    )

def get_record_schedules(config, dnu_items):
  transport = RequestsHTTPTransport(
    url="https://" + config.record_schedules_server + "/ecms-graphql/graphql", verify=True, retries=3,
  )

  client = Client(transport=transport, fetch_schema_from_transport=True)

  query = gql(
    """
    query schedulesQuery {
      recordSchedules(
        orderBy: [SCHEDULE_NUMBER_DESC]
      ) {
        nodes {
          id
          scheduleItemNumber
          scheduleNumber
          scheduleTitle
          itemNumber
          itemTitle
          functionCode
          functionTitle
          program
          applicability
          naraDisposalAuthorityRecordScheduleLevel
          naraDisposalAuthorityItemLevel
          finalDisposition
          cutoffInstructions
          dispositionInstructions
          scheduleDescription
          reservedFlag
          dispositionSummary
          guidance
          retention
          tenYear
          status
          revisedDate
          reasonsForDisposition
          custodians
          relatedSchedules
          previousNaraDisposalAuthority
          entryDate
          epaApproval
          naraApproval
          keywords
          keywordsTitle
          keywordsSubject
          keywordsOrg
          relatedTerms
        }
      }
    }
  """
  )

  result = client.execute(query)
  filtered_results = list(filter(lambda x: x['scheduleItemNumber'] not in dnu_items, result['recordSchedules']['nodes']))
  return RecordScheduleList([process_schedule_data(x) for x in filtered_results])