from transformers import AutoTokenizer, AutoModelForSequenceClassification
from .data_classes import RecordSchedule, Recommendation
import numpy as np
import json
import threading

def softmax(logits):
    return np.exp(logits)/sum(np.exp(logits))

def format_record_schedule(sched):
    split = sched.split('-')
    return RecordSchedule(function_number=split[0], schedule_number=split[1], disposition_number=split[2])

class HuggingFaceModel():
    def __init__(self, model_path, label_mapping_path, office_info_mapping_path):
        self.lock = threading.Lock()
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        with open(label_mapping_path, 'r') as f:
            self.label_mapping = json.loads(f.read())
            self.reverse_mapping = {v:k for k,v in self.label_mapping.items()}
        with open(office_info_mapping_path, 'r') as g:
            self.office_info_mapping = json.loads(g.read())
        # Convert indices to record schedules using mapping saved at model training time
        self.classes = [format_record_schedule(self.reverse_mapping[x]) for x in range(len(self.label_mapping))]
        
    def predict(self, text, doc_type, prediction_metadata, k=3, default_categorization_threshold=0.95, valid_schedules=None):
        # Preprocess text to include metadata
        enhanced_text = text[:4000]
        if prediction_metadata is not None:
            if prediction_metadata.department is not None:
                group_name = prediction_metadata.department
                office_info = self.office_info_mapping.get(group_name, '')
                group_name = group_name + ' ' + office_info
            else:
                group_name = ''
            if prediction_metadata.file_name is not None:
                title = prediction_metadata.file_name
                if '.' in title:
                    extension = title.split('.')[-1]
                else:
                    extension = ''
            else:
                title = ''
                extension = ''
            enhanced_text = f'{group_name}, {title}, {doc_type}, {extension}, {enhanced_text}'
        # Tokenize text
        # thread lock tokenization https://github.com/huggingface/tokenizers/issues/537
        with self.lock:
            tokens = self.tokenizer(enhanced_text, truncation=True, padding=True, return_tensors="pt")
        # Apply model, get logits
        outputs = self.model(**tokens)
        preds = outputs[0][0].detach().cpu().numpy()
        # Convert logits to probabilities and select top k
        probs = [float(x) for x in list(softmax(preds))] 
        # Prepare response
        final_preds = [Recommendation(probability=probs[i], schedule = self.classes[i]) for i in range(len(self.label_mapping))]
        final_preds = sorted(final_preds, key=lambda x:-x.probability)
        if valid_schedules is not None:
            final_preds = list(filter(lambda x: "{fn}-{sn}-{dn}".format(fn=x.schedule.function_number, sn=x.schedule.schedule_number, dn=x.schedule.disposition_number) in valid_schedules, final_preds))
        filtered_preds = final_preds[0:k]
        # Automatically categorize if top prediction exceeds threshold
        default_schedule = None
        highest_pred = filtered_preds[0]
        if highest_pred.probability > default_categorization_threshold:
            default_schedule = highest_pred.schedule
        return filtered_preds, default_schedule