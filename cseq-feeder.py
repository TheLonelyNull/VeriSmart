#!/usr/bin/env python

""" CSeq C Sequentialization Framework
	command-line front-end
	maintained by Truc Nguyen Lam, Univerisity of Southampton
"""
FRAMEWORK_VERSION = "CSeq-Feeder-1.3.1"
FRAMEWORK_VERSION = "CSeq-Feeder-1.3.2-2021.02.02"
"""

"""

"""
Description:
	Feeder for:
	Lazycseq-1.0-2021.02.02
	VeriSmart-1.2-2021.02.02

TODO:
	-

Changelog:
	2016.08.14  Initial version
"""
import builtins
import getopt
import glob
import importlib
import os.path
import shutil
import sys
import time
import traceback
from tempfile import NamedTemporaryFile
from pycparser.plyparser import ParseError
import core.config
import core.merger
import core.module
import core.parser
import core.utils


class cseqenv:
	cmdline = None						# full command-line
	opts = None							# command-line option-value pairs

	args = None         				#
	params = []         				# additional front-end input parameters
	paramIDs = []       				# parameters ID only
	paramvalues = {}    				# param values indexed by param ID
	debug = False       				# verbosity level
	showsymbols = False
	chainfile = None    				# file with the sequence of modules to execute
	inputfile = None    				# input source file to process
	includepath = None  				# #include path (for source merging)
	outputfile = None   				# TODO not implemented yet
	modules = []        				# modules (each performing a single code trasformation)
	transforms = 0      				# no. of modules executed so far
	maps = []
	lastlinenoinlastmodule = 0
	outputtofiles = []    				# map from merged sources (= Merger"s output) to original source file
	premodules = []
	aftermodules = []
	backendmodules = []
	savecommand = {}
	loadcommand = {}	
	cex = False
	cex_dir = ""				
	witness = ""
	seq_only = False
	backend = "cbmc"
	depth = 0							# backend depth bound (if supported by backend, default: no bound)
	error_label = "ERROR"
	clang_path = ""
	backend_path = ""					# path to clang (or llvm-gcc) binary (only for -b klee and -b llbmc)
	domain = "default"
	extra_args = ""						# extra arguments for backends

	# Unwind bound
	softunwindbound = False
	unwind = 1
	whileunwind = 0
	forunwind = 0
	soft_unwind_max = 0	

	# Threads and rounds
	max_threads = 0
	rounds = 1
	timelimit = 86400
	memorylimit = -1   					# no limit
	preprocessed = False
	headerfile = ""
	chain = ""
	force_chain = False
	
	# Swarm
	isSwarm = False
	cores = 4
	show_cs = False 					# show number of context switches for each thread
	config_file = ""					# TODO swarm verification with manual tiling configuration file
	initial_timeout = 3600 				 
	automatic = True
	instances_limit = 100
	window_length = 1
	picked_window = 1
	soft_limit = 0
	hard_limit = 0 						# must stay 0
	keep_logs = False
	split_config = False

	# RTOS
	oil = ""                 	# OIL description file
	sched = "default"        	# Scheduling type
	suffix = ""              	# suffix for swarm directory
	archive = True          	# suffix for swarm directory
	archive = False          	# suffix for swarm directory
	config_only = False      	# only generate configuration files
	cluster_config = 0       	# generate cluster of configuration files of given size
	swarm_translator = ""    	# only generate configuration files
	scatter = False          	# scatter context switch points
	shifted_window = False	
	percentage = False
	window_percent = -1
	skip_thread = {}
	stop_on_fail = True
	exit_on_error = False
	no_random = False
	start_sample = 0

	# For CBMC backend
	bounds_check = False
	div_by_zero_check = False
	pointer_check = False
	memory_leak_check = False
	signed_overflow_check = False
	unsigned_overflow_check = False
	float_overflow_check = False
	nan_check = False
	no_simplify = False
	refine_arrays = False

	inlineInfix = '$$$$'  # S: placeholder to insert counter value in function inlining, see varname.py and inliner.py

def parseChainCommand(s):
	ret = {}
	l = s.split()
	for i in l:
		pair = i.split("=")
		if len(pair) != 2:
			print("Load file error (%s):\n" % s)
			sys.exit(1)
		ret[pair[0]] = pair[1]

	return ret

