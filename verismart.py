import os
import os.path
import shutil
import sys
import getopt
import time
# Modules import
from bin import translator_handler, backend_handler, log_handler, utils

def usage(cmd, errormsg="", showHelp=True):
    if showHelp:
        print("")
        print("VeriSMART | Verification Smart")
        print("")
        print("Usage:")
        print("   %s [options] FILE (.c)" % cmd)
        print("")
        print(" general options:")
        print("   -h, --help                            display short help message")
        print("   -v, --version                         display version number")
        print("   -V, --verbose                         verbose mode (display extra information from other modules)")
        print("   --contextswitch                       show number of context switches for each thread")
        print("   -I,--include-dir=<dir>                include directory for input file (if requires)")
        ###BF print("   -o,--output=<filename>          output filename (%s mode only)" % (make_bold("normal")))
        print("   --suffix                              suffix name for generated output directory")
        ###BF print("   --archive                       keep instance files and logs in compressed archives (default: no)")
        ###BF print("   --keep-files                    keep instance files after analyzing (default: no)")
        ###BF print("   --keep-logs                     keep instance logs after analyzing (default: no)")
        print("   --config-only                         only generate tiling configuration file")
        print("   --cluster-config<X>                   generate set of tiling configuration files of given size")
        ###BF print("   -c,--config-file<X>             swarm verification with manual tiling configuration file")
        print("   -c,--config-file<X>                   use given tiling configuration file")
        ###BF print("   --seq-only                      only generate sequentialized program")
        print("   --instances-only                      only generate tiled and sequentialized program instances")
        print("   --cores<X>                            number of sub-processes spawned in parallel for instance generation and verification (default: 4)")
        print("   -T,--timelimit<X>                     overall time limit (in seconds, default: 86400s)")
        print("   -M,--memorylimit<X>                   memory limit (in kilobytes, default: no limit)")
        print("")
        print(" instrumentation options:")
        ###BF print("   -S,--analysis-mode=<X>          mode {normal, swarm} default: swarm")
        ###BF print("   --chain<X>                      module chain configuration file")
        # print("   --force-chain                       automatic select configuration file (default: false)")
        # print("   --no-robin                          do not use round-robin main driver")
        print("   -l,--window-length<X>                 window size in visible statements (default: 1)")
        print("   --window-percent<X>                   window size as percentage of thread size")
        print("   --sequential-analysis                 pick one context switch randomly in each thread")
        print("   -p,--picked-window<X>                 number of windows picked for each thread (default: 1)")
        print("   --shift-window                        windows can be shifted up and down (by half size of a window)")
        print("   --skip-thread<X>                      skip thread with name <X> in the tilings")
        print("   --instances-limit<X>                  limit the number of generated instances (default: 100, use 0 to unlimit)")
        print("")
        print(" program bounding options:")
        print("   -u<X>,--unwind<X>                     unwind bound for all loops (default: 1)")
        print("   -w<X>,--while-unwind<X>               unwind bound for potentially unbounded loops (default: 1)")
        print("   -f<X>,--for-unwind<X>                 unwind bound for bounded loops (default: 1)")
        print("   -r<X>,--rounds<X>                     number of round-robin schedules (default: 1)")
        print("")
        print(" verification options:")
        print("   --exit-on-error                       exit on first error found by one of instances")
        print("   -b,--backend=<fmt>                    backend verification tool (default: cbmc, use --list-backends for more details)")
        print("   --backend-path=<path>                 custom path to backend executable file") # does it "(requires -b, --backend)"?
        print("   --backend-clang-path=<path>           path to clang (or llvm-gcc) binary (only for -b klee and -b llbmc)")
        print("   -a,--extra-args<X>                    extra arguments for backends")
        print("   -d,--depth<X>                         backend depth bound (if supported by backend, default: no bound)")
        print("   --timeout<X>                          timeout for each verification process (default: 3600)")
        print("   --cex                                 enable counterexample generation (if supported by backend)")
        print("   --cex-dir<X>                          counterexample output directory (default: FILE-counterexample)")
        print("")
        print(" CBMC-specific options (requires -b cbmc)")
        print("   --stop-on-fail                        stop when the first error is found")
        print("   --bounds-check                        enable array bounds checks (optional)")
        print("   --div-by-zero-check                   enable division by zero checks (optional)")
        print("   --pointer-check                       enable pointer checks (optional)")
        print("   --memory-leak-check                   enable memory leak checks (optional)")
        print("   --signed-overflow-check               enable arithmetic over- and underflow checks of signed integer (optional)")
        print("   --unsigned-overflow-check             enable arithmetic over- and underflow checks of unsigned integer (optional)")
        print("   --float-overflow-check                check floating-point for +/-Inf (optional)")
        print("   --nan-check                           check floating-point for NaN (optional)")
        print("   --no-simplify                         no simplification from cbmc (optional)")
        print("   --refine-arrays                       array refinement from cbmc (optional)")
        print("   --overflow-check                      enable arithmetic over- and underflow check (optional)")
        print("")

    if errormsg:
        print(errormsg + "\n")
    sys.exit(1)

