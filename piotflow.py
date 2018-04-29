import RPi.GPIO as GPIO
import sys
from flowmeter import FlowMeter
import thread
import boto3
import requests
import json
import getopt

def get_serial():
  # Extract serial from cpuinfo file
  cpuserial = "0000000000000000"
  try:
    f = open('/proc/cpuinfo','r')
    for line in f:
      if line[0:6]=='Serial':
        cpuserial = line[10:26]
    f.close()
  except e:
    print e
    cpuserial = None
 
  return cpuserial



my_name = get_serial()

if my_name is None:
    sys.exit(1)

print "Hi! My name is " + my_name

iot_data_endpoint = ''
iot_credentials_endpoint = ''
role_alias = ''
certificate = ''
private_key = ''
try:
    opts, args = getopt.getopt(sys.argv[1:], "hi:e:r:c:p:", ["iot_endpoint=", "credentials_endpoint=", "role_alias=", "certificate=", "private_key="])
except getopt.GetoptError:
    print 'piotflow.py -i <iot endpoint> -e <iot data endpoint> -r <role alias> -c <certificate file> -p <private key file>'
    sys.exit(2)
for opt, arg in opts:
    if opt == '-h':
        print 'piotflow.py -i <iot endpoint> -e <iot data endpoint> -r <role alias> -c <certificate file> -p <private key file>'
        sys.exit()
    elif opt in ("-i", "--iot_endpoint"):
        iot_data_endpoint = arg
    elif opt in ("-e", "--credentials_endpoint"):
        iot_credentials_endpoint = arg
    elif opt in ("-r", "--role_alias"):
        role_alias = arg
    elif opt in ("-c", "--certificate"):
        certificate = arg
    elif opt in ("-p", "--private_key"):
        private_key = arg

#TODO make sure all arguments are there
#TODO read table name from command line
#TODO get data endpoint from cloud
#TODO get root topic from cloud

print "I'm using the '%s' certificate and '%s' key to get permissions from '%s'" % (certificate, private_key, iot_credentials_endpoint)

#Get this device's registered flowmeter configurations from the cloud
r = requests.get('https://%s:443/role-aliases/%s/credentials' % (iot_credentials_endpoint, role_alias),
                 cert=(certificate, private_key),
                 headers={'x-amzn-iot-thingname': my_name})

#TODO: validate response code
creds = r.json()
dynamodb = boto3.client('dynamodb',
                        aws_access_key_id=creds['credentials']['accessKeyId'],
                        aws_secret_access_key=creds['credentials']['secretAccessKey'],
                        aws_session_token=creds['credentials']['sessionToken'])


item = dynamodb.get_item(TableName='devices',
                         Key={'device_id':{'S': my_name}})
#TODO validate
print item


#TODO actually use device config for pin
#TODO support n flow meters


#setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)

#setup AWS IOT

iot = boto3.client('iot-data', endpoint_url=iot_data_endpoint)

#TODO: Think about topic naming, or look into using device shadow
flow_topic = 'flow'

def flow_started(flowmeter):
    #Nothing really needs to be done here
    print "Flow started"

def flow_update(flowmeter):
    message = b'{"flowmeter_id":"%s/0", "cumulative_flow":%d, "flowing":true}'%(my_name, flowmeter.count)
    iot.publish(topic=flow_topic,
    qos=0, #We dont really need high QoS here as we'll be sending a bunch of updates 
    payload=message)
    print "update: " + message

def flow_stopped(flowmeter):
    message = b'{"flowmeter_id":"%s/0", "cumulative_flow":%d, "flowing":false}'%(my_name, flowmeter.count)
    iot.publish(topic=flow_topic,
    qos=1, #Use a higher QoS since this essetially sets the next stable state. Maybe even QoS level 2 should be used. 
    payload=message)
    print "Flow stopped: " + message


flowmeter = FlowMeter(4)

try:
    print "Monitoring..."
    flowmeter.monitor(flow_started, flow_update, flow_stopped)
finally:
    GPIO.cleanup()
