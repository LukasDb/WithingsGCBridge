FROM python:3.10-alpine

# install dependencies
RUN pip install garminconnect pyyaml withings-api
RUN pip install flask

# copy script file

# mount volume?

# set entrypoint
CMD python