def moduleparamusage(p):
	abc = "--%s" % (p.id)
	abc += " <%s>" % p.datatype if p.datatype else ""
	opt = "optional" if p.optional else ""
	opt += ", " if p.optional and p.default else ""
	opt += "default:%s%s%s" % (core.utils.colors.HIGHLIGHT, p.default, core.utils.colors.NO) if p.default else ""
	opt = "(%s)" % opt if len(opt) > 0 else opt
	desc = ("\n    " + " " * 26).join([l for l in p.description.split("\n")])  # multiline description
	return "%-33s %s %s" % (abc, desc, opt)

def usage(cmd, errormsg, showhelp=True, detail=False, isSwarm=False):
	if showhelp:
		print("")
		print("  CSeq Feeder | January 2021  ")
		print("")
		print("Usage: ")
		print("")
		print("   %s -h [-l <config>]" % cmd)
		print("   %s -i <input.c> [options]" % cmd)
		print("")
		print("configuration options: ")
		print("   -l,--load=<file>                  configuration to use (default:%s%s%s)" % (core.utils.colors.HIGHLIGHT, core.config.defaultchain, core.utils.colors.NO))
		print("   -L,--list-configs                 show available configurations")
		print("")
		print("input options:")
		print("   -i,--input=<file>                 input filename")
		print("   -I,--include=<path>               include search path (use : as a separator) (default:%s./%s)" % (core.utils.colors.HIGHLIGHT, core.utils.colors.NO))
		print("")
		print("verification option:")
		print("   -b,--backend=<fmt>                backend verification tool (default: cbmc, use --list-backends for more details)")
		print("   --backend-path=<path>             custom path to backend executable file") # does it "(requires -b, --backend)"?
		print("   --backend-clang-path=<path>       path to clang (or llvm-gcc) binary (only for -b klee and -b llbmc)")
		print("   -a,--extra-args<X>                extra arguments for backends")
		print("   -d,--depth<X>                     backend depth bound (if supported by backend, default: no bound)")
		print("   --timeout<X>                      timeout for each verification process (default: 3600)")
		print("   --cex                             enable counterexample generation (if supported by backend)")
		print("   --cex-dir<X>                      counterexample output directory (default: FILE-counterexample)")
		print("")
		print("CBMC-specific options (requires -b cbmc):")
		print("   --stop-on-fail                    stop when the first error is found")
		print("   --bounds-check                    enable array bounds checks (optional)")
		print("   --div-by-zero-check               enable division by zero checks (optional)")
		print("   --pointer-check                   enable pointer checks (optional)")
		print("   --memory-leak-check               enable memory leak checks (optional)")
		print("   --signed-overflow-check           enable arithmetic over- and underflow checks of signed integer (optional)")
		print("   --unsigned-overflow-check         enable arithmetic over- and underflow checks of unsigned integer (optional)")
		print("   --float-overflow-check            check floating-point for +/-Inf (optional)")
		print("   --nan-check                       check floating-point for NaN (optional)")
		print("   --no-simplify                     no simplification from cbmc (optional)")
		print("   --refine-arrays                   array refinement from cbmc (optional)")
		print("   --overflow-check                  enable arithmetic over- and underflow check (optional)")
		# Module-specific params for the given chain (or for the default one)
		print("")
		print("module options:")

		outputparamssofar = []   # used to check which module input params are front-end input
		inputparamssofar = []

		for m in cseqenv.modules + cseqenv.aftermodules:
			if detail:
				print("  [%s]" % m.getname())
				if len(m.inputparamdefs) == len(m.outputparamdefs) == 0:
					print("")

			try:
				if detail:
					if len(m.inputparamdefs) > 0:
						print("     input:")

				for p in m.inputparamdefs:
					if (p.id not in [q.id for q in outputparamssofar] and
							p.id not in [q.id for q in inputparamssofar]):
						inputparamssofar.append(p)
						print("   " + moduleparamusage(p))
					elif detail:
						print("  (" + moduleparamusage(p) + ")")

				if detail and len(m.inputparamdefs) > 0:
					print("")

				if detail:
					if len(m.outputparamdefs) > 0:
						print("     output:")

				for p in m.outputparamdefs:
					outputparamssofar.append(p)
					if detail:
						abc = "--%s" % (p.id)
						print("   %-33s %s" % (abc, p.description))

				if detail and len(m.outputparamdefs) > 0:
					print("")

			except Exception as e:
				print("Module error %s:\n%s.\n" % (m.getname(), str(e)))
				traceback.print_exc(file=sys.stdout)
				sys.exit(1)

		print("")
		print("other options: ")
		print("   -h, --help                        show help")
		print("   -H, --detailedhelp                show detailed configuration-specific help")
		print("   -v  --version                     show version number")
		print("")

	if errormsg:
		print(errormsg + "\n")
		sys.exit(1)

	sys.exit(0)

