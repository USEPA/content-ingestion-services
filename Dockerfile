from python:3.9

# Install requirements
COPY requirements.txt /home/requirements.txt
RUN pip install -r /home/requirements.txt 

# Copy code, models, config
COPY . /home
COPY dev_config.json /home/config.json
COPY cis/test.db /home/favorites.db
WORKDIR /home

# Run server
ENTRYPOINT python wsgi.py --model_path /home/models/distilbert-12-10 --label_mapping_path /home/models/label_mapping.json --config_path /home/config.json --upgrade --database_uri sqlite:////home/favorites.db