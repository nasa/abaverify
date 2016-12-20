"""
This is the main API for the abaverify package.
"""
import unittest
from optparse import OptionParser
import sys
import platform
import os
import re
import shutil
import subprocess
import contextlib
import itertools as it
import time
import inspect

#
# Local
#

class measureRunTimes:
	"""
	Measures run times during unit tests
	"""

	def __init__(self):
		self.runtimes = dict()


	def processLine(self, line):
		""" Helper function to mark the start and end times """

		if re.match(r'Begin Linking', line):
			self.Compile_start = time.time()
		elif re.match(r'End Linking', line):
			self.Compile_end = time.time()
			self.compile_time = self.Compile_end - self.Compile_start
			sys.stderr.write("\nCompile run time: {:.2f} s\n".format(self.compile_time))

		elif re.match(r'Begin Abaqus/Explicit Packager', line):
			self.packager_start = time.time()
		elif re.match(r'End Abaqus/Explicit Packager', line):
			self.packager_end = time.time()
			self.package_time = self.packager_end - self.packager_start
			sys.stderr.write("Packager run time: {:.2f} s\n".format(self.package_time))

		elif re.match(r'Begin Abaqus/Explicit Analysis', line):
			self.solver_start = time.time()
		elif re.match(r'End Abaqus/Explicit Analysis', line) or re.match(r'.*Abaqus/Explicit Analysis exited with an error.*', line):
			self.solver_end = time.time()
			self.solver_time = self.solver_end - self.solver_start
			sys.stderr.write("Solver run time: {:.2f} s\n".format(self.solver_time))


#
# Public facing API
#

