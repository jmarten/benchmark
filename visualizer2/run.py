#!/usr/bin/env python
import SimpleHTTPServer
import BaseHTTPServer
import SocketServer
import json
import os
import pandas as pd
import math
import numpy as np
from functools import partial
import os.path, time
import cherrypy
import random
from subprocess import call
import requests
import psutil
import commands

#dict of tuples of result file and event file.
#event file is None if no events should be displayed
AB_LOGS = {
    # 'NVRAM': ('../results/recovery_demo/{}/NVRAM/ab.log', None),
    # 'Logger': ('../results/recovery_demo/{}/Logger/ab.log', None),
    #'MasterWrites': ('./ab_writes.log', "./events_master.json"),
    #'Reads': ('./ab_reads.log', "./events_reads.json")
}

def readlog(logfilename):
    try:
        with open(logfilename) as f:
            content = f.readlines()
            return content
    except:
        return ""

def create_json_from_ab(logfilename):
    start_time = time.time()
    jsonstring = ""
    fname = AB_LOGS[logfilename][0]

    if not os.path.isfile(fname):
        # print "ab log not found " + fname
        return

    df = pd.read_csv(fname, sep="\t", engine='c', usecols=['seconds', 'status'], dtype={
        'seconds': np.uint64,
        'status': np.uint64,
    })

    df = df[df.status == 200]
    if df.seconds.max() > 1008914214395976:
        df = df[df.seconds > 1008914214395976] # filter out the crap
    
    if math.isnan(df.seconds.max()):
        print "no valid data found " + fname
        print "max seconds: ", df.seconds.max()
        return

    start_timestamp = int(df.seconds.min())
    df.seconds -= start_timestamp

    df.seconds /= 1e6
    df.seconds = np.round(df.seconds, 1)
    
    df = df.status.groupby(df.seconds).agg('count')

    df = df.head(len(df.index)-10)
    df = df * 10 # normalize to seconds

    jsonstring += '{"data":'
    jsonstring += df.to_json()
    jsonstring += ', "events":'

    eventfile = AB_LOGS[logfilename][1]
    if os.path.isfile(eventfile):
        with open(eventfile) as f:
            events = json.load(f)
        events_normalized = {}
        for k, v in events.iteritems():
            print int(k.replace('.',''))
            print start_timestamp
            events_normalized[(int(k.replace('.',''))-start_timestamp)/1e6] = v
        jsonstring += json.dumps(events_normalized)
    else:
        jsonstring += '[]'
    jsonstring += '}'               

    # print str(time.time() - start_time) + " elapsed"
    return jsonstring

