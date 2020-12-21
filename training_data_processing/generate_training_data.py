import argparse
import pandas as pd
from datetime import datetime, timedelta
import urllib
from io import BytesIO
from zipfile import ZipFile 
from random import randrange
import requests
import os

documentum_start = datetime.strptime('1/1/2008', '%m/%d/%Y')

def get_random_date_range(time_span=30):
    """
    This function will return a random datetime between 2008 (around when Documentum was first used) and now.
    """
    end = datetime.now()
    delta = end - documentum_start
    int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
    random_second = randrange(int_delta)
    range_start = documentum_start + timedelta(seconds=random_second)
    range_end = range_start + timedelta(days=time_span)
    return (range_start, range_end)

def dql_request(sql, username, password):
    url = "https://ecms.epa.gov/dctm-rest/repositories/ecmsrmr65?dql=" + urllib.parse.quote(sql)
    headers = {'cache-control': 'no-cache'}
    r = requests.get(url, headers=headers, auth=(username,password))
    return r

def get_batch(office_name, office_code, output_dir, username, password, batch_size, time_span=30, retry_number=0):
    # If time span is too large, give up.
    if retry_number > 2:
        print('Records could not be found after 3 retries.')
        return []
    
    # Get ERMA DOC IDs within a random date range
    start, end = get_random_date_range(time_span)
    doc_id_sql = "select DISTINCT(s.ERMA_DOC_ID) from ECMSRMR65.ERMA_DOC_SV s where lower(group_name) = '" + office_code + "' and s.R_CREATION_DATE > date('" + start.strftime('%m/%d/%Y %H:%M:%S') + "') and s.R_CREATION_DATE < date('" + end.strftime('%m/%d/%Y %H:%M:%S') +"') enable (return_top " + str(batch_size) + ");"
    doc_id_req = dql_request(doc_id_sql, username, password)
    if doc_id_req.status_code != 200:
        print('Doc ID request failed.')
        return []
    doc_id_resp = doc_id_req.json()
    if 'entries' not in doc_id_resp:
        print("No documents found for " + office_code + ', retrying.')
        new_retry = retry_number + 1
        return get_batch(office_name, office_code, output_dir, username, password, batch_size, retry_number=new_retry)
    doc_ids = [x['content']['properties']['erma_doc_id'] for x in doc_id_resp['entries']]
    
    # Fetch all records related to these doc IDs
    doc_where_clause = ' OR '.join(["erma_doc_id = '" + str(x) + "'" for x in doc_ids])
    doc_info_sql = "select s.object_name,s.ERMA_DOC_ID as erma_doc_id, s.ERMA_DOC_CUSTODIAN, s.R_OBJECT_ID,s.ERMA_DOC_TITLE,group_name from ECMSRMR65.ERMA_DOC_SV s where " + doc_where_clause + ";"
    r = dql_request(doc_info_sql, username, password)
    
    if r.status_code == 200:
        resp = r.json()
        hrefs = ['https://ecms.epa.gov/dctm-rest/repositories/ecmsrmr65/objects/' + x['content']['properties']['r_object_id'] for x in resp['entries']]
        data = {'hrefs': list(set(hrefs))}
        archive_url = 'https://ecms.epa.gov/dctm-rest/repositories/ecmsrmr65/archived-contents'
        post_headers = {
            'cache-control': 'no-cache',
            'Content-Type': 'application/vnd.emc.documentum+json'
        }
        archive_req = requests.post(archive_url, headers=post_headers, json=data, auth=(username,password))
        if archive_req.status_code == 200:
            # Unzip files into memory
            f = BytesIO()
            for chunk in archive_req.iter_content(chunk_size=1024): 
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                    
            sheet_data = [x['content']['properties'] for x in resp['entries']]
            
            # Group metadata by ERMA Doc ID
            grouped_data = {}
            for x in sheet_data:
                _id = x['erma_doc_id']
                if _id not in grouped_data:
                    grouped_data[_id] = {
                        'object_name': [x['object_name']],
                        'erma_doc_id': _id,
                        'erma_doc_custodian': x['erma_doc_custodian'], 
                        'r_object_id': [x['r_object_id']],
                        'erma_doc_title': [x['erma_doc_title']],
                        'group_name': x['group_name'],
                        'files': [],
                        'record_schedule': '',
                        'comments' : ''
                    }
                else:
                    current = grouped_data[_id]
                    current['object_name'].append(x['object_name'])
                    current['r_object_id'].append(x['r_object_id'])
                    current['erma_doc_title'].append(x['erma_doc_title'])
            
            # Match files with corresponding metadata, then write files to directories corresponding to doc ids
            with ZipFile(f, 'r') as zip: 
                for info in zip.infolist():
                    filename = info.filename 
                    for k in grouped_data.keys():
                        key = k[1:]
                        if key in filename:
                            grouped_data[k]['files'].append(filename)
                            break
                
                dupes = set()
                for k in grouped_data.keys():
                    path = os.path.join(output_dir, k)
                    if not os.path.isdir(path):
                        os.mkdir(path)
                        files = grouped_data[k]['files']
                        for file in files:
                            with open(os.path.join(path, file), 'wb') as fw:
                                fw.write(zip.read(file))
                    else:
                        dupes.add(k)
            
            # Remove any dupes
            for dupe in dupes:
                grouped_data.pop(dupe)
            
            # Format spreadsheet data
            return_data = list(grouped_data.values())
            for x in return_data:
                x['object_name'] = ','.join(x['object_name'])
                x['r_object_id'] = ','.join(x['r_object_id'])
                x['erma_doc_title'] = ','.join(x['erma_doc_title'])
                x['files'] = ','.join(x['files'])
            return return_data       
        else:
            print('Status code ' + r.status_code + ' encountered for archive request.')
            return []
    
def fetch_data(office_name, office_code, num_records, output_dir, username, password, batch_size=10):
    num_batches = int(num_records / batch_size)
    records = [get_batch(office_name, office_code, output_dir, username, password, batch_size) for x in range(num_batches)]
    flattened = [item for sublist in records for item in sublist]
    return flattened


def generate_training_data(request_file_name, data_output_dir, spreadsheet_path, username, password):
    if not os.path.isdir(data_output_dir):
        os.mkdir(data_output_dir)
    req = pd.read_excel(request_file_name, engine='openpyxl', sheet_name=0)
    req = req[~req['Office Name'].isna()].rename(columns={'Number of Records (will be round to nearest 10)':'num_records', 'Office Name':'office_name', 'Organization':'office_code'})
    requests = list(req.T.to_dict().values())
    served_requests = [fetch_data(r['office_name'], r['office_code'], r['num_records'], data_output_dir, username, password) for r in requests]
    flattened = [item for sublist in served_requests for item in sublist]
    sheet = pd.DataFrame.from_records(flattened)
    sheet.to_excel(spreadsheet_path, engine='openpyxl', index=False)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates samples from documents already labeled with record schedules so that they can be reviewed. Produces a spreadsheet for annotation, a folder with the documents, and a zip file with the documents.')
    parser.add_argument('--request_file_name', default='Categorization Record Request.xlsx',
                    help='Name of the file containing the record request.')
    parser.add_argument('--data_output_dir', default='record_annotations_data',
                    help='Directory where raw data will be stored.')
    parser.add_argument('--spreadsheet_path', default='record_annotations.xlsx',
                    help='Path where spreadsheet will be stored')
    parser.add_argument('--username', 
                    help='Username for Documentum.')
    parser.add_argument('--password', default='record_request',
                    help='Password for Documentum.')
    args = parser.parse_args()
    generate_training_data(**vars(args))
    