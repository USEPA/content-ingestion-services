import re
import json
from rebulk import Rebulk
import csv
import ahocorasick

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
    def __init__(self):
        self.facility_regex = Rebulk().regex(r'\b110\d{9}\b')
        self.tri_regex = Rebulk().regex(r'\b\d{5}[B-DF-HJ-NP-TV-Z0-9]{10}\b')
        self.docket_regex = Rebulk().regex(r'\bEPA-([a-zA-Z0-9]{2,3})-([a-zA-Z]{2,5})-\d{4}-\d{4}-\d{4}\b')
        self.cas_regex = Rebulk().regex(r'\b\d{2,7}-\d{2}-\d{1}\b')
        self.inchi_regex = Rebulk().regex(r'\b([A-Z0-9]{14})-([A-Z0-9]{10})-([A-Z0-9]{1})\b')
        self.dsstox_regex = Rebulk().regex(r'\bDTXSIDd{7,9}\b')
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

        # Limit all identifier lists to a max of 3 items
        response = {k:v[:3] for k,v in response.items()}
        return response