class TestCase(unittest.TestCase):
	"""
	Base test case. Includes generic functionality to run tests on abaqus models.
	"""

	def tearDown(self):
		"""
		Removes Abaqus temp files. This function is called by unittest.
		"""
		files = os.listdir(os.getcwd())
		patterns = [re.compile('.*abaqus.*\.rpy.*'), re.compile('.*abaqus.*\.rec.*'), re.compile('.*pyc')]
		[os.remove(f) for f in files if any(regex.match(f) for regex in patterns)]


	def runTest(self, jobName):
		"""
		Generic test method
		"""

		# Save output to a log file
		with open(os.path.join(os.getcwd(), 'testOutput', jobName + '.log'), 'w') as f:

			# Time tests
			if options.time:
				timer = measureRunTimes()
			else:
				timer = None

			# Execute the solver
			if not options.useExistingResults:
				self.runModel(jobName=jobName, f=f, timer=timer)

			# Execute process_results script load ODB and get results
			pathForThisFile = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
			if not os.path.isfile(os.path.join(os.getcwd(), 'testOutput', jobName + '.odb')):
				raise Exception("Error: Abaqus odb was not generated. Check the log file in the testOutput directory.")
			pathForProcessResultsPy = '"' + os.path.join(pathForThisFile, 'processresults.py') + '"'
			self.callAbaqus(cmd=options.abaqusCmd + ' cae noGUI=' + pathForProcessResultsPy + ' -- -- ' + jobName, log=f, timer=timer)

		# Run assertions
		self.runAssertionsOnResults(jobName)


	def runModel(self, jobName, f, timer):
		"""
		Logic to submit the abaqus job
		"""

		# Platform specific file extension for user subroutine
		if not options.precompileCode:
			if (platform.system() == 'Linux'):
				subext = '.f'
			else:
				subext = '.for'
			userSubPath = os.path.join(os.getcwd(), options.relPathToUserSub + subext)

		# Copy input deck
		shutil.copyfile(os.path.join(os.getcwd(), jobName + '.inp'), os.path.join(os.getcwd(), 'testOutput', jobName + '.inp'))

		# build abaqus cmd
		cmd = options.abaqusCmd + ' job=' + jobName
		if not options.precompileCode:
			cmd += ' user="' + userSubPath + '"'
		if options.cpus > 1:
			cmd += ' cpus=' + str(options.cpus)
		cmd += ' double=both interactive'

		# Copy parameters file, if it exists
		parameterName = 'CompDam.parameters'
		parameterPath = os.path.join(os.getcwd(), parameterName)
		if os.path.exists(parameterPath):
			shutil.copyfile(parameterPath, os.path.join(os.getcwd(), 'testOutput', parameterName))

		# Run the test from the testOutput directory
		os.chdir(os.path.join(os.getcwd(), 'testOutput'))
		self.callAbaqus(cmd=cmd, log=f, timer=timer)

		os.chdir(os.pardir)


	def runAssertionsOnResults(self, jobName):
		"""
		Runs assertions on each result in the jobName_results.py file
		"""

		outputFileName = jobName + '_results.py'
		outputFileDir = os.path.join(os.getcwd(), 'testOutput')
		if (os.path.isfile(os.path.join(outputFileDir, outputFileName))):
			sys.path.insert(0, outputFileDir)
			results = __import__(outputFileName[:-3]).results

			for r in results:

				# Loop through values if there are more than one
				if hasattr(r['computedValue'], '__iter__'):
					for i in range(0, len(r['computedValue'])):
						self.assertAlmostEqual(r['computedValue'][i], r['referenceValue'][i], delta=r['tolerance'][i])

				else:
					if "tolerance" in r:
						self.assertAlmostEqual(r['computedValue'], r['referenceValue'], delta=r['tolerance'])
					elif "referenceValue" in r:
						self.assertEqual(r['computedValue'], r['referenceValue'])
					else:
						# No data to compare with, so pass the test
						pass
		else:
			self.fail('No results file provided by process_results.py')


	def callAbaqus(self, cmd, log, timer=None, shell=True):
		"""
		Logic for calls to abaqus. Support streaming the output to the log file.
		"""

		p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, shell=shell)

		# Parse output lines & save to a log file
		for line in self.outputStreamer(p):

			# Time tests
			if options.time:
				if timer != None:
					timer.processLine(line)

			# Log data
			log.write(line + "\n")
			if options.interactive:
				print line


	def outputStreamer(self, proc, stream='stdout'):
		"""
		Hanldes streaming of subprocess.
		Copied from: http://blog.thelinuxkid.com/2013/06/get-python-subprocess-output-without.html
		"""

		newlines = ['\n', '\r\n', '\r']
		stream = getattr(proc, stream)
		with contextlib.closing(stream):
			while True:
				out = []
				last = stream.read(1)
				# Don't loop forever
				if last == '' and proc.poll() is not None:
					break
				while last not in newlines:
					# Don't loop forever
					if last == '' and proc.poll() is not None:
						break
					out.append(last)
					last = stream.read(1)
				out = ''.join(out)
				yield out


