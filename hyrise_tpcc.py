import argparse
import benchmark
import logging
import os
import requests
import shutil
import subprocess
import sys

# include py-tpcc files
sys.path.insert(0, os.path.join(os.getcwd(), "pytpcc", "pytpcc"))
from util import *
from runtime import *
import drivers
from tpcc import *

# disable py-tpcc internal logging
logging.getLogger("requests").setLevel(logging.WARNING)

class TPCCUser(benchmark.User):

    def __init__(self, userId, host, port, dirOutput, queryDict, **kwargs):
        benchmark.User.__init__(self, userId, host, port, dirOutput, queryDict, **kwargs)

        self.scaleParameters = kwargs["scaleParameters"]
        self.config = kwargs["config"]
        self.config["reset"] = False
        self.config["execute"] = True
        self.config["querylog"] = None
        self.config["print_load"] = False
        self.config["port"] = self._port
        self.config["database"] = self._port
        self.driver = drivers.hyrisedriver.HyriseDriver("")
        self.driver.loadConfig(self.config)
        self.driver.conn = self
        self.context = None
        self.lastResult = None
        self.lastHeader = None

    def prepareUser(self):
        """ executed once when user starts """
        self.e = executor.Executor(self.driver, self.scaleParameters)

    def runUser(self):
        """ main user activity """
        txn, params = self.e.doOne()
        tStart = time.time()
        self.driver.executeTransaction(txn, params)
        tEnd = time.time()
        self.log("transactions", "%s,%f" % (txn, tEnd - tStart))

    def stopUser(self):
        """ executed once after stop request was sent to user """
        pass

    # HyriseConnection stubs
    # ======================
    def query(self, querystr, paramlist=None, commit=False):
        for k,v in paramlist.iteritems():
            if v == True:    v = 1;
            elif v == False: v = 0;
        result = self.fireQuery(querystr, paramlist, sessionContext=self.context, autocommit=commit).json()
        self.context = result.get("session_context", None)
        self.lastResult = result.get("rows", None)
        self.lastHeader = result.get("header", None)
        self.lastPerf   = result.get("performanceData", None)

    def commit(self):
        if not self.context:
            raise Exception("Should not commit without running context")
        result = self.fireQuery("""{"operators": {"cm": {"type": "Commit"}}}""", sessionContext=self.context)
        self.context = None
        return result

    def rollback(self):
        if not self.context:
            raise Exception("Should not rollback without running context")
        result = self.fireQuery("""{"operators": {"rb": {"type": "Rollback"}}}""", sessionContext=self.context)
        self.context = None
        return result

    def runningTransactions(self):
        return self._session.get("http://%s:%s/status/tx" % (self._host, self._port)).json()

    def fetchone(self, column=None):
        if self.lastResult:
            r = self.lastResult.pop()
            return r[self.lastHeader.index(column)] if column else r
        return None

    def fetchone_as_dict(self):
        if self.lastResult:
            return dict(zip(self.lastHeader, self.lastResult.pop()))
        return None

    def fetchall(self):
        tmp = self.lastResult
        self.lastResult = None
        return tmp

    def fetchall_as_dict(self):
        if self.lastResult:
            r = [dict(zip(self.lastHeader, cur_res)) for cur_res in self.lastResult]
            self.lastResult = None
            return r
        return None


