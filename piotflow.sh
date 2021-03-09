#! /bin/bash

IOT_ENDPOINT= #AWS IoT endpoint (with https://)
IOT_CREDENTIALS_ENDPOINT= # AWS IoT credentials endpoint (no https://)
IOT_ROLE= #AWS IoT role alias
CERTIFICATE= # Path to device crt file
PRIVATE_KEY= # Path to device private key file 

cd /usr/sbin/piotflow
python -u piotflow.py -i $IOT_ENDPOINT -e $IOT_CREDENTIALS_ENDPOINT -r $IOT_ROLE -c $CERTIFICATE -p $PRIVATE_KEY
