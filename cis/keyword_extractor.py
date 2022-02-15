import re
import marisa_trie
from rebulk import Rebulk

class KeywordExtractor():
    def __init__(self, vocab_path, priority_categories_path):
        self.pattern = re.compile("[\\(\\).!?\\-\n]")
        with open(vocab_path, 'r') as f:
            mapping = f.read().splitlines()
            self.keyword_mapping = {x.split(',')[0].replace('"',''):','.join(x.split(',')[1:]).replace('"','') for x in mapping}
        with open(priority_categories_path, 'r') as f:
            self.priority_categories = f.read().splitlines()
        lower_list = [' ' + x.lower().strip() + ' ' for x in self.keyword_mapping.keys()]
        self.trie = marisa_trie.Trie(lower_list)
        self.max_length = max([len(x) for x in lower_list])
        self.facility_regex = Rebulk().regex(r'\b110\d{9}\b')
        self.tri_regex = Rebulk().regex(r'\b\d{5}[B-DF-HJ-NP-TV-Z0-9]{10}\b')
        self.docket_regex = Rebulk().regex(r'\bEPA-([a-zA-Z0-9]{2,3})-([a-zA-Z]{2,5})-\d{4}-\d{4}-\d{4}\b')
        self.cas_regex = Rebulk().regex(r'\b\d{2,7}-\d{2}-\d{1}\b')
        self.inchi_regex = Rebulk().regex(r'\b([A-Z0-9]{14})-([A-Z0-9]{10})-([A-Z0-9]{1})\b')
        self.dsstox_regex = Rebulk().regex(r'\bDTXSIDd{7,9}\b')
        self.srs_regex = Rebulk().regex(r'(?i)\b(srs|srs id|internal tracking number)\s?\b\d{1,100}\b')
        self.naics_regex = Rebulk().regex(r'(?i)\b(naics|naics code|naics no|naics num|niacs no|naics no\.|naics \#)\s?([ ]|[:]|[\-])\s?\b\d{5,6}\b')
        self.sic_regex = Rebulk().regex(r'(?i)\b(sic|sic code|sic no|sic num|sic no|sic no\.|sic \#)\s?([ ]|[:]|[\-])\s?\b\d{4}\b')
        self.duns_regex = Rebulk().regex(r'0([0-9]{1})-([0-9]{3})-([0-9]{4})').regex(r'0([0-9]{8})0000').regex(r'(?i)\b(duns|duns no|duns num|duns no|duns no\.|duns \#)\s?([ ]|[:]|[\-])\s?\b\d{8}\b')
        self.cfda_regex = Rebulk().regex(r'(?i)\b(cfda|cfda code|cfda no|cfda num|cfda no\.|cfda \#)\s?([ ]|[:]|[\-])\s?\b\d+.\d{0,3}\b')
        self.bia_regex = Rebulk().regex(r'(?i)\b(tribal code|bia|bia tribal code|bia code|bia num|bia no|bia no\.|bia \#)\s?([ ]|[:]|[\-])\s?\b(\d{3}|[A]\d{0,2})\b').regex(r'(?i)\b(tribal code|bia|bia tribal code|bia code|bia num|bia no\.|bia \#)\s?([ ]|[:]|[\-])\s?[A]\b(\d{3}|[A]\d{0,2})\b')
        self.epa_reg_regex = Rebulk().regex(r'(?i)\b(epa registration no\.|epa reg\. no\.)\s?([ ]|[:]|[\-])\s?\b\d{0,4}-\d{0,4}(?:-\d{0,4})?\b')
        self.epa_est_regex = Rebulk().regex(r'(?i)\b(epa est\. no\.|epa est\.)\s?([ ]|[:]|[\-])\s?\b\d{0,4}-[A-Z]{2}-\d{0,4}\b')
        self.huc_regex = Rebulk().regex(r'(?i)\b(huc|hydrologic unit code)\s?([ ]|[:]|[\-])\s?\b(?:[0-9]{2,12})*\b')
        self.npdes_regex = Rebulk().regex(r'(\b[a-zA-z]{2}\d{7}\b)|(\b[a-zA-Z]{3}\d{6}\b)')
        self.sems_regex = Rebulk().regex(r'\b[a-zA-z]{3}\d{9}\b')
        self.contract_regex = Rebulk().regex(r'(?i)\b(contract number|contract num|contract no|contract no\.|contract \#)\s?([ ]|[:]|[\-])\s?\b[A-Z0-9]{8,14}\b')
        self.ebusiness_regex = Rebulk().regex(r'(?i)\b(registration id|ebusiness registration id)\s?([ ]|[:]|[\-])\s?\bR[A-Z0-9]{7}\b')
        self.pr_regex = Rebulk().regex(r'\bPR\d{8}\b')
        self.sa_regex = Rebulk().regex(r'(?i)\b(sa|service account|sa no|sa no\.|sa \#)\s?([ ]|[:]|[\-])\s?\b\d{2}[A-Z0-9]{9}\b')
        self.re_rq_regex = Rebulk().regex(r'(?i)\b(re|re no|re no\.|re \#|rq|rq no|rq no\.|rq \#)\s?\b([ ]|[:]|[-])s?(RQ|RE)([|])?[A-Z0-9]{1,10}\b')
        #self.doi_regex = Rebulk().regex(r'\b10.(\d+.*)+[/](([^s.])+.*)+\b')
        self.edg_regex = Rebulk().regex(r'\b[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\b')
        self.epa_pub_regex = Rebulk().regex(r'\b\d{3}-[a-zA-z]-\d{2}-\d{3}\b').regex(r'(?i)\b(epa|epa publication|epa publication number|epa publication num|epa publication no|epa publication no\.|epa publication \#)\s?([ ]|[:]|[\-])\s?\d{3}[a-zA-z]\d{5}')
        
    def extract_keywords(self, text):
        all_matches = set()
        sub_doc = re.sub(self.pattern, " ", " " + text + " ").lower()
        for i in range(len(sub_doc)):
            if sub_doc[i] == ' ':
                check_text = sub_doc[i:(i + self.max_length)]
                matches = self.trie.prefixes(check_text)
                if len(matches) > 0:
                    for match in matches:
                        all_matches.add(match[1:-1])
        return list(sorted(list(all_matches)))
    
    def extract_identifiers(self, text):
        content = text[:1000000]
        response = {}

        facility_id = self.facility_regex.matches(content)
        facility_ids = set()        
        for i in facility_id:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                facility_ids.add(extracted_val)
        response['Facility ID'] = list(facility_ids)

        #TRI Facility ID (e.g. 90058GSSRL2618F)
        tri_id = self.tri_regex.matches(content)
        tri_ids = set()
        for i in tri_id:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                tri_ids.add(extracted_val)
        response['TRI Facility ID'] = list(tri_ids)

        #Docket ID (e.g. EPA-HQ-OPP-2014-0483-0001)
        docket_id = self.docket_regex.matches(content)
        docket_ids = set()
        for i in docket_id:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                docket_ids.add(extracted_val)
        response['Docket ID'] = list(docket_ids)
                
        #SUBSTANCES
        #CAS Number (e.g. 11121-31-6)
        cas_num = self.cas_regex.matches(content)
        cas_nums = set()
        for i in cas_num:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                cas_nums.add(extracted_val)
        response['CAS Number'] = list(cas_nums)

        #International Chemical Identifier Key (e.g. FBMORZZOJSDNRQ-GLQYFDAESA-N)
        inchikey = self.inchi_regex.matches(content)
        inchis = set()
        for i in inchikey:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                inchis.add(extracted_val)
        response['InChI Key'] = list(inchis)

        #DSSTox ID (e.g. DTXSID6020014)
        dsstox = self.dsstox_regex.matches(content)
        dsstox_ids = set()
        for i in dsstox:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                dsstox_ids.add(extracted_val)
        response['DSSTox ID'] = list(dsstox_ids)

        #SRS ID (e.g. 1736818)
        srs = self.srs_regex.matches(content)
        srs_ids = set()
        for i in srs:
            extracted_val = re.sub('\D', '', str(i).replace('<','').split(':(', 1)[0])
            if extracted_val:
                srs_ids.add(extracted_val)
        response['SRS'] = list(srs_ids)
                                
        #NAICS Code (e.g. NAICS 311221)
        naics = self.naics_regex.matches(content)
        naics_ids = set()
        for i in naics:
            extracted_val = re.findall('\d{5,6}', str(i))[0]
            if extracted_val:
                naics_ids.add(extracted_val)
        response['NAICS'] = list(naics_ids)

        #SIC Code (e.g. SIC 311221)
        sic = self.sic_regex.matches(content)
        sic_ids = set()
        for i in sic:
            extracted_val = re.findall('\d{4}', str(i))[0]
            if extracted_val:
                sic_ids.add(extracted_val)
        response['SIC'] = list(sic_ids)
        
        #DUNS Number (e.g. 02-507-5342)
        duns = self.duns_regex.matches(content)
        duns_ids = set()
        for i in duns:
            if re.search('[a-zA-Z]', str(i)):
                extracted_val = re.findall('\d{8}', str(i))[0]
            else:
                extracted_val = str(i).replace('<','').split(':(', 1)[0]

            if extracted_val:
                duns_ids.add(extracted_val)
        response['DUNS'] = list(duns_ids)
                
        #CFDA Number for Grants (e.g. CFDA 10.001)
        cfda = self.cfda_regex.matches(content)
        cfda_ids = set()
        for i in cfda:
            extracted_val = re.findall('\d+\.\d{0,3}', str(i))[0]
            if extracted_val:
                cfda_ids.add(extracted_val)
        response['CFDA'] = list(cfda_ids)

        #BIA Tribal Code for Grants (e.g. BIA A10)
        bia = self.bia_regex.matches(content)
        bia_ids = set()
        for i in bia:
            extracted_val = str(i).split(':(')[0][-3:]
            
            if extracted_val:
                bia_ids.add(extracted_val)
        response['BIA'] = list(bia_ids)

        #EPA Registration Number (e.g. EPA Reg. No. 3120-280-1492)
        epa_reg_number = self.epa_reg_regex.matches(content)
        epa_reg_ids = set()
        for i in epa_reg_number:
            extracted_val = re.findall('\d{0,4}-\d{0,4}(?:-\d{0,4})?', str(i))[0]
            if extracted_val:
                epa_reg_ids.add(extracted_val)
        response['EPA Registration Number'] = list(epa_reg_ids)

        #EPA Establishment Number (e.g. EPA Est. No. 264-MO-02)
        epa_est_number = self.epa_est_regex.matches(content)
        epa_est_ids = set()
        for i in epa_est_number:
            extracted_val = re.findall('\d{0,4}-[A-Z]{2}-\d{0,4}', str(i))[0]
            if extracted_val:
                epa_est_ids.add(extracted_val)
        response['EPA Establishment Number'] = list(epa_est_ids)

        #Hydrologic Unit Codes (HUCs) (e.g. 180902030303)
        huc = self.huc_regex.matches(content)
        huc_ids = set()
        for i in huc:
            extracted_val = re.sub('\D', '', str(i).replace('<','').split(':(', 1)[0])
            if extracted_val:
                huc_ids.add(extracted_val)
        response['HUC'] = list(huc_ids)
        
        # NPDES Permit No. (e.g. GUS040001, GU0020371)
        npdes_id = self.npdes_regex.matches(content)
        npdes_ids = set()
        for i in npdes_id:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                npdes_ids.add(extracted_val)
        response['NPDES Permit No.'] = list(npdes_ids)
                
        # SEMS EPA ID (CERCLA ID?) e.g. MAD001026319
        sems_epa_id = self.sems_regex.matches(content)
        sems_ids = set()
        for i in sems_epa_id:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                sems_ids.add(extracted_val)
        response['SEMS EPA ID'] = list(sems_ids)

        #FINANCE
        #EPA Contact Number (e.g. EPC07058)
        epa_contract_number = self.contract_regex.matches(content)
        contract_numbers = set()
        for i in epa_contract_number:
            extracted_val = re.findall('[A-Z0-9]{8,14}', str(i))[0]
            if extracted_val:
                contract_numbers.add(extracted_val)
        response['EPA Contract Number'] = list(contract_numbers)

        #ebusiness Registration ID (e.g. R0499360)
        registration_id = self.ebusiness_regex.matches(content)
        reg_ids = set()
        for i in registration_id:
            extracted_val = re.findall('R[A-Z0-9]{7}', str(i))[0]
            if extracted_val:
                reg_ids.add(extracted_val)
        response['eBusiness Registration ID'] = list(reg_ids)

        #PR Number (e.g. PR00013635)
        pr_number = self.pr_regex.matches(content)
        pr_numbers = set()
        for i in pr_number:
            extracted_val = re.findall('PR\d{8}', str(i))[0]
            if extracted_val:
                pr_numbers.add(extracted_val)
        response['PR Number'] = list(pr_numbers)

        #Service Account Number (e.g. 22DPEHSTRAT)
        sa_number = self.sa_regex.matches(content)
        sa_numbers = set()

        for i in sa_number:
            extracted_val = re.findall('\d{2}[A-Z0-9]{9}', str(i))[0]
            if extracted_val:
                sa_numbers.add(extracted_val)
        response['SA Number'] = list(sa_numbers)

        #RE RQ Number (e.g. RE|15H3CAE030)
        re_rq_number = self.re_rq_regex.matches(content)
        re_req_numbers = set()
        for i in re_rq_number:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                extracted_val = re.sub(r'^.*?RE', 'RE', extracted_val)
                extracted_val = re.sub(r'^.*?RQ', 'RQ', extracted_val)
                re_req_numbers.add(extracted_val)
        response['RE RQ Number'] = list(re_req_numbers)

        #DOI Number (e.g. 10.1080/15588742.2015.1017687)
        #doi_number = self.doi_regex.matches(content)
        #doi_numbers = set()
        #for i in doi_number:
        #    extracted_val = str(i).replace('<','').split(':(', 1)[0]
        #    if extracted_val:
        #        doi_numbers.add(extracted_val)
        #response['DOI Number'] = list(doi_numbers)

        #EDG UUID (e.g. E95156F3-39BE-4734-9999-0DFAEE036BA6), may change later
        uuid = self.edg_regex.matches(content)
        edg_ids = set()
        for i in uuid:
            extracted_val = str(i).replace('<','').split(':(', 1)[0]
            if extracted_val:
                edg_ids.add(extracted_val)
        response['EDG UUID'] = list(edg_ids)

            #EPA Publication Number (e.g. EPA 430F10028, 200-B-96-001)
        epa_pub = self.epa_pub_regex.matches(content)
        epa_pubs = set()
        for i in epa_pub:
            if re.search('[-]', str(i)):
                extracted_val = str(i).replace('<','').split(':(', 1)[0]
            else:
                extracted_val = str(i).split(':(')[0][-9:]
            if extracted_val:
                epa_pubs.add(extracted_val)
        response['EPA Publication'] = list(epa_pubs)

        return response

    def extract_subjects(self, text, num_top_cats=5):
        keywords = self.extract_keywords(text)
        subjects = {}
        for keyword in keywords:
            if keyword in self.keyword_mapping:
                subject = self.keyword_mapping[keyword]
                if subject in subjects:
                    subjects[subject] += 1
                else:
                    subjects[subject] = 1

        top_cats = set([x[0] for x in sorted(subjects.items(), key = lambda x: x[1], reverse = True)[:num_top_cats]])
        for p in self.priority_categories:
            if p in subjects and subjects[p] >= 3:
                top_cats.add(p)
        return list(top_cats)