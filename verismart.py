#!/usr/bin/env python
import os.path
import subprocess
import shlex
import os
import os.path
import sys
import getopt

from bin import log_handler


VERSION = "VeriSmart-1.0-2017.12.19"
VERSION = "VeriSmart-1.1-2019.02.07"
VERSION = "VeriSmart-1.2-2021.02.11"

"""

Description:
	Verification Smart, swarm verification
	
TODO:


Changelog:
	2021.02.11  Software Reengineering
	----------
	2018.07.09  Allow splitting the configuration file and loop on analysis (see env ["split-config"])
	2017.12.19  counterexample generation
	2017.09.06  add generate-limit option
	2016.11.16  Overhaul option help printing
	2016.11.05  Add option to use percentage for windows (swarm)
	2016.11.03  Add option for inplacer translator, now can swarm on WMM
	2016.09.15  Become a swarm launcher by default
	2016.05.23  Add option to explode pc array
	2016.05.17  Add Seahorn as a backend
	2015.11.25  Add option to keep static array
	2015.08.24  Now outputfile is the actual outputfile for normal mode
	2015.08.06  Add option to force selection of chain for backend
	2015.07.28  Add additional deadlock check
	2015.07.06  Add options for passing main function arguments
	2015.03.06  Add custom path for clang (llvm) to support llbmc and klee backends
	2015.02.16  Add SWARM strategy for separate iteration
	2015.02.03  Add SWARM strategy for incremental swarming strategy
	2015.01.20  Add SWARM strategies for SAFE and UNSAFE instance
	2015.01.16  Add logging feature, for easier experimental calls
	2015.01.14  Fix options print
	2014.12.12  Move backends handler to backend_handler.py, translator handler to translator_handler.py,
				and preprocessor handler to the corresponding file
	2014.12.02  Initial version

"""

def usage(cmd, errormsg="", showHelp=True):
	if showHelp:
		print("")
		print("  VeriSMART | Verification Smart  ")
		print("")
		print("Usage: ")
		print("   %s [options] -i FILE (.c)" % cmd)
		print("")
		print("swarm options:")
		print("   -Y,--contextswitch                show number of context switches for each thread")
		#print("   -I,--include-dir=<dir>           include directory for input file (if requires)")
		#print("   -o,--output=<filename>           output filename (%s mode only)" % (make_bold("normal")))
		print("   --suffix                          suffix name for generated output directory")
		#print("   --archive                        keep instance files and logs in compressed archives (default: no)")
		#print("   --keep-files                     keep instance files after analyzing (default: no)")
		#print("   --keep-logs                      keep instance logs after analyzing (default: no)")
		print("   --config-only                     only generate tiling configuration file")
		#print("   --cluster-config<X>              generate set of tiling configuration files of given size")
		#print("   -c,--config-file<X>              swarm verification with manual tiling configuration file")
		#print("   -c,--config-file<X>              use given tiling configuration file")
		#print("   --seq-only                       only generate sequentialized program")
		#print("   --instances-only                 only generate tiled and sequentialized program instances")
		print("   --exit-on-error                   exit on first error found by one of instances")	
		print("   --cores<X>                        number of sub-processes spawned in parallel for instance generation and verification (default: 4)")
		print("   --instances-limit<X>              limit the number of generated instances (default: 100, use 0 to unlimit)")
		print("   -T,--timelimit<X>                 overall time limit (in seconds, default: 86400s)")
		#print("   -M,--memorylimit<X>              memory limit (in kilobytes, default: no limit)")
		print("")
		print("instrumentation options:")
		#print("   -S,--analysis-mode=<X>          	mode {normal, swarm} default: swarm")
		#print("   --chain<X>                      	module chain configuration file")
		#print("   --force-chain                     automatic select configuration file (default: false)")
		#print("   --no-robin                       do not use round-robin main driver")
		print("   -l,--window-length<X>             window size in visible statements (default: 1)")
		print("   --window-percent<X>               window size as percentage of thread size")
		#print("   --sequential-analysis            pick one context switch randomly in each thread")
		print("   -p,--picked-window<X>             number of windows picked for each thread (default: 1)")
		print("   --shift-window                    windows can be shifted up and down (by half size of a window)")
		#print("   --scatter                       	windows can be scattered (default: no)")
		#print("   --skip-thread<X>                 skip thread with name <X> in the tilings")
		# print("   --parallel-generator            enable generating instances in parallel (default: no)")
		#print("   --generators<X>                 	number of cores used to generate instances (default: 4)")
		#print(""
		#print(" %s options:" % (make_bold("swarm"))
		#print("   -A,--automatic                  	automatic generating tiling configuration file")
		#print("   --percentage                    	use percentage of thread length (recommend for long thread)")
		#print("   --no-random                     	deterministic generation of instances")
		#print("   --start-sample<X>               	determine the first sample to pick (requires --no-random --instances-limit)")
		#print("   --instances-limit<X>            	limit the number of generated instances (for generating config, default: 1000, use 0 to unlimit)")
		#print("   --generate-limit<X>             	limit the number of generated instances (after generating config, default: 1000, use 0 to unlimit)")
		#print("   --soft-limit<X>                 	use automatic limit on the total combinations (default: 1000, use 0 to unlimit)")
		#print("   --hard-limit<X>                 	generate at most X instances (default: 1000, use 0 to unlimit)")
		#print("")
		#print(" swarm execution options:")
		#print("   -E,--execution-mode<X>          	execution method for analyzing instances (sequential, parallel, default: parallel)")
		#print("   --verifiers<X>                  	number of cores used in parallel for verification backends (default: 4)")
		#print("   --incremental                    automatically launch swarm new timeout=2*initial-timeout")
		#print("   --split-config<X>              	incrementally generate config file for <X> instances  and start verification immediately")
		#print("   --bag-size<X>                   	number of instances in each partial config file (default: 100)")
		#print("")
		#print(" miscellaneous options:")
		#print("   --svcomp                        	svcomp mode")
		#print("   --explode-pc                    	do not use array for program counter")
		#print("   --main-argc<X>                   argc argument for main function (default: 1)")
		#print("   --main-argv<X>                   argv argument for main function (default: \"program\")")
		#print("   --keepstaticarray               	keep static array, do not change to pointer version")
		#print("   --donotcheckvisiblepointer      	do not check visible statement causes by pointer")
		print("")

	if errormsg:
		print(errormsg + "\n")

def main(args):
	cmd = args[0]
	cmdline = os.path.dirname(sys.argv[0]) + "/"
	from bin import config
	cmdline += config.relpath["translator"]
	cmdline += " --vs" 
	for argument in args[1:]:
		if "-h" in argument:
			usage(cmd)
			print("======================================================================================")
			os.system(cmdline + " -h")
			sys.exit(0)
		if "-H" in argument:	
			usage(cmd)
			print("======================================================================================")
			os.system(cmdline + " -H")
			sys.exit(0)
		cmdline += " %s" % argument
	os.system(cmdline)
	sys.exit(0)


if __name__ == "__main__":
	main(sys.argv[0:])