def listmodulechains():
	list = ""
	for filename in glob.glob("modules/*.chain"):
		list += filename[len("modules/"):-len(".chain")] + ", "
	if list.endswith(", "):
		list = list[:-2]
	return list

def main():

	"""                   """
	""" I. Initialisation """
	"""                   """
	cseqenv.cmdline = sys.argv
	cseqenv.starttime = time.time()    # save wall time

	# Extract the configuration from the command-line or set it to the default.
	cseqenv.chainname = core.utils.extractparamvalue(cseqenv.cmdline, "-c", "--conf", core.config.defaultchain)
	cseqenv.chainfile = "modules/%s.chain" % core.utils.extractparamvalue(cseqenv.cmdline, "-c", "--conf", core.config.defaultchain)

	if not core.utils.fileExists(cseqenv.chainfile):
		usage(cseqenv.cmdline[0], "error: unable to open configuration file (%s)" % cseqenv.chainfile, showhelp=False)

	temporaryfile = NamedTemporaryFile()
	loadtype = 0   # normal

	# Import all modules in the current configuration.
	for modulename in core.utils.printFile(cseqenv.chainfile).splitlines():
		if not modulename.startswith("#") and len(modulename) >= 1:
			modulename = modulename.strip()
			loadtype = 0

			if modulename.startswith("@save"):
				cseqenv.savecommand = parseChainCommand(modulename.replace("@save", "").strip())
				continue

			if modulename.startswith("@load"):
				cseqenv.loadcommand = parseChainCommand(modulename.replace("@load", "").strip())
				continue

			if modulename.startswith("@pre"):
				modulename = modulename.replace("@pre", "").strip()
				loadtype = 1  # pre

			if modulename.startswith("@after"):
				modulename = modulename.replace("@after", "").strip()
				loadtype = 2  # after

			if modulename.startswith("@backend"):
				modulename = modulename.replace("@backend", "").strip()
				loadtype = 3  # backend


			try:
				mod = importlib.import_module("modules." + modulename)
				if loadtype == 0:
					cseqenv.modules.append(getattr(mod, modulename)())
				elif loadtype == 1:
					cseqenv.premodules.append(getattr(mod, modulename)())
				elif loadtype == 2:
					cseqenv.aftermodules.append(getattr(mod, modulename)())
				elif loadtype == 3:
					cseqenv.backendmodules.append(getattr(mod, modulename)())
			except ImportError as e:
				print("Unable to import module %s,\nplease check installation.\n" % modulename)
				traceback.print_exc(file=sys.stdout)
				sys.exit(1)
			except AttributeError as e:
				print("Unable to load module %s,\nplease check that the module filename,\n"
					  "the entry in the chain-file, and\nthe top-level classname in the module correctly match.\n" % modulename)
				traceback.print_exc(file=sys.stdout)
				sys.exit(1)
			except Exception as e:
				print("Unable to initialise module %s:\n%s.\n" % (modulename, str(e)))
				traceback.print_exc(file=sys.stdout)
				sys.exit(1)

	# Init modules.
	for m in cseqenv.modules:
		try:
			if "init" in dir(m):
				m.init()
		except Exception as e:
			print("Unable to initialise module %s:\n%s.\n" % (m.getname(), str(e)))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)

	# Init pre modules.
	for m in cseqenv.premodules:
		try:
			if "init" in dir(m):
				m.init()
		except Exception as e:
			print("Unable to initialise module %s:\n%s.\n" % (m.getname(), str(e)))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)

	# Init after modules.
	for m in cseqenv.aftermodules:
		try:
			if "init" in dir(m):
				m.init()
		except Exception as e:
			print("Unable to initialise module %s:\n%s.\n" % (m.getname(), str(e)))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)

	# Init backend modules.
	for m in cseqenv.backendmodules:
		try:
			if "init" in dir(m):
				m.init()
		except Exception as e:
			print("Unable to initialise module %s:\n%s.\n" % (m.getname(), str(e)))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)

	# Init module parameters.
	#
	# Modules can have input and output parameters.
	# Any module input that is not the output of a previous module
	# is a front-end parameter
	# (it is displayed in the usage() screen, and
	#  it can be provided to the front-end in the command-line)
	inParams = []      # module-specific input parameters seen so far
	inParamIDs = []
	inparamvalues = {}

	outParams = []     # module-specific output parameters seen so far
	outParamIDs = []
	outparamvalues = {}

	for m in cseqenv.modules + cseqenv.aftermodules + cseqenv.backendmodules:
		try:
			for p in m.inputparamdefs:  # global input params seen so far
				if p.id not in inParamIDs:
					inParamIDs.append(p.id)
					inParams.append(p)

				# if the input param  p  is new and
				# no previous module generates it
				# (i.e., it is not an output param for any previous module)
				# then it needs to be a global (front-end) input
				if p.id not in outParamIDs:
					cseqenv.paramIDs.append(p.id)
					cseqenv.params.append(p)

			for p in m.outputparamdefs:  # output params seen so far
				if p.id not in outParamIDs:
					outParamIDs.append(p.id)
					outParams.append(p)
		except Exception as e:
			print("Unable to initialise module %s:\n%s.\n" % (m.getname(), str(e)))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)

	"""                """
	""" II. Parameters """
	"""                """
	try:
		shortargs = "hHvDLSdI:i:c:su:w:f:U:YT:M:l:p:b:a:d:"
		longargs = ["help", "detailedhelp", "version", "debug", "list-configs", "showsymbols",
					"detail", "include=", "input=", "config-file", "softunwindbound", "unwind=",
					"unwind-while=", "unwind-for=", "--soft-unwind-max=",

					#Verismart
					"vs", "contextswitch", "suffix=", "config-only", "cores=", "timelimit=", "memorylimit=",
					"window-length=", "window-percent=", "picked-window=", "shift-window", "instances-limit=",
					
					"exit-on-error", "backend=", "backend-path=", "backend-clang-path=", "extra-args=",
					"depth=", "timeout=", "cex", "cex-dir=",

					#Backend
					"stop-on-fail", "bounds-check", "div-by-zero-check", "pointer-check", "memory-leak-check",
					"signed-overflow-check", "unsigned-overflow-check", "float-overflow-check", "nan-check",
					"no-simplify", "refine-arrays", ] # <-- append module params here

		# add one command-line parameter for each module-specific parameter
		for p in cseqenv.params:
			longargs.append("%s%s" % (p.id, "" if p.isflag() else "="))

		cseqenv.opts, cseqenv.args = getopt.getopt(sys.argv[1:], shortargs, longargs)
	except getopt.GetoptError as err:
		usage(cseqenv.cmdline[0], "error: " + str(err))

	for o, a in cseqenv.opts:
		if o in ("-h", "--help"):
			usage(cseqenv.cmdline[0], "")
		elif o in ("-H", "--detailedhelp"):
			usage(cseqenv.cmdline[0], "", detail=True)
		elif o in ("-v", "--version"):
			print(FRAMEWORK_VERSION)
			sys.exit()
		elif o in ("-D", "--debug"):
			cseqenv.debug = True
		elif o in ("-L", "--list-configs"):
			print(listmodulechains())
			sys.exit()
		elif o in ("-S", "--showsymbols"):
			cseqenv.showsymbols = True
		elif o in ("-d", "--detail"):
			detail = True
		elif o in ("-I", "--include"):
			cseqenv.includepath = a
		elif o in ("-i", "--input"):
			cseqenv.inputfile = a
		elif o in ("-c", "--config-file"):
			cseqenv.automatic = False
			cseqenv.config_file = a

		#Unwind
		elif o in ("-s", "--softunwindbound"):
			cseqenv.softunwindbound = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("-u", "--unwind"):
			cseqenv.unwind = int(a)
			cseqenv.paramvalues[o[2:]] = int(a)
		elif o in ("-w", "--while-unwind", "--unwind-while"):
			cseqenv.whileunwind = int(a)
			cseqenv.paramvalues[o[2:]] = int(a)
		elif o in ("-f", "--for-unwind", "--unwind-for"):
			cseqenv.forunwind = int(a)
			cseqenv.paramvalues[o[2:]] = int(a)
		elif o in ("-U", "--soft-unwind-max", "--unwind-for-max"):
			cseqenv.soft_unwind_max = int(a)
			cseqenv.paramvalues[o[2:]] = int(a)

		#Verismart
		elif o in ("--vs"):
			cseqenv.isSwarm = True
		elif o in ("-Y", "--contextswitch"):
			cseqenv.show_cs = True
		elif o in ("--suffix"):
			cseqenv.suffix = a
		elif o in ("--config-only"):
			cseqenv.config_only = True
		elif o in ("--cores"):
			cseqenv.cores = int(a)
		elif o in ("-T", "--timelimit"):
			cseqenv.timelimit = int(a)
		elif o in ("-M", "--memorylimit"):
			cseqenv.memorylimit = int(a)
		elif o in ("-l", "--window-length"):
			cseqenv.window_length = int(a)
		elif o in ("-p", "--picked-window"):
			cseqenv.picked_window = int(a)
		elif o in ("--window-percent"):
			cseqenv.percentage = True
			cseqenv.window_percent = int(a)
		elif o in ("--shift-window"):
			cseqenv.shifted_window = True
		elif o in ("--instances-limit"):
			cseqenv.instances_limit = int(a)
		
		elif o in ("--exit-on-error"):
			cseqenv.exit_on_error = True
		elif o in ("-b", "--backend"):
			cseqenv.backend = a
			cseqenv.paramvalues[o[2:]] = a
		elif o in ("--backend-path"):
			cseqenv.backend_path = a
		elif o in ("--backend-clang-path"):
			cseqenv.clang_path = a
		elif o in ("-a", "--extra-args"):
			cseqenv.extra_args = a
		elif o in ("-d", "--depth"):
			cseqenv.depth = int(a)
			cseqenv.paramvalues[o[2:]] = a
		elif o in ("--timeout"):
			cseqenv.initial_timeout = int(a)
			cseqenv.paramvalues["time"] = int(a)
		elif o in ("--cex"):
			cseqenv.cex = True
		elif o in ("--cex-dir"):
			cseqenv.cex_dir = a
		
		elif o in ("--stop-on-fail "):
			cseqenv.stop_on_fail = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--bounds-check"):
			cseqenv.bounds_check = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--div-by-zero-check "):
			cseqenv.div_by_zero_check = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--pointer-check "):
			cseqenv.pointer_check = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--memory-leak-check"):
			cseqenv.memory_leak_check = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--signed-overflow-check"):
			cseqenv.signed_overflow_check = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--unsigned-overflow-check"):
			cseqenv.unsigned_overflow_check = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--float-overflow-check "):
			cseqenv.float_overflow_check = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--nan-check"):
			cseqenv.nan_check = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--no-simplify"):
			cseqenv.no_simplify = True
			cseqenv.paramvalues[o[2:]] = True
		elif o in ("--refine-arrays"):
			cseqenv.refine_arrays = True
			cseqenv.paramvalues[o[2:]] = True

		else:  # module-specific parameters
			cseqenv.paramvalues[o[2:]] = a

	# Basic parameter check.
	if not cseqenv.inputfile:
		usage(cseqenv.cmdline[0], "error: input file name not specified.")
	if not core.utils.fileExists(cseqenv.inputfile):
		usage(cseqenv.cmdline[0], "error: unable to open input file (%s)" % cseqenv.inputfile, showhelp=False)
	if not core.utils.fileExists(cseqenv.chainfile):
		usage(cseqenv.cmdline[0], "error: unable to open module-chain file (%s)" % cseqenv.chainfile, showhelp=False)

	# All global parameters (calculated above) should be in the command-line.
	for p in cseqenv.params:
		if not p.optional and not p.default:
			usage(cseqenv.cmdline[0], "error: %s (option --%s) not specified." % (p.description, p.id))

	# Debug setup.
	cseqenv.debugpath = core.config.debugpath
	if not os.path.exists(core.config.debugpath):
		os.makedirs(core.config.debugpath)
	elif cseqenv.debug:
		shutil.rmtree(core.config.debugpath)
		os.makedirs(core.config.debugpath)

	"""              """
	""" III. Merging """
	"""              """

	# Load the input file.
	input = core.utils.printFileRows(cseqenv.inputfile)

	# Patch for SVCOMP2016 .i file
	if cseqenv.inputfile.endswith(".i") and core.utils.isPreprocessed(cseqenv.inputfile):
		input = core.utils.stripIfNeeded(cseqenv.inputfile)[1]
		cseqenv.inputfile = cseqenv.inputfile[:-2] + ".c"
		core.utils.saveFile(cseqenv.inputfile, input)

	# Merge all the source files into a single string.
	try:
		cseqenv.moduleID = "merger"

		Merger = core.merger.Merger()
		Merger.loadfromstring(input, cseqenv)
		output = Merger.getoutput()
		cseqenv.transforms += 1

		if cseqenv.debug:
			core.utils.saveFile("%s/_000_input___merger.c" % core.config.debugpath, input)
			core.utils.saveFile("%s/_000_marked__merger.c" % cseqenv.debugpath, Merger.markedoutput)
			core.utils.saveFile("%s/_000_output__merger.c" % core.config.debugpath, output)
			core.utils.saveFile("%s/_000_linemap__merger.c" % core.config.debugpath, Merger.getlinenumbertable())

	except ParseError as e:
		print("Parse error (%s):\n" % str(e))
		print("%s%s%s" % (core.utils.colors.HIGHLIGHT, core.utils.snippet(output, Merger.getLineNo(e), Merger.getColumnNo(e), 5, True), core.utils.colors.NO))
		sys.exit(1)
	except builtins.SystemExit as e:  # the module invoked sys.exit()
		sys.exit(1)
	except:
		traceback.print_exc(file=sys.stdout)
		sys.exit(1)

	#
	if cseqenv.showsymbols:
		Parser = core.parser.Parser()
		Parser.loadfromstring(output)
		Parser.ast.show()
		sys.exit(0)

	"""                    """
	""" IV. Transformation """
	"""                    """

	cseqenv.maps.append(Merger.outputtoinput)
	cseqenv.outputtofiles = Merger.outputtofiles

	# Run all modules in a sequence
	for cseqenv.transforms, m in enumerate(cseqenv.modules):
		try:
			timeBefore = time.time()
			if cseqenv.debug:
				print("/* " + m.getname())
			m.initParams(cseqenv)
			m.loadfromstring(output, cseqenv)
			output = m.getoutput()

			if "inputtooutput" in dir(m):   # linemapping only works on Translator (C-to-C) modules
				cseqenv.maps.append(m.outputtoinput)
				cseqenv.lastlinenoinlastmodule = m.output.count("\n")

			if cseqenv.debug:
				fileno = "0" + str(cseqenv.transforms + 1).zfill(2)
				core.utils.saveFile("%s/_%s_input___%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.input)
				core.utils.saveFile("%s/_%s_output__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.output)
				try:
					# core.utils.saveFile("%s/_%s_ast__%s.c" % (cseqenv.debugpath,fileno,m.getname()), str(m.Parser.ast.show()))
					core.utils.saveFile("%s/_%s_symbols__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.Parser.printsymbols())
				except AttributeError:
					pass
				print("[%s] ok %0.2fs */" % (fileno, int(time.time()) - int(timeBefore)))
				sys.stdout.flush()

			if cseqenv.debug and "markedoutput" in dir(m):  # current module is a Translator
				core.utils.saveFile("%s/_%s_marked__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.markedoutput)
				core.utils.saveFile("%s/_%s_linemap__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.getlinenumbertable())

		except ParseError as e:
			print("Parse error (%s) while performing %s->%s:\n" % (str(e),
																   cseqenv.modules[cseqenv.transforms - 1].getname() if cseqenv.transforms > 0 else "", cseqenv.modules[cseqenv.transforms].getname()))
			print("%s%s%s" % (core.utils.colors.HIGHLIGHT, core.utils.snippet(output, m.getLineNo(e), m.getColumnNo(e), 5, True), core.utils.colors.NO))
			sys.exit(1)
		except core.module.ModuleParamError as e:
			print("Module error (%s).\n" % (str(e)))
			sys.exit(1)
		except core.module.ModuleError as e:
			print("Error from %s module: %s.\n" % (cseqenv.modules[cseqenv.transforms].getname(), str(e)[1:-1]))
			sys.exit(1)
		except KeyboardInterrupt as e:
			sys.exit(1)
		except ImportError as e:
			print("Import error (%s),\nplease re-install the tool.\n" % str(e))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)
		except Exception as e:
			print("Error while performing %s->%s:\n"
				  % (cseqenv.modules[cseqenv.transforms - 1].getname() if cseqenv.transforms > 0 else "", cseqenv.modules[cseqenv.transforms].getname()))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)


	cachedOutput = output
	# For the sack of preanalysis
	temporaryfile = NamedTemporaryFile()

	# save environment if there is save and log
	cachedparams = {}
	for item in cseqenv.savecommand:
		if item == "backend" and item not in cseqenv.paramvalues:
			cseqenv.paramvalues[item] = "cbmc"
		if item == "rounds" and item in cseqenv.paramvalues and int(cseqenv.paramvalues[item]) > 1:
			cseqenv.savecommand[item] = cseqenv.paramvalues[item]
		if item in cseqenv.paramvalues:
			cachedparams[item] = cseqenv.paramvalues[item]

	# Set environment for pre-module if applicable
	for item in cseqenv.savecommand:
		if cseqenv.savecommand[item] == "tempfile":
			cseqenv.paramvalues[item] = temporaryfile.name
		else:
			cseqenv.paramvalues[item] = cseqenv.savecommand[item]

	# Pre-modules
	timepremodules = time.time()
	output = cachedOutput

	for cseqenv.transforms, m in enumerate(cseqenv.premodules):
		try:
			timeBefore = time.time()
			if cseqenv.debug:
				print("/* " + m.getname(), m.initParams(cseqenv))
			m.loadfromstring(output, cseqenv)
			output = m.getoutput()

			if cseqenv.debug:
				fileno = "1" + str(cseqenv.transforms + 1).zfill(2)
				core.utils.saveFile("%s/_%s_input___%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.input)
				core.utils.saveFile("%s/_%s_output__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.output)
				try:
					# core.utils.saveFile("%s/_%s_ast__%s.c" % (cseqenv.debugpath,fileno,m.getname()), str(m.Parser.ast.show()))
					core.utils.saveFile("%s/_%s_symbols__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.Parser.printsymbols())
				except AttributeError:
					pass
				print("[%s] ok %0.2fs */" % (fileno, int(time.time()) - int(timeBefore)))
				sys.stdout.flush()

			if cseqenv.debug and "markedoutput" in dir(m):  # current module is a Translator
				core.utils.saveFile("%s/_%s_marked__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.markedoutput)
				core.utils.saveFile("%s/_%s_linemap__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.getlinenumbertable())

		except ParseError as e:
			print("Parse error (%s) while performing %s->%s:\n" % (str(e),
																   cseqenv.premodules[cseqenv.transforms - 1].getname() if cseqenv.transforms > 0 else "", cseqenv.premodules[cseqenv.transforms].getname()))
			print("%s%s%s" % (core.utils.colors.HIGHLIGHT, core.utils.snippet(output, m.getLineNo(e), m.getColumnNo(e), 5, True), core.utils.colors.NO))
			sys.exit(1)
		except core.module.ModuleParamError as e:
			print("Module error (%s).\n" % (str(e)))
			sys.exit(1)
		except core.module.ModuleError as e:
			print("Error from %s module: %s.\n" % (cseqenv.premodules[cseqenv.transforms].getname(), str(e)[1:-1]))
			sys.exit(1)
		except KeyboardInterrupt as e:
			sys.exit(1)
		except ImportError as e:
			print("Import error (%s),\nplease re-install the tool.\n" % str(e))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)
		except Exception as e:
			print("Error while performing %s->%s:\n"
				  % (cseqenv.premodules[cseqenv.transforms - 1].getname() if cseqenv.transforms > 0 else "", cseqenv.premodules[cseqenv.transforms].getname()))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)

	# After-modules
	# remove added parameter
	for item in cseqenv.savecommand:
		if item in cseqenv.paramvalues:
			del cseqenv.paramvalues[item]

	# restore cached parameter
	for item in cachedparams:
		cseqenv.paramvalues[item] = cachedparams[item]

	# load new parameter
	for item in cseqenv.loadcommand:
		if item.startswith("env."):  # which mean the environment gonna be set
			attri = item.replace("env.", "")
			if cseqenv.loadcommand[item] == "<get_time>":
				setattr(cseqenv, attri, time.time() - timepremodules)
			else:
				setattr(cseqenv, attri, cseqenv.loadcommand[item])
		else:
			if cseqenv.loadcommand[item] == "tempfile":
				cseqenv.paramvalues[item] = temporaryfile.name

	temporaryfile.close()

	for cseqenv.transforms, m in enumerate(cseqenv.aftermodules):
		try:
			timeBefore = time.time()
			if cseqenv.debug:
				print("/* " + m.getname(), m.initParams(cseqenv))
			m.loadfromstring(output, cseqenv)
			output = m.getoutput()

			if "inputtooutput" in dir(m):  # linemapping only works on Translator (C-to-C) modules
				cseqenv.maps.append(m.outputtoinput)
				cseqenv.lastlinenoinlastmodule = m.output.count("\n")

			if cseqenv.debug:
				fileno = "2" + str(cseqenv.transforms + 1).zfill(2)
				core.utils.saveFile("%s/_%s_input___%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.input)
				core.utils.saveFile("%s/_%s_output__%s.c" % (cseqenv.debugpath, fileno, m.getname()), m.output)
				try:
					# core.utils.saveFile("%s/_%s_ast__%s.c" % (cseqenv.debugpath,fileno,m.getname()), str(m.Parser.ast.show()))
					core.utils.saveFile("%s/_%s_symbols__%s.c" % (cseqenv.debugpath, fileno, m.getname()),
										m.Parser.printsymbols())
				except AttributeError:
					pass
				print("[%s] ok %0.2fs */" % (fileno, int(time.time()) - int(timeBefore)))
				sys.stdout.flush()

			if cseqenv.debug and "markedoutput" in dir(m):  # current module is a Translator
				core.utils.saveFile("%s/_%s_marked__%s.c" % (cseqenv.debugpath, fileno, m.getname()),
									m.markedoutput)
				core.utils.saveFile("%s/_%s_linemap__%s.c" % (cseqenv.debugpath, fileno, m.getname()),
									m.getlinenumbertable())

		except ParseError as e:
			print("Parse error (%s) while performing %s->%s:\n"
				  % (
				  str(e), cseqenv.aftermodules[cseqenv.transforms - 1].getname() if cseqenv.transforms > 0 else "",
				  cseqenv.aftermodules[cseqenv.transforms].getname()))
			print("%s%s%s" % (
			core.utils.colors.HIGHLIGHT, core.utils.snippet(output, m.getLineNo(e), m.getColumnNo(e), 5, True),
			core.utils.colors.NO))
			sys.exit(1)
		except core.module.ModuleParamError as e:
			print("Module error (%s).\n" % (str(e)))
			sys.exit(1)
		except core.module.ModuleError as e:
			print(
				"Error from %s module: %s.\n" % (cseqenv.aftermodules[cseqenv.transforms].getname(), str(e)[1:-1]))
			sys.exit(1)
		except KeyboardInterrupt as e:
			sys.exit(1)
		except ImportError as e:
			print("Import error (%s),\nplease re-install the tool.\n" % str(e))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)
		except Exception as e:
			print("Error while performing %s->%s:\n"
				  % (cseqenv.aftermodules[cseqenv.transforms - 1].getname() if cseqenv.transforms > 0 else "",
					 cseqenv.aftermodules[cseqenv.transforms].getname()))
			traceback.print_exc(file=sys.stdout)
			sys.exit(1)

		temporaryfile.close()
		sys.exit(0)

if __name__ == "__main__":
	main()
