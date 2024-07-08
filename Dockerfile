FROM python:3.11.9-slim
ENV WORKDIR=/code
RUN (apt-get update | :) \
    && apt-get -y install bind9-dnsutils

WORKDIR $WORKDIR
COPY ./requirements.txt $WORKDIR/requirements.txt
RUN pip install --no-cache-dir --upgrade -r $WORKDIR/requirements.txt
COPY *.py *.json $WORKDIR/app/
CMD ["python", "./app/dyndns_upd_ip.py"]