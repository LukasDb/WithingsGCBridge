FROM python:3.10-alpine

# install dependencies
RUN pip install garminconnect pyyaml withings-api
RUN pip install flask

# copy script file
COPY ./main.py /app/main.py

WORKDIR /app

# set entrypoint
ENTRYPOINT [ "python", "main.py"]
