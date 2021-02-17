from python:3.9

# Install requirements
COPY requirements.txt /home/requirements.txt
RUN pip install -r /home/requirements.txt 

# Copy code, models, config
COPY cis /home/cis
COPY models /home/models
COPY dev_config.json /home/config.json 
COPY swagger.yaml /home/swagger.yaml 

# Run server
ENTRYPOINT cd /home && python cis/cis_server.py --model_path /home/models/distilbert-12-10 --label_mapping_path /home/models/label_mapping.json --config_path /home/config.json