def analysisSwarm(env, preprocessedoutfile, logger, realstarttime, percentage):
    if env["sequential-analysis"]:    # Sequential analysis mode

        if percentage:
            print("Sequential analysis is not available for this mode.")
            sys.exit(0)  # Successfully return

        logger.record("Sequential analysis\n")
        seqoutfilelist, result = translator_handler.callTranslatorSwarmSA(env, preprocessedoutfile, logger)
        if not result:   # Sequentialization unsuccessful
            overalltime = time.time() - realstarttime
            if env["singlefile"]:
                backend_handler.printStats(env["input"], "REJECT", overalltime)
            else:
                backend_handler.printStats("<multiple files>", "REJECT", overalltime)
            sys.exit(2)
        if env["seq-only"]:
            sys.exit(0)
        # Debug, override initial time out
        env["timeout"] = max(env["timelimit"], env["initial-timeout"])
        backend_handler.callBackendSwarmSA(env, seqoutfilelist, realstarttime, logger)
        if not env["keep-files"]:
            for f in seqoutfilelist:
                try:
                    os.remove(f)
                except os.error:
                    pass
        logger.writelog()
        logger.savereport()
        sys.exit(0)  # Successfully return
    else:
        """
            METHOD 2: sequentialization + swarm technique
        """
        """ 3. Call TRANSLATOR and save the files as "_cs_......"
        """
        listFile, instanceIterator = translator_handler.callTranslatorSwarm(env, preprocessedoutfile, percentage, logger)

        if env["seq-only"]:
            for index in instanceIterator: print ("."),
            print("done.")
            sys.exit(0)

        """ 4. Call BACKEND on _cs_....... files
            """
        backend_handler.callBackendSwarm(env, listFile, realstarttime, logger, instanceIterator)

        if env["archive"]:
            dirname, filename = os.path.split(os.path.abspath(preprocessedoutfile))
            swarmdirname = dirname + "/" + filename[:-2] + ".swarm%s/" % env["suffix"]
            shutil.make_archive(swarmdirname, "tar", swarmdirname)
            shutil.rmtree(swarmdirname, True)

        logger.writelog()
        logger.savereport()
        sys.exit(0)  # Successfully return