class ParametricMetaClass(type):
	"""
	Meta class for parametric tests
	More info: http://stackoverflow.com/a/20870875

	Expects that the inheriting class defines
	baseName: The name of the input deck to use as a template (without the .inp)
	parameters: a dictionary with each parameter to vary. For example: {'alpha': range(-40,10,10), 'beta': range(60,210,30)}
	"""

	def __new__(mcs, name, bases, dct):

		def make_test_function(testCase):
			"""
			Creates test_ function for the particular test case passed in
			"""

			items = testCase.items()

			jobName = testCase['name']
			baseName = testCase['baseName']
			parameters = {k: v for k, v in items if not k in ('baseName', 'name')}


			def test(self):

				# Create the input deck
				# Copy the template input file
				if 'pythonScriptForModel' in testCase:
					inpFilePath = os.path.join(os.getcwd(), jobName + '.py')
					shutil.copyfile(os.path.join(os.getcwd(), baseName + '.py'), inpFilePath)
				else:
					inpFilePath = os.path.join(os.getcwd(), jobName + '.inp')
					shutil.copyfile(os.path.join(os.getcwd(), baseName + '.inp'), inpFilePath)

				# Update all of the relevant *Parameter terms in the Abaqus input deck
				with file(inpFilePath, 'r') as original:
					data = original.readlines()
				for p in parameters.keys():
					for line in range(len(data)):
						if re.search('.{0,}' + str(p) + '.{0,}=.{0,}$', data[line]) is not None:
							data[line] = data[line].split('=')[0] + '= ' + str(parameters[p]) + '\n'
							break
				with file(inpFilePath, 'w') as modified:
					modified.writelines(data)

				# Generate an expected results Python file with jobName
				expectedResultsFile = os.path.join(os.getcwd(), jobName + '_expected.py')
				shutil.copyfile(os.path.join(os.getcwd(), baseName + '_expected.py'), expectedResultsFile)

				# Update expected results if needed
				with file(expectedResultsFile, 'r') as original:
					data = original.readlines()
				for p in parameters.keys():
					for line in range(len(data)):
						if re.search('.{0,}' + str(p) + '.{0,}=.{0,}$', data[line]) is not None:
							data[line] = data[line].split('=')[0] + '= ' + str(parameters[p]) + '\n'
							break
				with file(expectedResultsFile, 'w') as modified:
					modified.writelines(data)

				# Save output to a log file
				with open(os.path.join(os.getcwd(), 'testOutput', jobName + '.log'), 'w') as f:

					# Generate input file from python script
					if 'pythonScriptForModel' in testCase:
						self.callAbaqus(cmd=options.abaqusCmd + ' cae noGUI=' + inpFilePath, log=f)

					# Time tests
					if options.time:
						timer = measureRunTimes()
					else:
						timer = None

					# Execute the solver
					if not options.useExistingResults:
						self.runModel(jobName=jobName, f=f, timer=timer)

					# Execute process_results script load ODB and get results
					pathForThisFile = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
					if not os.path.isfile(os.path.join(os.getcwd(), 'testOutput', jobName + '.odb')):
						raise Exception("Error: Abaqus odb was not generated. Check the log file in the testOutput directory.")
					pathForProcessResultsPy = '"' + os.path.join(pathForThisFile, 'processresults.py') + '"'
					self.callAbaqus(cmd=options.abaqusCmd + ' cae noGUI=' + pathForProcessResultsPy + ' -- -- ' + jobName, log=f, timer=timer)

				os.remove(jobName + '.inp')  # Delete temporary parametric input file
				os.remove(jobName + '_expected.py') # Delete temporary parametric expected results file
				if 'pythonScriptForModel' in testCase:
					os.remove(jobName + '.py')

				# Run assertions
				self.runAssertionsOnResults(jobName)


			# Rename the test method and return the test
			test.__name__ = jobName
			return test

		# Store input arguments
		try:
			baseName = dct['baseName']
			parameters = dct['parameters']
		except:
			print "baseName and parameters must be defined by the sub class"

		# Get the cartesian product to yield a list of all the potential test cases
		testCases = list(dict(it.izip(parameters, x)) for x in it.product(*parameters.itervalues()))

		# Loop through each test
		for i in range(0,len(testCases)):

			# Add a name to each test case
			# Generate portion of test name based on particular parameter values
			pn = '_'.join(['%s_%s' % (key, value) for (key, value) in testCases[i].items()])
			# Replace periods with commas so windows doesn't complain about file names
			pn = re.sub('[.]','',pn)
			# Add the test case name; concatenate the base name and parameter name
			testCases[i].update({'name': baseName + '_' + pn})
			testCases[i].update({'baseName': baseName})
			if 'pythonScriptForModel' in dct:
				testCases[i].update({'pythonScriptForModel': dct['pythonScriptForModel']})
			if 'expectedpy_parameters' in dct:
				exp_dict = {}
				for k, v in  dct['expectedpy_parameters'].iteritems():
					exp_dict[k] = v[i]
				testCases[i].update(exp_dict)

			# Add test functions to the testCase class
			dct[testCases[i]['name']] = make_test_function(testCases[i])

		return type.__new__(mcs, name, bases, dct)


