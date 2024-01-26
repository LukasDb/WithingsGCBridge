FROM python:3.10-alpine

RUN apk update
RUN apk add git

# install dependencies
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# copy script file
COPY ./main.py /app/main.py

WORKDIR /app

# set entrypoint
ENTRYPOINT [ "python", "main.py"]
