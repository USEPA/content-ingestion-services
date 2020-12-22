from transformers import AutoTokenizer, AutoModelForSequenceClassification
import numpy as np
import json

def softmax(logits):
    return np.exp(logits)/sum(np.exp(logits))

class HuggingFaceModel():
    def __init__(self, model_path, label_mapping_path):
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        with open(label_mapping_path, 'r') as f:
            self.label_mapping = json.loads(f.read())
            self.reverse_mapping = {v:k for k,v in self.label_mapping.items()}
        
    def predict(self, text, k=3):
        # Tokenize text
        tokens = self.tokenizer(text, truncation=True, padding=True, return_tensors="pt")
        # Apply model, get logits
        outputs = self.model(**tokens)
        preds = outputs[0][0].detach().cpu().numpy()
        # Find indices of the highest k predictions
        ind = list(np.argpartition(preds, -k)[-k:])
        # Convert logits to probabilities and select top k
        probs = softmax(preds)
        selected_probs = list(probs[ind])
        selected_probs = [float(x) for x in selected_probs]
        # Convert indices to record schedules using mapping saved at model training time
        classes = [self.reverse_mapping[x] for x in ind]
        # Prepare response
        final_preds = [{'probability': selected_probs[i], 'schedule': classes[i]} for i in range(k)]
        final_preds = sorted(final_preds, key=lambda x:-x['probability'])
        return final_preds