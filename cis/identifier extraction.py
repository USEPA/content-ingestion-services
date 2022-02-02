# 4 columns to the spreadsheet: filename, record/non-record, non-record code, custodian
# Determine whether the text file being processed is a record or non-record

from rebulk import Rebulk
from os import path
import os
import os.path
import getpass
import re

username = getpass.getuser()

folderpath = "C:\\Users\\" + username + "\\Environmental Protection Agency (EPA)\\ECMS - Documents\\New Technology Migration\identifer extraction\\samples"
directory = os.fsencode(folderpath)

for file in os.listdir(directory):

    filename = os.fsdecode(file)
    filepath = folderpath +  '\\' + filename

    if('.txt' in filename):
  
        # content of message defined as empty in case file is corrupted
        content = ''
        try:
            with open(filepath, "rb") as f:
                content = f.read().decode("utf-8")
                # print(content)

                #FACILITIES
                #Facility Registry ID (e.g. 110036409464)
                facility_id = Rebulk().regex(r'110\d{9}').matches(content)
                
                for i in facility_id:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"Facility ID":"'+ extracted_val+'"')

                #TRI Facility ID (e.g. 90058GSSRL2618F)
                tri_id = Rebulk().regex(r'\d{5}[B-DF-HJ-NP-TV-Z0-9]{10}').matches(content)

                for i in tri_id:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"TRI Facility ID":"'+ extracted_val+'"')

                #Docket ID (e.g. EPA-HQ-OPP-2014-0483-0001)
                docket_id = Rebulk().regex(r'EPA-([a-zA-Z0-9]{2,3})-([a-zA-Z]{2,5})-\d{4}-\d{4}-\d{4}').matches(content)
                
                for i in docket_id:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"Docket ID":"'+ extracted_val+'"')
                ######
                        
                #SUBSTANCES
                #CAS Number (e.g. 11121-31-6)
                cas_num = Rebulk().regex(r'\d{2,7}-\d{2}-\d{1}').matches(content)

                for i in cas_num:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"CAS Number":"'+ extracted_val+'"')        
                #International Chemical Identifier Key (e.g. FBMORZZOJSDNRQ-GLQYFDAESA-N)
                inchikey = Rebulk().regex(r'([A-Z0-9]{14})-([A-Z0-9]{10})-([A-Z0-9]{1})').matches(content)

                for i in inchikey:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"InChI Key":"'+ extracted_val+'"')
                #DSSTox ID (e.g. DTXSID6020014)
                dsstox = Rebulk().regex(r'DTXSID\d{7,9}').matches(content)

                for i in dsstox:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"DSSTox ID":"'+ extracted_val+'"')
                #SRS ID (e.g. 1736818)
                srs = Rebulk().regex(r'(?i)\b(srs|srs id|internal tracking number)\s?\d{1,100}').matches(content)


                for i in srs:
                    extracted_val = re.sub('\D', '', str(i).replace('<','').split(':(', 1)[0])
                    if extracted_val:
                        print('"SRS":"'+ extracted_val+'"')
                        
                ######
                        
                #INDUSTRY IDENTIFICATION
                #NAICS Code (e.g. NAICS 311221)
                naics = Rebulk().regex(r'(?i)\b(naics|naics code|naics no|naics num|niacs no|naics no\.|naics \#)\s?([ ]|[:]|[\-])\s?\d{5,6}').matches(content)

                for i in naics:
                    extracted_val = re.findall('\d{5,6}', str(i))[0]
                    if extracted_val:
                        print('"NAICS":"'+ extracted_val+'"')

                #SIC Code (e.g. SIC 311221)
                sic = Rebulk().regex(r'(?i)\b(sic|sic code|sic no|sic num|sic no|sic no\.|sic \#)\s?([ ]|[:]|[\-])\s?\d{4}').matches(content)

                for i in sic:
                    extracted_val = re.findall('\d{4}', str(i))[0]
                    if extracted_val:
                        print('"SIC":"'+ extracted_val+'"')
                ######

                #COMPANY IDENTIFICATION

                #UEI
                
                #DUNS Number (e.g. 02-507-5342)
                duns = Rebulk().regex(r'0([0-9]{1})-([0-9]{3})-([0-9]{4})').regex(r'0([0-9]{8})0000').regex(r'(?i)\b(duns|duns no|duns num|duns no|duns no\.|duns \#)\s?([ ]|[:]|[\-])\s?\d{8}').matches(content)
                for i in duns:
                    if re.search('[a-zA-Z]', str(i)):
                        extracted_val = re.findall('\d{8}', str(i))[0]
                    else:
                        extracted_val = str(i).replace('<','').split(':(', 1)[0]

                    if extracted_val:
                        print('"DUNS":"'+ extracted_val+'"')
                ######
                        
                #CFDA Number for Grants (e.g. CFDA 10.001)
                cfda = Rebulk().regex(r'(?i)\b(cfda|cfda code|cfda no|cfda num|cfda no\.|cfda \#)\s?([ ]|[:]|[\-])\s?\d+\.\d{0,3}').matches(content)

                for i in cdfa:
                    extracted_val = re.findall('\d+\.\d{0,3}', str(i))[0]
                    if extracted_val:
                        print('"CDFA":"'+ extracted_val+'"')

                #BIA Tribal Code for Grants (e.g. BIA A10)
                bia = Rebulk().regex(r'(?i)\b(tribal code|bia|bia tribal code|bia code|bia num|bia no|bia no\.|bia \#)\s?([ ]|[:]|[\-])\s?\d{3}').regex(r'(?i)\b(tribal code|bia|bia tribal code|bia code|bia num|bia no\.|bia \#)\s?([ ]|[:]|[\-])\s?[A]\d{0,2}').matches(content)

                for i in bia:
                    extracted_val = str(i).split(':(')[0][-3:]
                    
                    if extracted_val:
                        print('"BIA":"'+ extracted_val+'"')


                #EPA Registration Number (e.g. EPA Reg. No. 3120-280-1492)
                epa_reg_number = Rebulk().regex(r'(?i)\b(epa registration no\.|epa reg\. no\.)\s?([ ]|[:]|[\-])\s?\d{0,4}-\d{0,4}(?:-\d{0,4})?').matches(content)

 
                for i in epa_reg_number:

                    extracted_val = re.findall('\d{0,4}-\d{0,4}(?:-\d{0,4})?', str(i))[0]
                    if extracted_val:
                        print('"EPA Registration Number":"'+ extracted_val+'"')

                #EPA Establishment Number (e.g. EPA Est. No. 264-MO-02)
                epa_est_number = Rebulk().regex(r'(?i)\b(epa est\. no\.|epa est\.)\s?([ ]|[:]|[\-])\s?\d{0,4}-[A-Z]{2}-\d{0,4}').matches(content)

 
                for i in epa_est_number:

                    extracted_val = re.findall('\d{0,4}-[A-Z]{2}-\d{0,4}', str(i))[0]
                    if extracted_val:
                        print('"EPA Establishment Number":"'+ extracted_val+'"')

                #Hydrologic Unit Codes (HUCs) (e.g. 180902030303)
                huc = Rebulk().regex(r'(?i)\b(huc|hydrologic unit code)\s?([ ]|[:]|[\-])\s?(?:[0-9]{2,12})*').matches(content)


                for i in huc:
                    extracted_val = re.sub('\D', '', str(i).replace('<','').split(':(', 1)[0])
                    if extracted_val:
                        print('"HUC":"'+ extracted_val+'"')
                
                # PATT ID (e.g. 0000010-3-02-1-a1)
                #patt_id = Rebulk().regex(r'\d{7}-\d{1,3}-[0][1-2]-\d{1,4}(-[a]\d{1,4})?').matches(content)
                
                #for i in patt_id:
                #    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                #    if extracted_val:
                #        print('"PATT ID":"'+ extracted_val+'"')
                
                # NPDES Permit No. (e.g. GUS040001, GU0020371)
                npdes_id = Rebulk().regex(r'\b[a-zA-z]{2}\d{7}|[a-zA-Z]{3}\d{6}\b').matches(content)
                
                for i in npdes_id:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"NPDES Permit No.":"'+ extracted_val+'"')
                        
                # SEMS EPA ID (CERCLA ID?) e.g. MAD001026319
                sems_epa_id = Rebulk().regex(r'\b[a-zA-z]{3}\d{9}\b').matches(content)
                
                for i in sems_epa_id:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"SEMS EPA ID":"'+ extracted_val+'"')

                #FINANCE
                #EPA Contact Number (e.g. EPC07058)
                epa_contract_number = Rebulk().regex(r'(?i)\b(contract number|contract num|contract no|contract no\.|contract \#)\s?([ ]|[:]|[\-])\s?[A-Z0-9]{8,14}').matches(content)

 
                for i in epa_contract_number:

                    extracted_val = re.findall('[A-Z0-9]{8,14}', str(i))[0]
                    if extracted_val:
                        print('"EPA Contract Number":"'+ extracted_val+'"')


                #ebusiness Registration ID (e.g. R0499360)
                registration_id = Rebulk().regex(r'(?i)\b(registration id|ebusiness registration id)\s?([ ]|[:]|[\-])\s?R[A-Z0-9]{7}').matches(content)

 
                for i in registration_id:

                    extracted_val = re.findall('R[A-Z0-9]{7}', str(i))[0]
                    if extracted_val:
                        print('"eBusiness Registration ID":"'+ extracted_val+'"')


                #PR Number (e.g. PR00013635)
                pr_number = Rebulk().regex(r'PR\d{8}').matches(content)

 
                for i in pr_number:

                    extracted_val = re.findall('PR\d{8}', str(i))[0]
                    if extracted_val:
                        print('"PR Number":"'+ extracted_val+'"')

                #Service Account Number (e.g. 22DPEHSTRAT)
                sa_number = Rebulk().regex(r'(?i)\b(sa|service account|sa no|sa no\.|sa \#)\s?([ ]|[:]|[\-])\s?\d{2}[A-Z0-9]{9}').matches(content)

 
                for i in sa_number:

                    extracted_val = re.findall('\d{2}[A-Z0-9]{9}', str(i))[0]
                    if extracted_val:
                        print('"SA Number":"'+ extracted_val+'"')

                #RE RQ Number (e.g. RE|15H3CAE030)
                re_rq_number = Rebulk().regex(r'(?i)\b(re|re no|re no\.|re \#|rq|rq no|rq no\.|rq \#)\s?([ ]|[:]|[\-])\s?(RQ|RE)([|])?[A-Z0-9]{1,10}').matches(content)

 
                for i in re_rq_number:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        extracted_val = re.sub(r'^.*?RE', 'RE', extracted_val)
                        extracted_val = re.sub(r'^.*?RQ', 'RQ', extracted_val)
                        print('"RE RQ Number":"'+ extracted_val+'"')
                ######

                #DOCUMENT/DATA RELATED
                #DOI Number (e.g. 10.1080/15588742.2015.1017687)
                doi_number = Rebulk().regex(r'\b10\.(\d+\.*)+[\/](([^\s\.])+\.*)+\b').matches(content)
                
                for i in doi_number:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"DOI Number":"'+ extracted_val+'"')

                #EDG UUID (e.g. E95156F3-39BE-4734-9999-0DFAEE036BA6), may change later
                uuid = Rebulk().regex(r'[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}').matches(content)
                
                for i in uuid:
                    extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    if extracted_val:
                        print('"EDG UUID":"'+ extracted_val+'"')

                 #EPA Publication Number (e.g. EPA 430F10028, 200-B-96-001)
                epa_pub = Rebulk().regex(r'\d{3}-[a-zA-z]-\d{2}-\d{3}').regex(r'(?i)\b(epa|epa publication|epa publication number|epa publication num|epa publication no|epa publication no\.|epa publication \#)\s?([ ]|[:]|[\-])\s?\d{3}[a-zA-z]\d{5}').matches(content)

 
                for i in epa_pub:

                    if re.search('[-]', str(i)):
                        extracted_val = str(i).replace('<','').split(':(', 1)[0]
                    else:
                        extracted_val = str(i).split(':(')[0][-9:]
                    if extracted_val:
                        print('"EPA Publication":"'+ extracted_val+'"')
                ######

        except:
            print('error')