def main(args):
    """ 1. Parse command line option"""
    cmd = args[0]
    shortopts = "hVvI:b:d:u:w:f:r:T:M:c::l:p:a:"
    longopts = ["help", "version", "cex", "cex-dir=", "verbose", "include-dir=", "backend=", "depth=",
                "extra-args=", "unwind=", "while-unwind=", "for-unwind=",
                "max-threads=", "rounds=", "timelimit=", "memorylimit=", "contextswitch",
                "config-file=", "window-length=", "picked-window=", "instances-limit=", "backend-path=",
                "timeout=", "generate-limit=", "soft-limit=", "sequential-analysis", "cores=",
                "backend-clang-path=", "instances-only", "list-backends", "suffix=",
                "config-only", "cluster-config=", "shifted-window",
                "stop-on-fail", "bounds-check", "div-by-zero-check", "pointer-check",
                "memory-leak-check", "signed-overflow-check", "unsigned-overflow-check",
                "float-overflow-check", "nan-check", "no-simplify", "refine-arrays"]
    
    try:
        opts, nonopts = getopt.gnu_getopt(args[1:], shortopts, longopts)
    except getopt.GetoptError as err:
        usage(cmd, "error: " + str(err))
        sys.exit(2)

    # Environment for CSeq
    env = {}

    # Predefined values, God please forgive me for this long function!
    env["cex"] = False
    env["witness"] = ""
    env["cil"] = False
    env["debug"] = False
    env["default-include"] = False
    env["verbose"] = False
    env["produce-reduce"] = False
    env["minimum-bits"] = 4
    env["maximum-bits"] = 8
    env["analysis-mode"] = "swarm"
    env["seq-only"] = False
    env["include-dir"] = []  # multiple include directory
    env["outputfile"] = ""
    env["depth"] = 0
    env["extra-args"] = ""
    env["domain"] = "default"
    env["backend"] = "cbmc"   # default is CBMC
    env["backend-path"] = ""
    env["clang-path"] = ""
    env["mallocscanfail"] = False
    env["main-argc"] = 1
    env["main-argv"] = "program"
    env["error-label"] = "ERROR"  # Default
    env["sv-comp"] = False
    env["svcomp"] = False
    # Properties check
    env["deadlock"] = False
    env["keepstaticarray"] = False
    env["donotcheckvisiblepointer"] = False
    env["robin"] = True
    env["explode-pc"] = False
    # Unwind bound
    env["softunwindbound"] = False
    env["unwind"] = 1
    env["whileunwind"] = 0
    env["forunwind"] = 0
    env["soft-unwind-max"] = 0
    # Threads and rounds
    env["max-threads"] = 0
    env["rounds"] = 1
    env["timelimit"] = 86400
    env["memorylimit"] = -1   # no limit
    env["preprocessed"] = False
    env["headerfile"] = ""
    env["chain"] = ""
    env["force-chain"] = False
    # Swarm things
    env["showcs"] = False   # Show number of context switches for each thread
    env["configFile"] = ""
    env["generate-limit"] = 0
    env["automatic"] = True
    env["incremental"] = False
    env["execution-mode"] = "parallel"
    env["cores"] = 4
    env["window-length"] = 1
    env["picked-window"] = 1
    env["instances-limit"] = 100
    env["soft-limit"] = 0
    env["hard-limit"] = 0 	# must stay 0
    env["initial-timeout"] = 3600
    env["parallel-generator"] = False
    env["generators"] = 4
    env["sequential-analysis"] = False
    env["iterations"] = 4
    env["strategy"] = "quarter"
    env["lowerbound"] = 500
    env["stats"] = False
    env["candidate"] = "all"
    env["keep-files"] = False
    env["keep-logs"] = False
    env["split-config"] = False
    env["bag-size"] = 100
    env["initial-iteration"] = False
    env["descFile"] = ""
    env["mode"] = "B"
    env["cluster-jobs"] = False
    env["workers"] = 1
    env["workerID"] = 0
    env["type"] = "safe"
    env["save-results"] = True
    env["oResFile"] = ""
    env["dOption"] = ""
    env["dl"] = 0
    env["du"] = 86400
    env["dtl"] = -1
    env["dtu"] = -1
    env["dfl"] = -1
    env["dfu"] = -1
    env["dul"] = -1
    env["duu"] = -1
    env["dol"] = -1
    env["dou"] = -1
    env["iResFile"] = ""
    env["pOption"] = "f"
    env["pl"] = 0
    env["pu"] = 86400
    env["ptl"] = -1
    env["ptu"] = -1
    env["pfl"] = -1
    env["pfu"] = -1
    env["pul"] = -1
    env["puu"] = -1
    env["pol"] = -1
    env["pou"] = -1
    env["no-dividing"] = False
    env["iter-id"] = 0

    # RTOS
    env["oil"] = ""                 # OIL description file
    env["sched"] = "default"        # Scheduling type
    env["suffix"] = ""              # suffix for swarm directory
    env["archive"] = False          # suffix for swarm directory
    env["config-only"] = False      # only generate configuration files
    env["cluster-config"] = 0       # generate cluster of configuration files of given size
    env["swarm-translator"] = ""    # only generate configuration files
    env["scatter"] = False          # scatter context switch points
    env["shifted-window"] = False

    # wmm
    env["wmm"] = False
    env["wmm-p"] = -1
    env["wmm-l"] = -1
    env["wmm-double"] = False
    env["percentage"] = False
    env["window-percent"] = -1
    env["skip-thread"] = {}
    env["exit-on-error"] = False
    env["stop-on-fail"] = False
    env["no-random"] = False
    env["start-sample"] = 0

    # For cbmc backend
    env["bounds-check"] = False
    env["div-by-zero-check"] = False
    env["pointer-check"] = False
    env["memory-leak-check"] = False
    env["signed-overflow-check"] = False
    env["unsigned-overflow-check"] = False
    env["float-overflow-check"] = False
    env["nan-check"] = False
    env["no-simplify"] = False
    env["refine-arrays"] = False

    # Logger for reporting result
    logger = log_handler.Logger()
    # record command line
    logger.logging(" ".join(args), 0)
    logger.record(" ".join(args) + "\n")

    # Parse options
    for o, a in opts:
        if o in ("-h", "--help"):
            usage(cmd, "")
            sys.exit(0)
        elif o in ("-v", "--version"):
            ### BF print "Lazy-CSeq: %s" % VERSION
            print("%s" % VERSION)
            sys.exit(0)
        elif o in ("-C", "--cex"):
            env["cex"] = True
        elif o in ("--cex-dir",):
            env["witness"] = a
        elif o in ("-D", "--debug"):
            env["debug"] = True
        elif o in ("--cil",):
            env["cil"] = True
        elif o in ("--default-include",):
            env["default-include"] = True
        elif o in ("-V", "--verbose"):
            env["verbose"] = True
        elif o in ("-S", "--analysis-mode"):
            env["analysis-mode"] = a
        elif o in ("-I", "--include-dir"):
            env["include-dir"].append(a)
        elif o in ("-o", "--output"):
            env["outputfile"] = a
        elif o in ("-b", "--backend"):
            env["backend"] = a
        elif o in ("--backend-path", "--path-backend"):
            env["backend-path"] = a
        elif o in ("--instances-only",):
            env["seq-only"] = True
        elif o in ("--deadlock",):
            env["deadlock"] = True
        elif o in ("--keepstaticarray",):
            env["keepstaticarray"] = True
        elif o in ("--donotcheckvisiblepointer",):
            env["donotcheckvisiblepointer"] = True
        elif o in ("--no-robin",):
            env["robin"] = False
        elif o in ("--explode-pc",):
            env["explode-pc"] = True
        elif o in ("--backend-clang-path",):
            env["clang-path"] = a
        elif o in ("--produce-reduce",):
            env["produce-reduce"] = True
        elif o in ("--minimum-bits",):
            env["minimum-bits"] = int(a)
        elif o in ("--maximum-bits",):
            env["maximum-bits"] = int(a)
        elif o in ("-d", "--depth"):
            env["depth"] = int(a)
        elif o in ("-m", "--mallocscanfail"):
            env["mallocscanfail"] = True
        elif o in ("--main-argc",):
            env["main-argc"] = int(a)
        elif o in ("--main-argv",):
            env["main-argv"] = a
        elif o in ("-a", "--extra-args",):
            env["extra-args"] = a
        elif o in ("--list-backends",):
            print("List of supported backends in VeriSmart:")
            print("cbmc, esbmc, llbmc, klee, interproc, concurinterproc, framac, pagai, impara, 2ls, seahorn")
            sys.exit(0)
        elif o in ("--domain",):
            env["domain"] = a
        elif o in ("--error-label",):
            env["error-label"] = a
        elif o in ("--error-func",):
            env["error-label"] = a
        elif o in ("--sv-comp",):
            env["sv-comp"] = True
        elif o in ("--svcomp",):
            env["svcomp"] = True
        elif o in ("--preprocessed",):
            env["preprocessed"] = True
        elif o in ("--chain",):
            env["chain"] = a
            if env["chain"] == "unroller":
                env["seq-only"] = True
        elif o in ("--force-chain",):
            env["force-chain"] = True
        elif o in ("-s", "--softunwindbound"):
            env["softunwindbound"] = True
        elif o in ("-u", "--unwind"):
            env["unwind"] = int(a)
        elif o in ("-w", "--while-unwind", "--unwind-while"):
            env["whileunwind"] = int(a)
        elif o in ("-f", "--for-unwind", "--unwind-for"):
            env["forunwind"] = int(a)
        elif o in ("-U", "--soft-unwind-max", "--unwind-for-max"):
            env["soft-unwind-max"] = int(a)
        elif o in ("-t", "--max-threads"):
            env["max-threads"] = int(a)
        elif o in ("-r", "--rounds"):
            env["rounds"] = int(a)
        elif o in ("-T", "--timelimit"):
            env["timelimit"] = int(a)
        elif o in ("-M", "--memorylimit"):
            env["memorylimit"] = int(a)
        elif o in ("-Y", "--contextswitch"):
            env["showcs"] = True
        elif o in ("-c", "--config-file"):
            env["automatic"] = False
            env["configFile"] = a
        elif o in ("-A", "--automatic"):
            env["automatic"] = True
        elif o in ("--incremental",):
            env["incremental"] = True
        elif o in ("-l", "--window-length"):
            env["window-length"] = int(a)
        elif o in ("-p", "--picked-window"):
            env["picked-window"] = int(a)
        elif o in ("-L", "--instances-limit"):
            env["instances-limit"] = int(a)
        elif o in ("--generate-limit",):
            env["generate-limit"] = int(a)
        elif o in ("--soft-limit",):
            env["soft-limit"] = int(a)
        elif o in ("--hard-limit",):
            env["hard-limit"] = int(a)
        elif o in ("--timeout",):
            env["initial-timeout"] = int(a)
        elif o in ("--sequential-analysis",):
            env["sequential-analysis"] = True
        elif o in ("--parallel-generator",):
            env["parallel-generator"] = True
        elif o in ("--generators",):
            env["generators"] = int(a)
        elif o in ("--split-config",):
            env["split-config"] = True
        elif o in ("--bag-size",):
            env["bag-size"] = int(a)
        elif o in ("--iterations",):
            env["iterations"] = int(a)
        elif o in ("--strategy",):
            env["strategy"] = a
        elif o in ("--stats",):
            env["stats"] = True
        elif o in ("--lowerbound",):
            env["lowerbound"] = int(a)
        elif o in ("--keep-files",):
            env["keep-files"] = True
        elif o in ("--no-keep-files",):
            env["keep-files"] = False
        elif o in ("--keep-logs",):
            env["keep-logs"] = True
        elif o in ("--no-keep-logs",):
            env["keep-logs"] = False
        elif o in ("--candidate",):
            env["candidate"] = a
        elif o in ("--cores",):
            env["generators"] = int(a)
            env["cores"] = int(a)
        elif o in ("--initial-iteration",):
            env["initial-iteration"] = True
        elif o in ("--descFile",):
            env["descFile"] = a
        elif o in ("--mode",):
            env["mode"] = a
        elif o in ("--cluster-jobs",):
            env["cluster-jobs"] = True
        elif o in ("--workers",):
            env["workers"] = int(a)
        elif o in ("--workerID",):
            env["workerID"] = int(a)
        elif o in ("--type",):
            env["type"] = a
        elif o in ("--save-results",):
            env["save-results"] = True
        elif o in ("--oResFile",):
            env["oResFile"] = a
        elif o in ("--dOption",):
            env["dOption"] = a
        elif o in ("--dl",):
            env["dl"] = int(a)
        elif o in ("--du",):
            env["du"] = int(a)
        elif o in ("--dtl",):
            env["dtl"] = int(a)
        elif o in ("--dtu",):
            env["dtu"] = int(a)
        elif o in ("--dfl",):
            env["dfl"] = int(a)
        elif o in ("--dfu",):
            env["dfu"] = int(a)
        elif o in ("--dul",):
            env["dul"] = int(a)
        elif o in ("--duu",):
            env["duu"] = int(a)
        elif o in ("--dol",):
            env["dol"] = int(a)
        elif o in ("--dou",):
            env["dou"] = int(a)
        elif o in ("--iResFile",):
            env["iResFile"] = a
        elif o in ("--pOption",):
            env["pOption"] = a
        elif o in ("--pl",):
            env["pl"] = int(a)
        elif o in ("--pu",):
            env["pu"] = int(a)
        elif o in ("--ptl",):
            env["ptl"] = int(a)
        elif o in ("--ptu",):
            env["ptu"] = int(a)
        elif o in ("--pfl",):
            env["pfl"] = int(a)
        elif o in ("--pfu",):
            env["pfu"] = int(a)
        elif o in ("--pul",):
            env["pul"] = int(a)
        elif o in ("--puu",):
            env["puu"] = int(a)
        elif o in ("--pol",):
            env["pol"] = int(a)
        elif o in ("--pou",):
            env["pou"] = int(a)
        elif o in ("--no-dividing",):
            env["no-dividing"] = True
        elif o in ("--iter-id",):
            env["iter-id"] = int(a)
        elif o in ("--oil",):
            env["oil"] = a
        elif o in ("--sched",):
            env["sched"] = a
        elif o in ("--suffix",):
            env["suffix"] = a
        elif o in ("--archive",):
            env["archive"] = True
        elif o in ("--config-only",):
            env["config-only"] = True
        elif o in ("--swarm-translator",):
            env["swarm-translator"] = a
        elif o in ("--cluster-config",):
            env["cluster-config"] = int(a)
        elif o in ("--scatter",):
            env["scatter"] = True
        elif o in ("--shifted-window",):
            env["shifted-window"] = True
        elif o in ("--wmm",):
            env["wmm"] = True
        elif o in ("--wmm-p",):
            env["wmm-p"] = int(a)
        elif o in ("--wmm-l",):
            env["wmm-l"] = int(a)
        elif o in ("--wmm-shifted-window",):
            env["wmm-double"] = True
        elif o in ("--window-percent",):
            env["percentage"] = True
            env["window-percent"] = int(a)
        elif o in ("--skip-thread",):
            env["skip-thread"][a] = True
        elif o in ("--exit-on-error",):
            env["exit-on-error"] = True
        elif o in ("--stop-on-fail",):
            env["stop-on-fail"] = True
        elif o in ("--no-random",):
            env["no-random"] = True
        elif o in ("--start-sample",):
            env["start-sample"] = int(a)
        elif o in ("--bounds-check",):
            env["bounds-check"] = True
        elif o in ("--div-by-zero-check",):
            env["div-by-zero-check"] = True
        elif o in ("--pointer-check",):
            env["pointer-check"] = True
        elif o in ("--memory-leak-check",):
            env["memory-leak-check"] = True
        elif o in ("--signed-overflow-check",):
            env["signed-overflow-check"] = True
        elif o in ("--unsigned-overflow-check",):
            env["unsigned-overflow-check"] = True
        elif o in ("--float-overflow-check",):
            env["float-overflow-check"] = True
        elif o in ("--nan-check",):
            env["nan-check"] = True
        elif o in ("--no-simplify",):
            env["no-simplify"] = True
        elif o in ("--refine-arrays",):
            env["refine-arrays"] = True
        else:
            assert False, "unhandled options" + o

    # Parsing input files
    singlefile = True
    inputfile = ""
    inputfilelist = []

    # Check input files (non option arguments)
    if len(nonopts) == 1:
        inputfile = nonopts[0]
    elif len(nonopts) > 1:
        inputfilelist = nonopts
        singlefile = False
    else:
        usage(cmd, "error: please provide input file(s) for analysis", showHelp=False)
        sys.exit(2)

    # Check for existance of these input file
    if singlefile:
        if not os.path.isfile(inputfile):
            usage(cmd, "error: file %s does not exist" % inputfile, showHelp=False)
            sys.exit(2)
    else:
        for f in inputfilelist:
            if not os.path.isfile(f):
                usage(cmd, "error: file %s does not exist" % f, showHelp=False)
                sys.exit(2)
    
    # Input store here
    env["singlefile"] = singlefile
    env["input"] = inputfile
    if env["witness"] == "":
        env["witness"] = inputfile + "-counterexample"
    env["inputlist"] = inputfilelist

    # Check commandline options
    if ("--instances-only","") in opts and ("--config-only","") in opts:
        usage(cmd, "error: cannot use --instances-only and --config-only simultaneously", showHelp=False)
        sys.exit(2)
    if ("--config-only","") in opts:
        for (c, o) in opts:
            if c == "-c" or c == "--config-file" :
                usage(cmd, "error: cannot use --config-only and set config file simultaneously", showHelp=False)
                sys.exit(2)
    dopts = dict(opts)
    if "--cluster-config" in dopts:
        for (c, o) in opts:
            if c == "-c" or c == "--config-file" :
                usage(cmd, "error: cannot use --cluster-config and set config file simultaneously", showHelp=False)
                sys.exit(2)
            if c == "--config-only" :
                usage(cmd, "error: cannot use --cluster-config and --config-only simultaneously", showHelp=False)
                sys.exit(2)
            if c == "--instances-only" :
                usage(cmd, "error: cannot use --cluster-config and --instances-only only simultaneously", showHelp=False)
                sys.exit(2)

    realstarttime = time.time()    # save wallclock time

    # Begin business here
    """ 2. Call PREPROCESSOR and save the files as "....+._pp_.c"
        "_pp_" means IS PROPROCESSED
    """
    preprocessedoutfile = inputfile
    logger.setInputFile(preprocessedoutfile[:-2])  # strip out .c

    """ 3. Launch the analysis of preprocessed inputs
    """

    if env["analysis-mode"] == "normal":
        # analysisNormal(env, preprocessedoutfile, logger, realstarttime)
        translator_handler.callTranslatorNormal(env, preprocessedoutfile, logger)

    elif env["analysis-mode"] == "swarm":
        if env["wmm"]:
            analysisSwarmWMM(env, preprocessedoutfile, logger, realstarttime)
        #elif env["percentage"]:
        #    analysisSwarmPercentage(env, preprocessedoutfile, logger, realstarttime)
        else:
            analysisSwarm(env, preprocessedoutfile, logger, realstarttime, env["percentage"])

    else:
        usage(cmd, "error: incorrect analysis method - %s" % env["analysis-mode"], showHelp=False)
        sys.exit(2)

if __name__ == "__main__":
    main(sys.argv[0:])