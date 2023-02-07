import re
import json
from rebulk import Rebulk
import csv
import ahocorasick
import difflib
import random
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import spacy
import pandas as pd
import pytz
from datetime import datetime
import calendar

def search_keywords(automaton, content):
    keywords = []
    for end_index, (_, original_value) in automaton.iter(content.lower()):
        start_index = end_index - len(original_value) + 1
        keywords.append((original_value, start_index))
    return keywords

def extract_keywords(doc, kwtree, keyword_idf):
    keywords = search_keywords(kwtree, doc)
    keyword_counts = {}
    current_longest_word = ''
    current_starting_index = 0
    for k, v in sorted(keywords, key=lambda x: x[1]):
        word = k[1:-1]
        actual_index = v + 1
        if actual_index == current_starting_index:
            if len(word) > len(current_longest_word):
                current_longest_word = word
                continue
        if actual_index <= current_starting_index + len(current_longest_word):
            continue
        if actual_index > current_starting_index + len(current_longest_word):
            if current_longest_word != '':
                if current_longest_word not in keyword_counts:
                    keyword_counts[current_longest_word] = keyword_idf.get(current_longest_word, 1)
                else:
                    keyword_counts[current_longest_word] += keyword_idf.get(current_longest_word, 1)
            current_starting_index = actual_index
            current_longest_word = word

    if current_longest_word != '':
        if current_longest_word not in keyword_counts:
            keyword_counts[current_longest_word] = keyword_idf.get(current_longest_word, 1)
        else:
            keyword_counts[current_longest_word] += keyword_idf.get(current_longest_word, 1)
    return keyword_counts

def convert_keywords_to_subjects(text, keyword_weights, keyword_mapping, priority_categories, num_top_cats=3):
    subjects = {}
    for keyword in keyword_weights.keys():
        if keyword in keyword_mapping:
            subject = keyword_mapping[keyword]
            if subject in subjects:
                subjects[subject] += keyword_weights[keyword]
            else:
                subjects[subject] = keyword_weights[keyword]
    
    top_cats = set([x[0] for x in sorted(subjects.items(), key = lambda x: x[1], reverse = True)[:num_top_cats]])
    for p in priority_categories:
        if p in subjects and subjects[p] > 0 and len(text) <= 2000:
            top_cats.add(p)
        # 12 is chosen here since the min value of the keyword idf is ~4, and this threshold would pass if 3 common keywords are present
        # which was the original threshold
        elif p in subjects and subjects[p] >= 12 and len(text) > 2000:
            top_cats.add(p)
    return list(top_cats)

class CapstoneDetector():
    def __init__(self, capstone_path):
        index = 0
        self.capstone_kwtree = ahocorasick.Automaton()
        self.capstone_set = set([])
        with open(capstone_path, 'r') as f:
            for line in f.read().splitlines():
                item = line.lower().replace('"', '')
                for prefix in ['\n', ' ',"'",'"']:
                    for suffix in ['\n', ' ', ',','.','?',"'",'"']:
                        padded = prefix + item + suffix
                        self.capstone_kwtree.add_word(padded, (index, padded))
                        index += 1
                self.capstone_set.add(item)
        self.capstone_kwtree.make_automaton()
    
    def detect_capstone_text(self, text):
        return len(extract_keywords(text, self.capstone_kwtree, {})) > 0
    
    def detect_capstone_username(self, aliases):
        for x in aliases:
            if x.lower() in self.capstone_set:
                return True
        return False

class KeywordExtractor():
    def __init__(self, vocab_path, priority_categories_path, keyword_idf_path):
        with open(vocab_path, 'r', encoding='cp1252') as f:
            self.keyword_mapping = dict(csv.reader(f))
        with open(priority_categories_path, 'r') as f:
            self.priority_categories = f.read().splitlines()
        with open(keyword_idf_path, 'r') as f:
            self.keyword_idf = json.loads(f.read())

        self.kwtree = ahocorasick.Automaton()
        index = 0
        for row in self.keyword_mapping.keys():
            word = row.lower()
            for prefix in ['\n', ' ',"'",'"']:
                for suffix in ['\n', ' ', ',','.','?',"'",'"']:
                    padded = prefix + word + suffix
                    self.kwtree.add_word(padded, (index, padded))
            index += 1
        self.kwtree.make_automaton()
    
    def extract_keywords(self, text):
        return extract_keywords(text, self.kwtree, self.keyword_idf)
    
    def extract_subjects(self, text, keyword_weights):
        return convert_keywords_to_subjects(text, keyword_weights, self.keyword_mapping, self.priority_categories)

