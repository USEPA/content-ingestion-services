import torch
import os
import numpy as np
import random 
import json
from transformers import AutoTokenizer, AutoModelForSequenceClassification , Trainer, TrainingArguments

def get_training_data(base_dir="/home/ubuntu/train_split", text_length=4000):
    train_texts = []
    train_labels = []
    label_counts = {}
    for subdir, dirs, files in os.walk(base_dir):
        label = subdir.split(r"/")[-1]
        for f in files:
            if label not in label_counts:
                label_counts[label] = 1
            else:
                label_counts[label] += 1
            if f.split('.')[-1] == 'txt':
                path = os.path.join(subdir, f)
                text = ""
                with open(path, 'r', encoding="utf-8") as r:
                    text = r.read()[:text_length]
                train_texts.append(text)
                train_labels.append(label)
    label_counts = {k: v for k, v in sorted(label_counts.items(), key=lambda item: -item[1])}

    return train_texts, train_labels, label_counts

train_texts, train_labels, label_counts = get_training_data()
test_texts, test_labels, test_label_counts = get_training_data('/home/ubuntu/test_split')

zipped = list(zip(train_texts, train_labels))
random.shuffle(zipped)
train_texts = [x[0] for x in zipped]
train_labels = [x[1] for x in zipped]

tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased", use_fast=True)
train_encodings = tokenizer(train_texts, truncation=True, padding=True)
test_encodings = tokenizer(test_texts, truncation=True, padding=True)

with open('label_mapping.json', 'r') as f:
    label_mapping = json.loads(f.read())
reverse_mapping = {v:k for k,v in label_mapping.items()}

encoded_train_labels = [0 for x in train_labels]
encoded_test_labels = [0 for x in test_labels]
for i in range(len(train_labels)):
    encoded_train_labels[i] = label_mapping[train_labels[i]]
for i in range(len(test_labels)):
    encoded_test_labels[i] = label_mapping[test_labels[i]]

class RecordsDataset(torch.utils.data.Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __getitem__(self, idx):
        item = {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
        item['labels'] = torch.tensor(self.labels[idx])
        return item

    def __len__(self):
        return len(self.labels)

train_dataset = RecordsDataset(train_encodings, encoded_train_labels)
test_dataset = RecordsDataset(test_encodings, encoded_test_labels)

model = AutoModelForSequenceClassification.from_pretrained("distilbert-base-uncased", num_labels=len(label_mapping))

def top_k_accuracy(true_labels, predictions, k=3):
    ind = np.argpartition(predictions, -k, axis=1)[:,-k:]
    top_k_match = [(true_labels[i] in ind[i]) for i in range(len(true_labels))]
    return np.mean(top_k_match)

def compute_metrics(eval_pred):
    preds = eval_pred.predictions
    labels = eval_pred.label_ids
    return {'top_1_accuracy': top_k_accuracy(labels, preds, k=1), 'top_3_accuracy': top_k_accuracy(labels, preds, k=3),'top_5_accuracy': top_k_accuracy(labels, preds, k=5)}

training_args = TrainingArguments(
    output_dir='./auto_distilbert',          # output directory
    num_train_epochs=10,              # total number of training epochs
    per_device_train_batch_size=16,  # batch size per device during training
    per_device_eval_batch_size=128,   # batch size for evaluation
    warmup_steps=500,                # number of warmup steps for learning rate scheduler
    weight_decay=0.01,               # strength of weight decay
    logging_dir='./logs',            # directory for storing logs
    logging_steps=100,
    save_steps=3000,
    load_best_model_at_end=True,
    metric_for_best_model='top_1_accuracy'
)

trainer = Trainer(
    model=model,                         # the instantiated 🤗 Transformers model to be trained
    args=training_args,                  # training arguments, defined above
    train_dataset=train_dataset,         # training dataset
    eval_dataset=test_dataset,            # evaluation dataset
    compute_metrics = compute_metrics
)

trainer.train()
trainer.save_model('distilbert_10_epochs')
_eval = trainer.evaluate()
with open('distilbert_final_eval.json', 'w') as f:
    f.write(json.dumps(_eval))
print("DONE")