class MyServerHandler(object):
    @cherrypy.expose
    def index(self):
        with open("replication.html") as f:
            content = f.readlines()
            return content
    
    @cherrypy.expose
    def log1(self):
        return readlog("log1.txt")
        
    @cherrypy.expose
    def log2(self):
        return readlog("log2.txt")
    
    @cherrypy.expose
    def log3(self):
        return readlog("log3.txt")
    
    @cherrypy.expose
    def log4(self):
        return readlog("log4.txt")

    @cherrypy.expose
    def delay(self):
        payload = {'query': '{"operators": {"0": {"type": "ClusterMetaData"} } }'}
        r = requests.post("http://localhost:6666/delay", data=payload)
        return r.text

    @cherrypy.expose
    def load(self):
        l = psutil.cpu_percent(interval=0, percpu=True)
        return """{"0": [%d, %d, %d, %d, %d, %d, %d, %d], "1": [%d, %d, %d, %d, %d, %d, %d, %d], "2": [%d, %d, %d, %d, %d, %d, %d, %d], "3": [%d, %d, %d, %d, %d, %d, %d, %d] }""" % (l[0], l[2], l[4], l[6], l[8], l[10], l[12], l[14], l[20], l[22], l[24], l[26], l[28], l[30], l[32], l[34], l[40], l[42], l[44], l[46], l[48], l[50], l[52], l[54], l[60], l[62], l[64], l[66], l[68], l[70], l[72], l[74] )

    # @cherrypy.expose
    # def MasterWrites(self):
    #     return create_json_from_ab("MasterWrites")

    # @cherrypy.expose
    # def Reads(self):
    #     return create_json_from_ab("Reads")

    @cherrypy.expose
    def QueryData(self):
        payload = {'data':0}
        r = requests.post("http://localhost:6666/statistics", data=payload, stream=True)
        return '{"data":' + r.text + '}' 

    @cherrypy.expose
    def NVRAM(self):
        return create_json_from_ab("NVRAM")

    @cherrypy.expose
    def Logger(self):
        return create_json_from_ab("Logger")

    @cherrypy.expose
    def builds(self):
        return json.dumps(AB_LOGS.keys())

    @cherrypy.expose
    def startserver(self):
        call(["bash", "start.sh"])
        return ""

    @cherrypy.expose
    def killmaster(self):
        call(["bash", "killmaster.sh"])
        return ""

    @cherrypy.expose
    def killall(self):
        call(["bash", "end.sh"])
        return ""

    @cherrypy.expose
    def startworkload(self, num_write, num_read):
        call(["bash", "workload_start.sh", num_write, num_read])
        return ""

    @cherrypy.expose
    def stopworkload(self):
        call(["bash", "workload_end.sh"])
        return ""

    @cherrypy.expose
    def useonereplica(self):
        payload = {"data":0}
        r = requests.post("http://localhost:6666/number_of_slaves_1", data=payload)
        return r.text

    @cherrypy.expose
    def usetworeplica(self):
        payload = {"data":0}
        r = requests.post("http://localhost:6666/number_of_slaves_2", data=payload)
        return r.text

    @cherrypy.expose
    def usethreereplica(self):
        payload = {"data":0}
        r = requests.post("http://localhost:6666/number_of_slaves_3", data=payload)
        return r.text

    @cherrypy.expose
    def statusInst1(self):
        if commands.getstatusoutput('ps aux | grep [h]yrise-server_release | grep "5000" | wc -l')[1] == '1':
            return "Running, Master"
        else:
            opensockets = commands.getstatusoutput("netstat | grep 6666 | wc -l")[1]
            startsh = commands.getstatusoutput("ps aux | grep start.sh | grep -v grep | wc -l")[1]
            if opensockets != '0' and startsh == '1':
                return "Waiting " + opensockets + "..."
            else:
                return "Stopped"

    @cherrypy.expose
    def statusInst2(self):
        if commands.getstatusoutput('ps aux | grep [h]yrise-server_release | grep "5000" | wc -l')[1] == '1' and commands.getstatusoutput('ps aux | grep [h]yrise-server_release | grep "5001" | wc -l')[1] == '1':
            return "Running"
        elif commands.getstatusoutput('ps aux | grep [h]yrise-server_release | grep "5000" | wc -l')[1] != '1' and commands.getstatusoutput('ps aux | grep [h]yrise-server_release | grep "5001" | wc -l')[1] == '1': 
            return "Running, Master"
        else:
            return "Stopped"

    @cherrypy.expose
    def statusInst3(self):
        if commands.getstatusoutput('ps aux | grep [h]yrise-server_release | grep "5002" | wc -l')[1] == '1':
            return "Running"
        else:
            return "Stopped"

    @cherrypy.expose
    def statusInst4(self):
        if commands.getstatusoutput('ps aux | grep [h]yrise-server_release | grep "5003" | wc -l')[1] == '1':
            return "Running"
        else:
            return "Stopped"

    @cherrypy.expose
    def statusDisp(self):
        if commands.getstatusoutput('ps aux | grep dispatcher | grep "6666" | grep -v grep | wc -l')[1] == '1':
            return "Running"
        else:
            return "Stopped"

  
if __name__ == '__main__':

    random.seed()
    cherrypy.config.update({
        'server.socket_host': '192.168.30.112',
        'server.socket_port': 8080,
    })
    cherrypy.config.update({ "server.logToScreen" : False })
    cherrypy.config.update({'log.screen': False})
    cherrypy.config.update({ "environment": "embedded" })
    
    cherrypy.quickstart(MyServerHandler())

    # print create_json_from_ab("Reads")