# Dedupe a list of identifiers case insensitively
def dedupe_lower(_set):
    result=[]
    marker = set()
    for l in _set:
        ll = l.lower()
        if ll not in marker:   
            marker.add(ll)
            result.append(l) 
    return result

class IdentifierExtractor():
    def __init__(self, cities_path, water_bodies_path):
        self.facility_regex = Rebulk().regex(r'\b110\d{9}\b')
        self.tri_regex = Rebulk().regex(r'\b\d{1,5}[A-Z]{5,10}(\d{1,5})?([A-Z]{1,3})?(\d{1,3})?\b')
        self.docket_regex = Rebulk().regex(r'\bEPA-([a-zA-Z0-9]{2,3})-([a-zA-Z]{2,5})-\d{4}-\d{4}-\d{4}\b')
        self.cas_regex = Rebulk().regex(r'\b\d{2,7}-\d{2}-\d{1}\b')
        self.inchi_regex = Rebulk().regex(r'\b([A-Z0-9]{14})-([A-Z0-9]{10})-([A-Z0-9]{1})\b')
        self.dsstox_regex = Rebulk().regex(r'\bDTXSID\d{7,9}\b')
        self.srs_regex = Rebulk().regex(r'(?i)\b(srs|srs id|internal tracking number)\s?([ ]|[:]|[\-])\s?(\b\d{1,100}\b)\b')
        self.naics_regex = Rebulk().regex(r'(?i)\b(naics|naics code|naics no|naics num|niacs no|naics no\.|naics \#)\s?([ ]|[:]|[\-])\s?(\b\d{2,6}\b)\b')
        self.sic_regex = Rebulk().regex(r'(?i)\b(sic code|sic no|sic num|sic no|sic no\.|sic \#)\s?([ ]|[:]|[\-])\s?(\b\d{4}\b)\b')
        self.duns_regex = Rebulk().regex(r'(?i)\b(duns|duns no|duns num|duns no|duns no\.|duns \#)\s?([ ]|[:]|[\-])\s?((\b[0-9]{2}-[0-9]{3}-[0-9]{4}\b)|(\b0[0-9]{8}0000\b)|(\b\d{8}\b))\b')
        self.cfda_regex = Rebulk().regex(r'(?i)\b(cfda|cfda code|cfda no|cfda num|cfda no\.|cfda \#)\s?([ ]|[:]|[\-])\s?(\b\d+.\d{0,3}\b)\b')
        self.bia_regex = Rebulk().regex(r'(?i)\b(tribal code|bia|bia tribal code|bia code|bia num|bia no|bia no\.|bia \#)\s?([ ]|[:]|[\-])\s?(\b([A]\d{0,2}\b)|(\b\d{3}\b))\b')
        self.epa_reg_regex = Rebulk().regex(r'(?i)\b(epa registration no\.|epa reg\. no\.)\s?([ ]|[:]|[\-])\s?(\b\d{0,4}-\d{0,4}(?:-\d{0,4})?\b)\b')
        self.epa_est_regex = Rebulk().regex(r'(?i)\b(epa est\. no\.|epa est\.)\s?([ ]|[:]|[\-])\s?(\b\d{0,4}-[A-Z]{2}-\d{0,4}\b)\b')
        self.huc_regex = Rebulk().regex(r'(?i)\b(huc|huc code|hydrologic unit code)\s?([ ]|[:]|[\-])\s?(\b[A-Z0-9]{2,12}\b)\b')
        self.npdes_regex = Rebulk().regex(r'(\b[a-zA-z]{2}\d{7}\b)|(\b[a-zA-Z]{3}\d{6}\b)')
        self.sems_regex = Rebulk().regex(r'\b[a-zA-z]{3}\d{9}\b')
        self.contract_regex = Rebulk().regex(r'(?i)\b(contract number|contract num|contract no|contract no\.|contract \#)\s?([ ]|[:]|[\-])\s?(\b[A-Z\-0-9]{8,14}\b)\b')
        self.ebusiness_regex = Rebulk().regex(r'(?i)\b(registration id|ebusiness registration id)\s?([ ]|[:]|[\-])\s?(\bR[A-Z0-9]{7}\b)\b')
        self.pr_regex = Rebulk().regex(r'\bPR\d{8}\b')
        self.sa_regex = Rebulk().regex(r'(?i)\b(sa|service account|sa no|sa no\.|sa \#)\s?([ ]|[:]|[\-])\s?(\b\d{2}[A-Z0-9]{9}\b)\b')
        self.re_rq_regex = Rebulk().regex(r'(?i)\b(re|re no|re no\.|re \#|rq|rq no|rq no\.|rq \#)\s?\b([ ]|[:]|[-])s?(\b(RQ|RE)[|][A-Z0-9]{1,10}\b)\b')
        self.doi_regex = Rebulk().regex(r'\b(10[.][0-9]{4,}(?:[.][0-9]+)*/(?:(?![\"&\'<>])\S)+)\b')
        self.uuid_regex = Rebulk().regex(r'\b[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\b')
        self.epa_pub_regex = Rebulk().regex(r'(?i)\b(epa|epa publication|epa publication number|epa publication num|epa publication no|epa publication no\.|epa publication \#)\s?([ ]|[:]|[\-])\s?((\b\d{3}[a-zA-z]\d{5}\b)|(\b\d{3}-[a-zA-z]-\d{2}-\d{3}\b))\b')
        self.mrid_regex = Rebulk().regex(r'(?i)\b(mrid|mrids|master record identification|mird no|mrid no\.|mrid \#)\s?([ ]|[:]|[\-])\s?(\b\d{6}00\b)\b')
        self.epa_sln_regex = Rebulk().regex(r'(?i)\b(epa sln\. no\.|epa sln\.)\s?([ ]|[:]|[\-])\s?(\b[A-Za-z]{2}\d{6}\b)\b')
        self.nara_transfer_number_regex = Rebulk().regex(r'PT-412-[0-9]{4}-[0-9]{4}')
        self.nara_disposal_authority_regex = Rebulk().regex(r'DAA-(0412|GRS)-[0-9]{4}-[0-9]{4}-[0-9]{4}')

        ## TODO: Remove pandas dependency
        self.water_list = [x.lower() for x in pd.read_csv(water_bodies_path)['body']]
        self.uscities_list = list(pd.read_csv(cities_path)['loc'])
        self.nlp = spacy.load('en_core_web_lg')
      
    def extract_identifiers(self, content):
        response = {}

        facility_id = self.facility_regex.matches(content)
        facility_ids = set()        
        for i in facility_id:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                facility_ids.add(extracted_val[0])
        response['Facility ID'] = dedupe_lower(facility_ids)

        #TRI Facility ID (e.g. 90058GSSRL2618F)
        tri_id = self.tri_regex.matches(content)
        tri_ids = set()
        for i in tri_id:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                tri_ids.add(extracted_val[0])
        tri_ids = dedupe_lower(tri_ids)
        tri_ids = list(filter(lambda x: len(x) == 15, tri_ids))
        response['TRI Facility ID'] = dedupe_lower(tri_ids)

        #Docket ID (e.g. EPA-HQ-OPP-2014-0483-0001)
        docket_id = self.docket_regex.matches(content)
        docket_ids = set()
        for i in docket_id:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                docket_ids.add(extracted_val[0])
        response['Docket ID'] = dedupe_lower(docket_ids)
                
        #SUBSTANCES
        #CAS Number (e.g. 11121-31-6)
        cas_num = self.cas_regex.matches(content)
        cas_nums = set()
        for i in cas_num:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                cas_nums.add(extracted_val[0])
        response['CAS Number'] = dedupe_lower(cas_nums)

        #International Chemical Identifier Key (e.g. FBMORZZOJSDNRQ-GLQYFDAESA-N)
        inchikey = self.inchi_regex.matches(content)
        inchis = set()
        for i in inchikey:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                inchis.add(extracted_val[0])
        response['InChI Key'] = dedupe_lower(inchis)

        #DSSTox ID (e.g. DTXSID6020014)
        dsstox = self.dsstox_regex.matches(content)
        dsstox_ids = set()
        for i in dsstox:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                dsstox_ids.add(extracted_val[0])
        response['DSSTox ID'] = dedupe_lower(dsstox_ids)

        #SRS ID (e.g. 1736818)
        srs = self.srs_regex.matches(content)
        srs_ids = set()

        for i in range(len(srs)):
            if len(srs[i].children) > 2:
                extracted_val = str(srs[i].children[2]).replace('<','').split(':(', 1)

                if len(extracted_val) > 0:
                    srs_ids.add(extracted_val[0])
        response['SRS'] = dedupe_lower(srs_ids)
                                
        #NAICS Code (e.g. NAICS 311221)
        naics = self.naics_regex.matches(content)
        naics_ids = set()

        for i in range(len(naics)):
            if len(naics[i].children) > 2:
                extracted_val = str(naics[i].children[2]).replace('<','').split(':(', 1)
                if len(extracted_val) > 0:
                    naics_ids.add(extracted_val[0])
        response['NAICS'] = dedupe_lower(naics_ids)

        #SIC Code (e.g. SIC 311221)
        sic = self.sic_regex.matches(content)
        sic_ids = set()

        for i in range(len(sic)):
            if len(sic[i].children) > 2:
                extracted_val = str(sic[i].children[2]).replace('<','').split(':(', 1)
                if len(extracted_val) > 0:
                    sic_ids.add(extracted_val[0])
        response['SIC'] = dedupe_lower(sic_ids)
        
        #DUNS Number (e.g. 02-507-5342)
        duns = self.duns_regex.matches(content)
        duns_ids = set()

        for i in range(len(duns)):
            if len(duns[i].children) > 2:
                extracted_val = str(duns[i].children[2]).replace('<','').split(':(', 1)

                if len(extracted_val) > 0:
                    duns_ids.add(extracted_val[0])
        response['DUNS'] = dedupe_lower(duns_ids)
                
        #CFDA Number for Grants (e.g. CFDA 10.001)
        cfda = self.cfda_regex.matches(content)
        cfda_ids = set()

        for i in range(len(cfda)):
            if len(cfda[i].children) > 2:
                extracted_val = str(cfda[i].children[2]).replace('<','').split(':(', 1)

                if len(extracted_val) > 0:
                    cfda_ids.add(extracted_val[0])
        response['CFDA'] = dedupe_lower(cfda_ids)

        #BIA Tribal Code for Grants (e.g. BIA A10)
        bia = self.bia_regex.matches(content)
        bia_ids = set()

        for i in range(len(bia)):
            if len(bia[i].children) > 2:
                extracted_val = str(bia[i].children[2]).replace('<','').split(':(', 1)

                if len(extracted_val) > 0:
                    bia_ids.add(extracted_val[0])
        response['BIA'] = dedupe_lower(bia_ids)

        #EPA Registration Number (e.g. EPA Reg. No. 3120-280-1492)
        epa_reg_number = self.epa_reg_regex.matches(content)
        epa_reg_ids = set()
        for i in range(len(epa_reg_number)):
            if len(epa_reg_number[i].children) > 2:
                extracted_val = str(epa_reg_number[i].children[2]).replace('<','').split(':(', 1)

                if len(extracted_val) > 0:
                    epa_reg_ids.add(extracted_val[0])
        response['EPA Registration Number'] = dedupe_lower(epa_reg_ids)

        #EPA Establishment Number (e.g. EPA Est. No. 264-MO-02)
        epa_est_number = self.epa_est_regex.matches(content)
        epa_est_ids = set()
        for i in range(len(epa_est_number)):
            if len(epa_est_number[i].children)> 2:
                extracted_val = str(epa_est_number[i].children[2]).replace('<','').split(':(', 1)

                if len(extracted_val) > 0:
                    epa_est_ids.add(extracted_val[0])
        response['EPA Establishment Number'] = dedupe_lower(epa_est_ids)

        #Hydrologic Unit Codes (HUCs) (e.g. 180902030303)
        huc = self.huc_regex.matches(content)
        huc_ids = set()
        for i in range(len(huc)):
            if len(huc[i].children) > 2:
                extracted_val = str(huc[i].children[2]).replace('<','').split(':(', 1)

                if len(extracted_val) > 0:
                    huc_ids.add(extracted_val[0])
        response['HUC'] = dedupe_lower(huc_ids)
        
        # NPDES Permit No. (e.g. GUS040001, GU0020371)
        npdes_id = self.npdes_regex.matches(content)
        npdes_ids = set()
        for i in npdes_id:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                npdes_ids.add(extracted_val[0])
        response['NPDES Permit No.'] = dedupe_lower(npdes_ids)
                
        # SEMS EPA ID (CERCLA ID?) e.g. MAD001026319
        sems_epa_id = self.sems_regex.matches(content)
        sems_ids = set()
        for i in sems_epa_id:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                sems_ids.add(extracted_val[0])
        response['SEMS EPA ID'] = dedupe_lower(sems_ids)

        #FINANCE
        #EPA Contact Number (e.g. EPC07058)
        epa_contract_number = self.contract_regex.matches(content)
        contract_numbers = set()

        for i in range(len(epa_contract_number)):
            if len(epa_contract_number[i].children) > 2:
                extracted_val = str(epa_contract_number[i].children[2]).replace('<','').split(':(', 1)      

                if len(extracted_val) > 0:
                    contract_numbers.add(extracted_val[0])
        response['EPA Contract Number'] = dedupe_lower(contract_numbers)

        #ebusiness Registration ID (e.g. R0499360)
        registration_id = self.ebusiness_regex.matches(content)
        reg_ids = set()
        for i in range(len(registration_id)):
            if len(registration_id[i].children) > 2:
                extracted_val = str(registration_id[i].children[2]).replace('<','').split(':(', 1)      

                if len(extracted_val) > 0:
                    reg_ids.add(extracted_val[0])
        response['eBusiness Registration ID'] = dedupe_lower(reg_ids)

        #PR Number (e.g. PR00013635)
        pr_number = self.pr_regex.matches(content)
        pr_numbers = set()
        for i in pr_number:
            extracted_val = re.findall('PR\d{8}', str(i))
            if len(extracted_val) > 0:
                pr_numbers.add(extracted_val[0])
        response['PR Number'] = dedupe_lower(pr_numbers)

        #Service Account Number (e.g. 22DPEHSTRAT)
        sa_number = self.sa_regex.matches(content)
        sa_numbers = set()

        for i in range(len(sa_number)):
            if len(sa_number[i].children) > 2:
                extracted_val = str(sa_number[i].children[2]).replace('<','').split(':(', 1)    

                if len(extracted_val) > 0:
                    sa_numbers.add(extracted_val[0])
        response['SA Number'] = dedupe_lower(sa_numbers)

        #RE RQ Number (e.g. RE|15H3CAE030)
        re_rq_number = self.re_rq_regex.matches(content)
        re_req_numbers = set()

        for i in range(len(re_rq_number)):
            if len(re_rq_number[i].children) > 2:
                extracted_val = str(re_rq_number[i].children[2]).replace('<','').split(':(', 1)       

                if len(extracted_val) > 0:
                    extracted_val = re.sub(r'^.*?RE', 'RE', extracted_val[0])
                    extracted_val = re.sub(r'^.*?RQ', 'RQ', extracted_val)
                    re_req_numbers.add(extracted_val)
        response['RE RQ Number'] = dedupe_lower(re_req_numbers)

        #DOI Number (e.g. 10.1080/15588742.2015.1017687)
        doi_number = self.doi_regex.matches(content)
        doi_numbers = set()
        for i in doi_number:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                doi_numbers.add(extracted_val[0])
        response['DOI Number'] = dedupe_lower(doi_numbers)

        #UUID (e.g. E95156F3-39BE-4734-9999-0DFAEE036BA6), may change later
        uuid = self.uuid_regex.matches(content)
        uuid_ids = set()
        for i in uuid:
            extracted_val = str(i).replace('<','').split(':(', 1)
            if len(extracted_val) > 0:
                uuid_ids.add(extracted_val[0])
        response['UUID'] = dedupe_lower(uuid_ids)

        #EPA Publication Number (e.g. EPA 430F10028, 200-B-96-001)
        epa_pub = self.epa_pub_regex.matches(content)
        epa_pubs = set()

        for i in range(len(epa_pub)):
            if len(epa_pub[i].children) > 2:
                extracted_val = str(epa_pub[i].children[2]).replace('<','').split(':(', 1)       

                if len(extracted_val) > 0:
                    epa_pubs.add(extracted_val[0])
        response['EPA Publication'] = dedupe_lower(epa_pubs)

        #Master Record Identification (MRID) Number (e.g. 48668800)
        mrid_number = self.mrid_regex.matches(content)
        mrid_numbers = set()
        for i in range(len(mrid_number)):
            extracted_val = str(mrid_number[i].children[2]).replace('<','').split(':(', 1)       

            if len(extracted_val) > 0:
                mrid_numbers.add(extracted_val[0])
        response['MRID Number'] = dedupe_lower(mrid_numbers)

        #EPA Special Local Needs Number (e.g. SD890001)
        sln_number = self.epa_sln_regex.matches(content)
        sln_numbers = set()
        for i in range(len(sln_number)):
            extracted_val = str(sln_number[i].children[2]).replace('<','').split(':(', 1)     

            if len(extracted_val) > 0:
                sln_numbers.add(extracted_val[0])
        response['EPA SLN Number'] = dedupe_lower(sln_numbers)

        # NARA Transfer Number e.g. PT-412-2022-0123
        transfer_numbers = set([x.value for x in self.nara_transfer_number_regex.matches(content)])
        response['NARA Transfer Number'] = list(transfer_numbers)

        # NARA Disposal Authority e.g. DAA-0412-2013-0008-0001 or DAA-GRS-2013-0008-0006 
        disposal_authorities = set([x.value for x in self.nara_disposal_authority_regex.matches(content)])
        response['NARA Disposal Authority'] = list(disposal_authorities)

        # Limit all identifier lists to a max of 5 items
        response = {k:v[:5] for k,v in response.items()}
        return response

    def extract_spatial_temporal(self, text):
        doc = self.nlp(text.replace("\r"," ").replace("\n"," ").replace("\r\n"," ").replace("\t"," ").replace("\s"," ").replace("  ", " "))
        spatial = self.extract_spatial_extent(doc)
        temporal = self.extract_temporal_extent(doc)
        return (spatial, temporal)
    
    #Method for checking if the word/location is valid
    def isValid(self, word):
        invalid_chars = ['/', '\\','-','–','—','<','>','@','\'','[',']',';',':','(',')',',','”','“','"','=','±','1','2','3','4','5','6','7','8','9','0','tmdl','‘','ï‚·']
        invalidLocSuffix = ['st.','st','street','rd.','rd','road','ave.','ave','blvd','dr.','dr', 'county', 'city', 'state']
        splitWord = word.split()    # splits to check the last word
        lastWord = splitWord[-1]    # if it's a street
        if not any(ext in word.lower() for ext in invalid_chars) and not lastWord.lower() in invalidLocSuffix:    # pass if no invalid chars/terms/suffix
            if len(difflib.get_close_matches(word, self.uscities_list, n=1, cutoff=0.72)) == 1:                  # compare loc to uscities
                return True
            elif len(word.split()) > 1: #only take location if not one word
                for x in self.water_list: #compare to water list
                    if x.lower() in word.lower():
                        return True
        else:
            return False
    
    def extract_spatial_extent(self, doc):
                        
        #list of valid locations
        valid_locations = []

        gpe = [] # countries, cities, states
        loc = [] # non gpe locations, mountain ranges, bodies of water
        final_loc = []

        for ent in doc.ents:
            if (ent.label_ == 'GPE'):
                gpe.append(ent.text.strip())
            elif (ent.label_ == 'LOC'):
                loc.append(ent.text.strip())

        gpe = list(set(gpe))
        loc = list(set(loc))

        joinedloc = gpe + loc

        # add valid locations from the joined spacy lists
        for i in joinedloc:
            if self.isValid(i.lower()):
                final_loc.append(i)

        # Filtered Loctions after stop words removal
        stop_words = set(stopwords.words('english'))
        for location in final_loc:
            word_tokens = word_tokenize(str(location))
            temploc = ""
            for w in word_tokens:   # turns current location segments into a string
                if w not in stop_words:
                    temploc += w + " "
            location_clean = temploc.strip() # temp location is cleaned by stripping
            if location_clean.lower() not in (loc.lower() for loc in valid_locations):  # adds location
                if self.isValid(location_clean.lower()):
                    valid_locations.append(location_clean)

        random.shuffle(valid_locations)
        return sorted(valid_locations[0:10])  # Filtered w/o Stop Words

    # takes date and retuns it if format is valid
    def cleanDate(self, text):
        # match regex day/month/year or month/day/year
        for date in re.findall(r'^\d{1,2}[.,/-]\d{1,2}[.,/-]\d{4}$',text):
            return date

        # match regex Year/month/day
        for date in re.findall(r'^\d{4}[.,/-]\d{1,2}[.,/-]\d{1,2}$',text):
            return date
            
        # match regex Text-Month/day/year
        for date in re.findall(r'\w+[.]?\s+\d{1,2}\w*\s*[,]?\s+\d{4}',text):
            return date 
    
    def localize_time(self, date):
        utc=pytz.utc
        eastern=pytz.timezone('US/Eastern')
        fmt='%Y-%m-%dT%H:%M:%S'

        new_date=datetime.strptime(date,"%Y-%m-%d")
        date_eastern=eastern.localize(new_date,is_dst=None)
        date_utc=date_eastern.astimezone(utc)
        return date_utc.strftime(fmt)+date_utc.strftime('.%f')[:4] + 'Z'

    def formatMeta(self, month, day, year, validDates):
        # YYYY-MM-DDTHH:mm:ss (Example: 2021-01-01T14:09:53)T00:00:00.000Z
        try:
            # If value = 0,0,0 then don't add to validDates
            if int(month) > 0 and int(day) > 0 and int(year) > 0:
                # If month > 12 switch month and day
                date_checker = True
                if(int(month) > 12):
                    date_str = str(year) + '-' + str(day) + '-' + str(month)
                    try:
                        date_checker = bool(datetime.strptime(date_str, '%Y-%d-%m'))
                    except ValueError:
                        date_checker = False
                    formattedDate = self.localize_time(date_str)
                else:
                    date_str = str(year) + '-' + str(month) + '-' + str(day)
                    try:
                        date_checker = bool(datetime.strptime(date_str, '%Y-%m-%d'))
                    except ValueError:
                        date_checker = False
                    formattedDate = self.localize_time(date_str)
                
                # Check to make sure date is not already in list and date is valid
                if not formattedDate in validDates and date_checker:
                    validDates.append(formattedDate)
        except:
            pass
    
     # parses the date in the parameter depending on format
    def parseDate(self, date, validDates):
        # Search for number format
        date_search = re.findall(r'[.,/-]', date)
        # Search for english format
        range_search = re.findall(r'\w+\s+\d{1,2}\s+\w+.+?(?=\d{1,2})\d{1,2}', date)

        #  Check to make sure all delimiters are the same
        if date_search and len(date_search) == 2 and len(set(date_search)) == 1:
            if re.findall(r'\d{4}[.,/-]\d{1,2}[.,/-]\d{1,2}',date):
                whole = re.split(r'[.,/-]', date)
                self.formatMeta(whole[1], whole[2], whole[0], validDates)
            else:
                whole = re.split(r'[.,/-]', date)
                self.formatMeta(whole[0], whole[1], whole[2], validDates)
        # Split Month day, year and remove ranges
        elif not range_search:
            try:
                # Removes periods/commas from date
                date = date.replace('.', '').replace(',', '').lower()
                months_list = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december', 'jan', 'feb', 'mar', 'apr', 'aug', 'sept', 'oct', 'nov', 'dec']
                
                # Remove suffixes from number e.g. 1st, 2nd, 3rd, 4th
                suffix_search = re.findall(r'\d{1,2}th|\d{1,2}st|\d{1,2}nd|\d{1,2}rd', date)
                if suffix_search:
                    date = re.sub(r'st|nd|rd|th', '', date)

                # Split words if 1 word in the months_list
                for x in months_list:
                    if not date.startswith(x):
                        if x in date.lower():
                            date = re.split("(" + x + ")", date)
                            date = date[1] + date[2]

                # Remove commas from date
                date = date.title()
                whole = date.split()
                month = list(calendar.month_abbr).index(str(whole[0][0:3]))
                self, self.formatMeta(month,int(whole[1]),int(whole[2]), validDates)
            except:
                self.formatMeta(0,0,0, validDates)
        else:
            self.formatMeta(0,0,0, validDates)

    def extract_temporal_extent(self, doc):
        # list of valid dates
        validDates = []

        # NLP date extraction
        extracted_dates = []
        for ent in doc.ents:
            if (ent.label_ == 'DATE'):
                temp_date = ent.text.strip()             # set a temp date
                if(temp_date not in extracted_dates):    # to check for dupliactes
                    extracted_dates.append(ent.text.strip())

        extracted_dates = list(set(extracted_dates))

        # date extraction clean
        for date in extracted_dates:
            clean_date = self.cleanDate(date)
            if clean_date != None:
                self.parseDate(clean_date, validDates)
        
        random.shuffle(validDates)
        return sorted(validDates[0:10])