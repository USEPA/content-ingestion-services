import boto3
import numpy as np
import os
from datetime import date
import pandas as pd
import argparse
import shutil

def generate_samples(bucket_name, prefix, num_samples):
    # Fetch files from S3
    print('Listing files')
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(bucket_name)
    files = []
    for bucket_object in bucket.objects.filter(Prefix=prefix):
        files.append(bucket_object)
    
    # Filter to relevant files
    files = list(filter(lambda x: len(x.key.split('/')) == 3, files)) ## TODO handle case where prefix has multiple path components
    not_nrmp = list(filter(lambda x: '_NRMP' not in x.key and '-guidance.txt' not in x.key and '-description.txt' not in x.key, files))
    
    # Sample files
    sampled = np.random.choice(not_nrmp[1:], num_samples, replace=False)
    sampled = sorted(sampled,key= lambda x: x.key.split('/')[-1])
    
    # Prepare folder for downloading files
    today = date.today()
    d4 = today.strftime("%m-%d-%Y")
    folder_name = 'nrmp-review-' + d4
    if not os.path.isdir(folder_name):
        os.mkdir(folder_name)
    
    # Download files and create data for spreadsheet
    print('Downloading files.')
    s3_client = boto3.client('s3')
    data = []
    for obj in sampled:
        bucket = obj.bucket_name
        key = obj.key
        file_name = key.split('/')[-1]
        record_schedule = key.split('/')[-2]
        data.append({'file_name':file_name, 'schedule':record_schedule})
        with open(folder_name + '/' + file_name, 'wb') as f:
            s3_client.download_fileobj(bucket, key, f)
    
    print('Creating zip archive and spreadsheet.')
    # Create zip archive
    shutil.make_archive('Training Data QA-' + d4, 'zip', folder_name)
    
    # Format and write spreadsheet
    df = pd.DataFrame.from_records(data)
    df['Action'] = ""
    df['Comment'] = ""
    names = ['File', 'Schedule', 'Action', 'Comment']
    df.to_excel('Training Data QA Spreadsheet-' + d4 + '.xlsx', header=names, index=False)
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generates samples from documents already labeled with record schedules so that they can be reviewed. Produces a spreadsheet for annotation, a folder with the documents, and a zip file with the documents.')
    parser.add_argument('--bucket_name', 
                    help='AWS bucket to fetch data from.')
    parser.add_argument('--prefix', default='deepdetect/',
                    help='Prefix within the bucket where data is stored. Data is expected to be in <prefix>/<record schedule>/<data.txt> format.')
    parser.add_argument('--num_samples', default=1000, type=int,
                    help='Number of samples to pull for review.')
    args = parser.parse_args()
    generate_samples(**vars(args))