def runTests(relPathToUserSub, compileCodeFunc=None):
	"""
	This is the main entry point for abaverify.
	There is option optional argument (compileCodeFunc) which is the function called to compile subroutines via
	abaqus make. This functionality is used when compiling the subroutine once before running several tests is
	desired. By default the subroutine is compiled at every test execution.
	"""

	global options

	# Command line options
	parser = OptionParser()
	parser.add_option("-i", "--interactive", action="store_true", dest="interactive", default=False, help="Print output to the terminal; useful for debugging")
	parser.add_option("-t", "--time", action="store_true", dest="time", default=False, help="Calculates and prints the time it takes to run each test")
	parser.add_option("-c", "--precompileCode", action="store_true", dest="precompileCode", default=False, help="Compiles the subroutine before running each tests")
	parser.add_option("-e", "--useExistingBinaries", action="store_true", dest="useExistingBinaries", default=False, help="Uses existing binaries in /build")
	parser.add_option("-r", "--useExistingResults", action="store_true", dest="useExistingResults", default=False, help="Uses existing results in /testOutput; useful for debugging postprocessing")
	parser.add_option("-s", "--specifyPathToSub", action="store", dest="relPathToUserSub", default=relPathToUserSub, help="Override path to user subroutine")
	parser.add_option("-A", "--abaqusCmd", action="store", type="string", dest="abaqusCmd", default='abaqus', help="Override abaqus command; e.g. abq6141")
	parser.add_option("-k", "--keepExistingOutputFiles", action="store_true", dest="keepExistingOutputFile", default=False, help="Does not delete existing files in the /testOutput directory")
	parser.add_option("-C", "--cpus", action="store", type="int", dest="cpus", default=1, help="Specify the number of cpus to run abaqus jobs with")
	(options, args) = parser.parse_args()

	# Remove custom args so they do not get sent to unittest
	# http://stackoverflow.com/questions/1842168/python-unit-test-pass-command-line-arguments-to-setup-of-unittest-testcase
	# Loop through known options
	for x in sum([h._long_opts+h._short_opts for h in parser.option_list],[]):
		# Check if the known option is an argument 
		if x in sys.argv:
			# Get the option object
			if x in [h._short_opts[0] for h in parser.option_list]:
				idx = [h._short_opts[0] for h in parser.option_list].index(x)
				option = parser.option_list[idx]
			elif  x in [h._long_opts[0] for h in parser.option_list]:
				raise ''
			
			# If the option has additional info (e.g. -A abq6141), remove both from argv
			if option.type in ["string", "int"]:
				idx = sys.argv.index(x)
				del sys.argv[idx:idx+2]
			else:
				sys.argv.remove(x)
			

	# Remove rpy files
	testPath = os.getcwd()
	pattern = re.compile('^abaqus\.rpy(\.)*([0-9])*$')
	for f in os.listdir(testPath):
		if pattern.match(f):
			os.remove(os.path.join(os.getcwd(), f))

	# Remove old binaries
	if not options.useExistingBinaries:
		if os.path.isdir(os.path.join(os.pardir, 'build')):
			for f in os.listdir(os.path.join(os.pardir, 'build')):
				os.remove(os.path.join(os.pardir, 'build', f))

	# If testOutput doesn't exist, create it
	testOutputPath = os.path.join(os.getcwd(), 'testOutput')
	if not os.path.isdir(testOutputPath) and options.useExistingResults:
		raise Exception("There must be results in the testOutput directory to use the --useExistingResults (-r) option")
	if not os.path.isdir(testOutputPath):
		os.makedirs(testOutputPath)

	# Remove old job files
	if not options.useExistingResults:
		if not options.keepExistingOutputFile:
			testOutputPath = os.path.join(os.getcwd(), 'testOutput')
			pattern = re.compile('.*\.env$')
			for f in os.listdir(testOutputPath):
				if not pattern.match(f):
					os.remove(os.path.join(os.getcwd(), 'testOutput', f))
		else:
			# Check for files with the same name to avoid overwriting
			# This is a bit of pain
			# Process:
			# 1. Check if args any are classes in the calling file that are specified as arguments
			classesInCallingFile = {}
			# Get the calling file
			frame = inspect.stack()[1]
			# Get the classes in the calling file
			for name, obj in inspect.getmembers(inspect.getmodule(frame[0])):
				if inspect.isclass(obj) and issubclass(obj, TestCase):
					classesInCallingFile[obj.__name__] = obj
			calledClasses = list(set(sys.argv[1:]).intersection(classesInCallingFile.keys()))

			# 2. Build a list of test_ methods that will be called
			calledMethods = []

			# 3. Get test_ methods from the class(es) that are called
			for c in calledClasses:
				for name, obj in inspect.getmembers(classesInCallingFile[c], predicate=inspect.ismethod):
					if 'test_' in name:
						calledMethods.append(name)

			# 4. Get test_ methods list explicity in the arguments
			for arg in sys.argv[1:]:
				if len(arg.split('.')) == 2:
					testName = arg.split('.')[1]
					if 'test' in testName:
						calledMethods.append(testName)
			
			# Now we have a list of the test methods that will be called
			# print calledMethods

			# Get a list of unique file names begining with 'test' in testOutput directory (w/o file extensions)
			uniquefileNames = list(set([f.split('.')[0] for f in os.listdir(testOutputPath) if 'test_' in f]))

			# Check if any files exist in testOutput with these test names
			testsToBeOverwritten = list(set(uniquefileNames).intersection(calledMethods))
			if len(testsToBeOverwritten) > 0:
				raise Exception("Cannot overwrite the following tests {0}".format(str(testsToBeOverwritten)))


		# Try to pre-compile the code
		if not options.useExistingBinaries:
			wd = os.getcwd()
			if options.precompileCode:
				try:
					compileCodeFunc()
				except:
					print "ERROR: abaqus make failed.", sys.exc_info()[0]
					raise Exception("Error compiling with abaqus make. Look for 'compile.log' in the testOutput directory. Or try running 'abaqus make library=CompDam_DGD' from the /for directory to debug.")
					os.chdir(wd)

		# Make sure
		# 1) environment file exists
		# 2) it has usub_lib_dir
		# 3) usub_lib_dir is the location where the binaries reside
		# 4) a copy is in testOutput
		if os.path.isfile(os.path.join(os.getcwd(), 'abaqus_v6.env')):
			# Make sure it has usub_lib_dir
			if options.precompileCode:
				with open(os.path.join(os.getcwd(), 'abaqus_v6.env'), 'r+') as envFile:
					foundusub = False
					pattern_usub = re.compile('^usub_lib_dir.*')
					for line in envFile:
						if pattern_usub.match(line):
							print "Found usub_lib_dir"
							pathInEnvFile = re.findall('= "(.*)"$', line).pop()
							if pathInEnvFile:
								if pathInEnvFile == '/'.join(os.path.abspath(os.path.join(os.pardir, 'build')).split('\\')): # Note that this nonsense is because abaqus wants '/' as os.sep even on windows
									foundusub = True
									break
								else:
									raise Exception("ERROR: a usub_lib_dir is specified in the environment file that is different from the build location.")
							else:
								raise Exception("ERROR: logic to parse the environment file looking for usub_lib_dir failed.")

				# Add usub_lib_dir if it was not found
				if not foundusub:
					print "Adding usub_lib_dir to environment file."
					with open(os.path.join(os.getcwd(), 'abaqus_v6.env'), 'a') as envFile:
						pathWithForwardSlashes = '/'.join(os.path.abspath(os.path.join(os.pardir, 'build')).split('\\'))
						print pathWithForwardSlashes
						envFile.write('\nimport os\nusub_lib_dir = "' + pathWithForwardSlashes + '"\ndel os\n')

			# Copy to /test/testOutput
			shutil.copyfile(os.path.join(os.getcwd(), 'abaqus_v6.env'), os.path.join(os.getcwd(), 'testOutput', 'abaqus_v6.env'))
		else:
			raise Exception("Missing environment file. Please configure a local abaqus environement file. See getting started in readme.")



	unittest.main(verbosity=2)