class TPCCBenchmark(benchmark.Benchmark):

    def __init__(self, benchmarkGroupId, buildSettings, **kwargs):
        benchmark.Benchmark.__init__(self, benchmarkGroupId, buildSettings, **kwargs)

        self._dirHyriseDB = os.path.join(os.getcwd(), "hyrise", "test")
        os.environ['HYRISE_DB_PATH'] = self._dirHyriseDB

        self.scalefactor     = kwargs["scalefactor"] if kwargs.has_key("scalefactor") else 1
        self.warehouses      = kwargs["warehouses"] if kwargs.has_key("warehouses") else 4
        self.driverClass     = createDriverClass("hyrise")
        self.driver          = self.driverClass(os.path.join(os.getcwd(), "pytpcc", "tpcc.sql"))
        self.driver.confirm  = False
        self.driver.tables   = ["CUSTOMER", "DISTRICT", "HISTORY", "ITEM", "NEW_ORDER", "ORDER_LINE", "ORDERS", "STOCK", "WAREHOUSE"]
        self.scaleParameters = scaleparameters.makeWithScaleFactor(self.warehouses, self.scalefactor)
        self.regenerate      = False

        self.setUserClass(TPCCUser)

    def benchPrepare(self):
        # make sure the TPC-C query and table directories are present
        dirPyTPCC   = os.path.join(os.getcwd(), "pytpcc", "pytpcc")
        dirTables   = os.path.join(self._dirHyriseDB, "tpcc", "tables")

        sys.stdout.write("Checking for table files... ")
        sys.stdout.flush()
        generate = False
        if not os.path.isdir(dirTables):
            print "no table files found"
            generate = True
            os.makedirs(dirTables)
        else:
            for t in self.driver.tables:
                if not os.path.isfile(os.path.join(dirTables, "%s.tbl" % t)) or not os.path.isfile(os.path.join(dirTables, "%s.hdr" % t)):
                    print "table files incomplete"
                    generate = True
                    break
        if self.regenerate:
            print "table file regeneration requested"
            generate = True
        if generate:
            sys.stdout.write("regenerating... ")
            sys.stdout.flush()
            # regenerate here
        print "done"

        rand.setNURand(nurand.makeForLoad())
        defaultConfig = self.driver.makeDefaultConfig()
        config = dict(map(lambda x: (x, defaultConfig[x][1]), defaultConfig.keys()))
        config["querylog"] = None
        config["debug"] = False
        config["print_load"] = False
        config["reset"] = False
        config["port"] = self._port
        config["database"] = "tpcc/tables"
        config["queries"] = os.path.join(dirPyTPCC, "queries")
        self.driver.loadConfig(config)

        self.driver.executeStart()

        self.setUserArgs({
            "scaleParameters": self.scaleParameters,
            "config": config
        })

if __name__ == "__main__":
    aparser = argparse.ArgumentParser(description='Python implementation of the TPC-C Benchmark for HYRISE')
    aparser.add_argument('--scalefactor', default=1, type=float, metavar='SF',
                         help='Benchmark scale factor')
    aparser.add_argument('--warehouses', default=1, type=int, metavar='W',
                         help='Number of Warehouses')
    aparser.add_argument('--duration', default=20, type=int, metavar='D',
                         help='How long to run the benchmark in seconds')
    aparser.add_argument('--clients', default=1, type=int, metavar='N',
                         help='The number of blocking clients to fork')
    aparser.add_argument('--no-load', action='store_true',
                         help='Disable loading the data')
    aparser.add_argument('--no-execute', action='store_true',
                         help='Disable executing the workload')
    aparser.add_argument('--port', default=5001, type=int, metavar="P",
                         help='Port on which HYRISE should be run')
    aparser.add_argument('--warmup', default=5, type=int,
                         help='Warmuptime before logging is activated')
    aparser.add_argument('--manual', action='store_true',
                         help='Do not build and start a HYRISE instance (note: a HYRISE server must be running on the specified port)')
    args = vars(aparser.parse_args())

    s1 = benchmark.Settings("none", oldMode=True, PRODUCTION=1, WITH_MYSQL=1, COMPILER="g++48", PERSISTENCY="NONE")
    s2 = benchmark.Settings("logger", oldMode=True, PRODUCTION=1, WITH_MYSQL=1, COMPILER="g++48", PERSISTENCY="BUFFEREDLOGGER")
    s3 = benchmark.Settings("nvram", oldMode=True, PRODUCTION=1, WITH_MYSQL=1, COMPILER="g++48", PERSISTENCY="NVRAM")

    kwargs = {
        "port"              : args["port"],
        "manual"            : args["manual"],
        "warmuptime"        : args["warmup"],
        "runtime"           : args["duration"],
        "numUsers"          : args["clients"],
        "warehouses"        : args["warehouses"],
        "benchmarkQueries"  : [],
        "prepareQueries"    : []
    }

    for num_clients in xrange(11, 31):
        name = "tpcc_users_%s"%num_clients
        kwargs["numUsers"] = num_clients

        print "Executing number of users: " + str(num_clients)
        print "+---------------------------------+\n"

        b1 = TPCCBenchmark(name, s1, **kwargs)
        b2 = TPCCBenchmark(name, s2, **kwargs)
        # b3 = TPCCBenchmark(name, s3, **kwargs)

        b1.run()
        b2.run()
        #b3.run()
