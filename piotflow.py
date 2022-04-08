#!/usr/bin/python

import RPIO
import sys
from flowmeter import FlowMeter
import thread
import boto3
import requests
import threading
import json
import getopt
import time
from distutils.version import StrictVersion
import signal
import zipfile
from threading import Timer
import ciso8601

version = StrictVersion("1.2")

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

print "I'm using the '%s' certificate and '%s' key to get permissions from '%s'" % (certificate, private_key, iot_credentials_endpoint)

#Get access keys
creds = None
renew = None
iot = None
def get_credentials():
  global creds, renew, iot
  r = None
  connect_time = 0
  while not r and connect_time < 60:
    try:
      r = requests.get('https://%s:443/role-aliases/%s/credentials' % (iot_credentials_endpoint, role_alias),
                       cert=(certificate, private_key),
                       headers={'x-amzn-iot-thingname': my_name})
    except requests.exceptions.ConnectionError:
      time.sleep(5)
      connect_time += 5

  if not r:
    print "Failed to connect after 60 seconds. aborting. " + str(connect_time)
    sys.exit(1)

  if r.status_code != 200:
    print "Error getting permissions: " + str(r.status_code)
    sys.exit(1)

  creds = r.json()

  exp = time.mktime(ciso8601.parse_datetime(creds['credentials']['expiration']).timetuple())
  delay = exp - time.time() - 300
  print 'Current time is ' + str(time.time())
  print 'Credentials expire at ' + str(exp)
  print 'Renewing in ' + str(delay)
  renew = Timer(delay, get_credentials)
  renew.setDaemon(True)
  renew.start()

  iot = boto3.client('iot-data', endpoint_url=iot_data_endpoint,
                      aws_access_key_id=creds['credentials']['accessKeyId'],
                      aws_secret_access_key=creds['credentials']['secretAccessKey'],
                      aws_session_token=creds['credentials']['sessionToken'])


get_credentials()

#Get this device's flowmeter configurations from the cloud

dynamodb = boto3.client('dynamodb',
                        aws_access_key_id=creds['credentials']['accessKeyId'],
                        aws_secret_access_key=creds['credentials']['secretAccessKey'],
                        aws_session_token=creds['credentials']['sessionToken'])


item_response = dynamodb.get_item(TableName='devices',
                         Key={'device_id':{'S': my_name}})

print item_response

if not 'Item' in item_response:
  print "Device not found: " + my_name
  sys.exit(1)

item = item_response['Item']

#Check version
if not 'piotflow_version' in item:
  print 'No version info found'
else:
  latest_version = item['piotflow_version']['S']
  print latest_version
  if StrictVersion(latest_version) > version:
    print 'Downloading new version from ' + item['piotflow_url']['S']

    r = requests.get(item['piotflow_url']['S'], stream=True)
    #TODO: Avoid hardcoding this
    path = '/usr/sbin/piotflow/install.zip'
    with open(path, 'wb') as fd:
      for chunk in r.iter_content(chunk_size=300):
        fd.write(chunk)
      fd.flush()

    print 'Download complete. Extracting package.'
    zip_ref = zipfile.ZipFile(path, 'r')
    zip_ref.extractall('/usr/sbin/piotflow')
    zip_ref.close()

    print 'Package extracted. Exiting'
    sys.exit(2)

if not 'configuration' in item_response['Item']:
  print "No configuration for " + my_name
  sys.exit(1)


device_configs = json.loads(item_response['Item']['configuration']['S'])['flowmeters']
#[{'pin': 4, 'topic':flow_topic+"/0", 'id':my_name+"/0"},
#{'pin': 14, 'topic':flow_topic+"/1", 'id':my_name+"/1"},
#{'pin': 15, 'topic':flow_topic+"/2", 'id':my_name+"/2"}]


flowmeter_configs = {}

def flow_started(flowmeter):
    cfg = flowmeter_configs[flowmeter]
    #Nothing really needs to be done here
    print "Flow started on " + cfg['id']

def flow_update(flowmeter):
    #Ignore pulses emitted by the flowmeter for no reason
    if flowmeter.count > 2:
      message = b'{"flowmeter_id":"%s", "cumulative_flow":%d, "flowing":true}'%(cfg['id'], flowmeter.count)
      iot.publish(topic=cfg['topic'],
      qos=0, #We dont really need high QoS here as we'll be sending a bunch of updates
      payload=message)
      print "update: " + message

def flow_stopped(flowmeter):
    cfg = flowmeter_configs[flowmeter]
    message = b'{"flowmeter_id":"%s", "cumulative_flow":%d, "flowing":false}'%(cfg['id'], flowmeter.count)
    iot.publish(topic=cfg['topic'],
    qos=1, #Use a higher QoS since this essetially sets the next stable state. Maybe even QoS level 2 should be used.
    payload=message)
    print "Flow stopped: " + message

def monitor(flowmeter):
    cfg = flowmeter_configs[flowmeter]
    print "Monitoring " + cfg['id']
    flowmeter.monitor(flow_started, flow_update, flow_stopped)

#setup GPIO and flow meters
RPIO.setmode(RPIO.BCM)
threads = []
for cfg in device_configs:
    print "Setting up flowmeter %s on pin %d, publishing to %s" % (cfg['id'], cfg['pin'], cfg['topic'])
    RPIO.setup(cfg['pin'], RPIO.IN, pull_up_down=RPIO.PUD_UP)
    flowmeter = FlowMeter(cfg['pin'])
    flowmeter_configs[flowmeter] = cfg
    t = threading.Thread(target=monitor, args=(flowmeter,))
    threads.append(t)
    t.start()

running=True

# Setup reporting
reporter = None
def report():
  global reporter
  print "reporting"
  message = b'{"device_id":"%s"}'%(my_name)
  try:
    iot.publish(
      topic="report/" + my_name,
      qos=1, # Ensure delivery to avoid false alarms
      payload=message
    )
  except Exception as e:
    print e

  reporter = Timer(6*60*60, report) # Report every 6 hours
  reporter.setDaemon(True)
  reporter.start()

report()

def receive_signal(signum, stack):
    global running
    running = False
    print "Signal received. running is %s" % (str(running))

signal.signal(signal.SIGTERM, receive_signal)

try:
    while(running):
        time.sleep(5)
        #print "looping, running is %s" % (str(running))
    print "out of loop"
finally:
    print "stopping flowmeters"
    for flowmeter in flowmeter_configs:
        print "Stopping flowmeter on pin %s" % (flowmeter.pin)
        flowmeter.stop()
    print "Cleaning up GPIOs"
    RPIO.cleanup()
    if renew:
      renew.cancel()
    if reporter:
      reporter.cancel()
