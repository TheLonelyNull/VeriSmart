import os.path
import sys
import subprocess
import shlex
import re
import multiprocessing
import json

from bin import utils



def step3GenerateConfigIteratorNormal(env,out,configFilename,inputfile,percent,logger=None):
    configGen = utils.ConfigGenerator(out, percent, env["cluster-config"], env["window-length"],  env["window-percent"],  env["picked-window"],
            env["instances-limit"], env["config-only"], consecutive=(not env["scatter"]),
            double=env["shifted-window"], skiplist=env["skip-thread"])
    singleConfigFilename = configFilename + ".tmp"
    if env["automatic"]:
        # Create a generator
        # Overwrite configuration file
        return configGen.generatingConfig(configFilename, singleConfigFilename, inputfile, softLimit=env["soft-limit"],
            hardLimit=env["hard-limit"], randomness=(not env["no-random"]), start=env["start-sample"])
    else:
        fd = open(configFilename,"r")
        generatedData=json.load(fd) 
        fd.close()
         
        return configGen.generatorConfigIterator(singleConfigFilename,len(generatedData),generatedData) 


def step4GenerateInstanceIterator(env, cmdline, configIterator,listFile):
    if env["config-only"]:
        sys.exit(0)

    i = 0
    for config in configIterator:
        filename,chosenInstances,b = config
        newcmdline = cmdline + " -C \"%s\"" % filename
#        else:
#            newcmdline = cmdline + " -C %s" % newConfigFilename  
        newcmdline += " -Z %s" % listFile
        if env["verbose"]:
            print(newcmdline)
    # Generating multiple instances
        p = subprocess.Popen(shlex.split(newcmdline), stdout=subprocess.PIPE)
        out, err = p.communicate()
        sys.stdout.flush()
        yield i
        i+=1


#changed to iterator
def callTranslatorSwarm(env, inputfile, percent, logger=None):
    # setting up cmd
    cmdline = step1SetupCMD(env, inputfile, isSwarm=True, logger=logger)
    # get thread lines
    out, result = step2GetThreadLines(env, cmdline, inputfile)
    if not result:
        return out, result
    else:
        if env["showcs"]:   # Exit if this is the only job require to do
            # Extra feature, generating a configuration file for manual controlling context switch
            print("Now generating manual configuration file...")
            sys.stdout.flush()
            configFile = inputfile[:-2] + "_manual_config.json"
            configGen = utils.ConfigGenerator(out, 2, 1, 100)
            configGen.generatingManualConfig(configFile)
            print("...done")
            sys.stdout.flush()
            logger.writelog()
            sys.exit(0)
        # Generating configuration file
        if env["configFile"] == "":
            print("[Swarm by normal settings] Auto-creating configurations...")
            if not env["automatic"]:
                print("Please set -A option if you want to automatically generate instances")
                sys.exit(2)
            env["configFile"] = inputfile[:-2] + "_auto_config%s.json" % env["suffix"]
        configFile = env["configFile"]
        if env["automatic"]:
              print("Generating configurations..")
        else:
              print("Loading configurations..")
           
        #step3GenerateConfigFileNormal(env, out, configFile, logger)
        configIterator = step3GenerateConfigIteratorNormal(env, out,configFile,inputfile, percent, logger)
        
        print("... done.")
        # Generating instances
        if env["automatic"]: 
           if env["instances-limit"] == 0:
              print("Generating instances with no limit")
           else:
              print("Generating instances with limit %s" % env["instances-limit"])
        else:
              print("Generating instances ..")
        dirname, filename = os.path.split(os.path.abspath(inputfile))
        swarmdirname = dirname + "/" + filename[:-2] + ".swarm%s/" % env["suffix"]
        listFile = swarmdirname + "swarm_instances.list"
        #step4GenerateInstances(env, cmdline, configFile, listFile)
        instanceIterator=step4GenerateInstanceIterator(env, cmdline, configIterator,listFile)
        # Get file list
        return listFile, instanceIterator


def callTranslatorSwarmSA(env, inputfile, logger=None):
    """
    For SWARM translation + strategy for SAFE instances
    """
    # setting up cmd
    cmdline = step1SetupCMD(env, inputfile, isSwarm=True, logger=logger)
    # get thread line
    out, result = step2GetThreadLines(env, cmdline, inputfile)
    if not result:
        return out, result
    else:
        print("SEQUENTIAL ANALYSIS:")
        sys.stdout.flush()
        # Generating configuration file
        if env["configFile"] == "":
            env["configFile"] = inputfile[:-2] + "_auto_config%s.json" % env["suffix"]
        configFile = env["configFile"]
        step3GenerateConfigFileSA(env, out, configFile, logger)
        # Generating instances
        print("Generating %s instances..." % env["instances-limit"])
        dirname, filename = os.path.split(os.path.abspath(inputfile))
        swarmdirname = dirname + "/" + filename[:-2] + ".swarm%s/" % env["suffix"]
        listFile = swarmdirname + "swarm_instances.list"
        step4GenerateInstances(env, cmdline, configFile, listFile)
        # get file list
        return step5GetFileListNormal(listFile)