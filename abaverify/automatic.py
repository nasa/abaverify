import os
import sys
import subprocess
import contextlib
import re
import json
import time
import zipfile
import shutil

import smtplib
import email.utils
from email.mime.text import MIMEText
from email.MIMEBase import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import Encoders

import pprint

"""
Functionality to run abaverify tests automatically.
The intention is that a script (see sample_automatic_testing_script.py for example) triggered by cron would call run().
"""

pp = pprint.PrettyPrinter(indent=4)

class Automatic():
	"""
	Main functionality for the automatic module.
	"""


	#
	# Public API
	#
	def __init__(self, test_directory, archive_directory, repository=None, test_runner_file_name='test_runner.py',
		time_tests=True, force_tests=False, verbose=False, tests_to_run=[]):
		"""
		Setup Automatic with user defined options (kwargs)
		"""

		#-------------------------------------------------------------------------------
		# Required arguments
		self.test_directory = test_directory
		self.archive_directory = archive_directory
		

		# Execute from the test directory
		os.chdir(test_directory)

		# Make sure the archive directory exists
		if not os.path.isdir(archive_directory):
			os.makedirs(archive_directory)

		#-------------------------------------------------------------------------------
		# Load options

		# Get the repository information
		self.update_repo = False  # This attribute defines whether the code should attempt to git pull to get new commits in the tested repo
		if type(repository) is str:
			self.repository_name = repository
		elif type(repository) is dict:
			if 'name' in repository:
				self.repository_name = repository['name']
			if 'remote' in repository:
				self.repository_remote = repository['remote']
			if 'branch' in repository:
				self.repository_branch = repository['branch']
			if 'remote' in repository and 'branch' in repository:
				self.update_repo = True
		elif repository is None:
			self.repository_name = self._getRepoName()
		else:
			raise ValueError("The argument repository for Automatic intialization must be a string or a dictionary.")
		
		# Update repo
		if self.update_repo:
			subprocess.check_output("git pull " + self.repository_remote + " " + self.repository_branch, shell=True)

		# Name of the file that defines the tests
		self.test_runner_file_name = test_runner_file_name

		# Collect test durations?
		self.time_tests = time_tests
		
		# Abaverify -c option. Precompile abaqus subroutine before running tests.
		# TODO: I think this option is currently broken...
		#self.pre_compile_subroutine = kwargs.get('pre_compile_subroutine', True)

		# TODO Run with multiple cpus
		#self.cpus = kwargs.get('cpus', True)
		
		# Runs tests even if there are no changes to the repo
		self.force_tests = force_tests

		# Log parsing data
		self.verbose = verbose

		# List of tests to run [default is an empty list, in which case all tests are run]
		if not(type(tests_to_run) is list):
			raise ValueError("The argument tests_to_run for Automatic must be a list")
		self.tests_to_run = tests_to_run

		#-------------------------------------------------------------------------------
		# Initialize a new test report

		# Test report init
		self.test_report = TestReport()

		# Initialize a dict to store formated reports
		self.formatted_reports = dict()

		# Print configuration if verbose is on
		if self.verbose:
			_logVerbose(self.__dict__)

		return


	def run(self):
		"""
		Build a testReport object with all the repo info and testResults
		Store the testReport to the object instance
		"""

		# Get the sha of the current commit
		sha = subprocess.check_output("git rev-parse --short HEAD", shell=True).rstrip()
		self.test_report.metaData['sha'] = sha

		# Check if there are uncommited changes
		try:
			subprocess.check_call('git diff --quiet', shell=True)
			self.test_report.metaData['uncommited_changes'] = False
		except:
			self.test_report.metaData['uncommited_changes'] = True
			if self.verbose:
				_logVerbose("Found uncommitted changes")

		# Check if the current commit has been tested (and directory there are no uncommitted changes)
		if not self.force_tests and _currentCommitTested():
			print "No new commits"
			return False
		

		# Build the command to run the tests
		cmd = ["python", self.test_runner_file_name]
		if self.time_tests: 
			cmd.append("-t")
		if self.tests_to_run:
			cmd = cmd + self.tests_to_run
		if self.verbose:
			_logVerbose("Running abaverify: " + " ".join(cmd))
		# Run the tests
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

		# Parse output lines & save to a log file
		for line in _outputStreamer(p):
			self._parseLine(line)

		# Archive the report
		file_name = self.repository_name + '_' + sha + '_' + time.strftime("%Y-%b-%d") + '.json'
		if self.test_report.metaData['uncommited_changes']: file_name = 'uc_' + file_name
		trpath = os.path.join(self.archive_directory, file_name)
		with open(trpath, 'w') as outfile:
			json.dump(self.test_report.getDict(), outfile)
		if self.verbose:
			_logVerbose("Archived test report at: " + trpath)

		# zip job files and copy to the archive directory
		file_name = os.path.splitext(file_name)[0]
		zipf = zipfile.ZipFile(file_name + ".zip", 'w', allowZip64=True)
		_zipdir('testOutput', zipf)
		zipf.close()

		# Move the archive to storage
		shutil.move(file_name + ".zip", os.path.join(self.archive_directory, file_name + ".zip"))

		# Return the report obj
		return True


	def generateReport(self, template):
		rpt = _generateReport(template=template, report=self.test_report)
		self.formatted_reports[template] = rpt
		return rpt
	

	@classmethod
	def generateReport2(cls, template, report):
		return _generateReport(template=template, report=report)


	def generateRunTimePlots(self, template, path):
		"""
		Build plots with plotly (see runtimeplots.py)
		"""
		pass


	def commitReportToGitHub(self, repo_info):
		"""
		Options should be set at instantiation
		"""

	def emailResults(self, recipients, sender, template):
		"""
		TODO: include options to attach plots etc from jobs (ie failure envelope plots)
		"""

		# If the report has already been run, use it
		if template in self.formatted_reports:
			b = self.formatted_reports[template]
		
		# Otherwise run the report
		else:
			b = _generateReport(template=template, report=self.test_report)

		# Call helper to send the email
		_emailResults(recipients=recipients, sender=sender, body=b, attachments=None, repository_info=None)
		return


	@classmethod
	def emailResults2(cls, recipients, sender, body, attachments=None, repository_info=None):
		if repository_info is None:
			repository_info = {'name': 'repo_name_placeholder', 'branch': 'repo_branch_placeholder'}

		_emailResults(recipients, sender, body, attachments, repository_info)
		return


	def archiveReports(self):
		"""
		TODO: this is designed to be called once all reports are prepared. archive reports to archive directory.
		"""

	#
	# Locals
	#

	def _getRepoName(self):
		repo_path = subprocess.check_output("git rev-parse --show-toplevel", shell=True).strip()
		return repo_path.split('/').pop()


	def _parseLine(self, line):
		"""
		Parses output from test_runner.py
		"""
		
		# Match 'ok'
		if re.match(r'.*ok$', line):
			if self.verbose: _logParsing("MATCHED", line)
			self.test_report.setTestResult(True)

		# Match 'fail'
		elif re.match(r'.*FAIL$', line):
			if self.verbose: _logParsing("MATCHED", line)
			self.test_report.setTestResult(False)

		# Match lines starting with test_
		# These lines indicate the start of a new test
		elif re.match(r'^test_.*', line):
			if '...' in line:
				if self.verbose: _logParsing("MATCHED", line)
				sl = line.split('...')
				s2 = sl[0].split(' (')
				self.test_report.addTestResult(s2[0])

			else:
				if self.verbose: _logParsing("NOT MATCHED", line)

		# Match time:
		elif re.match(r'.*time:.*$', line):
			if self.verbose: _logParsing("MATCHED", line)
			match = re.search(r'^([a-zA-Z]*)[\w ]*: ([0-9\.]*) s$', line)
			self.test_report.setRunTime(category=match.group(1).lower(), duration=match.group(2))

		# Match summary
		elif re.match(r'Ran ([0-9]*) tests in ([0-9\.]*)s$', line):
			match = re.search(r'Ran ([0-9]*) tests in ([0-9\.]*)s$', line)
			self.test_report.setSummaryPassed(int(match.group(1)), match.group(2))
		
		# Failed summary
		elif re.match(r'FAILED', line):
			match = re.search(r'FAILED \(errors=([0-9]*)\)$', line)
			self.test_report.setSummaryFailed(int(match.group(1)))

		# Other lines
		else:
			if self.verbose: _logParsing("NOT MATCHED", line)



#
# Helper functions
#

def _currentCommitTested():
	"""
	Checks if the current SHA has an archived result
	"""

	# Get current SHA
	currentSHA = subprocess.check_output("git rev-parse --short HEAD", shell=True).strip()
	
	# Get most recent SHA in archive dir
	mostRecentTestResultsSHA = ''
	files = [os.path.join(self.archive_directory, f) for f in os.listdir(self.archive_directory)]
	if len(files) > 0:
		files.sort(key=lambda x: os.path.getmtime(x))
		pathToMostRecent = files.pop()

		# # Filter for files that match the naming convention
		# pattern = re.compile('.*DGD_.*\.html$')
		# filteredFiles = [fileName.split('/').pop() for fileName in files if pattern.match(fileName)]
		# fileName = filteredFiles[-1]
		
		print "Most recent file " + pathToMostRecent

		match = re.search(r'.*_([a-zA-Z0-9]*)_.*\.json$', pathToMostRecent.split('/').pop())
		if match:
			if len(match.groups()) != 1:
				raise Exception("Error parsing file names in archive directory")
			
			mostRecentTestResultsSHA = match.groups()[0]
	
	# Compare SHAs
	if (currentSHA == mostRecentTestResultsSHA):
		return True
	else:
		return False


def _generateReport(template, report):
	"""
	Return the template with the test report data substituted 
	"""

	# TODO add some logic to check if template is in working directory, if not search templates dir
	sys.path.append(os.path.join(os.pardir, os.pardir, 'templates'))

	# Load the template file
	templ = __import__(template)
	
	# Build string of test results
	test_result_formatted_str = ""
	for tr in report.test_results:
		c = 'green' if tr.test_status else 'red'
		test_result_formatted_str += templ.test_result.format(test_name=tr.test_name, packager_time=tr.run_times['packager'], 
			solver_time=tr.run_times['solver'], status_color=c, status_text=tr.test_status)

	# Build string for body
	body_formatted_str = templ.body.format(git_sha=report.metaData['sha'], test_results=test_result_formatted_str, 
		number_of_tests_run=report.summary['number_tests'], total_duration=report.summary['duration'])

	return body_formatted_str


def _emailResults(recipients, sender, body, attachments, repository_info):
	"""
	Emails results
	recipients = list
	body = path to file containing body of email (assumes the file is html)
	attachments = paths to files to attach to the email
	repository_info = {'name': , 'branch': }
	"""

	msg = MIMEMultipart('alternative')

	# Read the file containing the unittest output
	with open(body, 'rb') as f:
		html_body = MIMEText(f.read(), "html")
		msg.attach(html_body)

	# Setup the message
	msg["from"] = sender
	msg["To"] = ", ".join(recipients)
	msg["Subject"] = "[abaverify] Repository: " + repository_info['name'] + "; Branch: " + repository_info['branch']

	# # TODO Attachments
	# # Attach image files
	# imgFileNames = [x for x in os.listdir(os.path.join(os.getcwd(), 'testOutput')) if x.endswith(".png")]
	# for imgFileName in imgFileNames:
	# 	imgPath = os.path.join(os.getcwd(), 'testOutput', imgFileName)
	# 	with open(imgPath, 'rb') as i:
	# 		img = MIMEBase('application', 'octect-stream')
	# 		img.set_payload(i.read())
	# 		Encoders.encode_base64(img)
	# 		img.add_header('Content-Disposition', 'attachment; filename=%s' % os.path.basename(imgFileName))
	# 		msg.attach(img)

	# # Attach the html plot file
	# with open(htmlFileName, 'rb') as h:
	# 	htmlFileAttachment = MIMEBase('application', 'octect-stream')
	# 	htmlFileAttachment.set_payload(h.read())
	# 	Encoders.encode_base64(htmlFileAttachment)
	# 	htmlFileAttachment.add_header('Content-Disposition', 'attachment; filename=%s' % htmlFileName)
	# 	msg.attach(htmlFileAttachment)
		
	# # Attach the CompDam.parameters file
	# with open(os.path.join('testOutput', 'CompDam.parameters'), 'rb') as h:
	# 	paraFileAttachment = MIMEBase('application', 'octect-stream')
	# 	paraFileAttachment.set_payload(h.read())
	# 	Encoders.encode_base64(paraFileAttachment)
	# 	paraFileAttachment.add_header('Content-Disposition', 'attachment; filename=CompDam.parameters')
	# 	msg.attach(paraFileAttachment)
	
	# Send
	s = smtplib.SMTP('localhost')
	try:
		s.sendmail(sender, recipients, msg.as_string())         
	finally:
		s.quit()



def _outputStreamer(proc, stream='stdout'):
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


def _logParsing(status, line):
	print status + ": " + line
	sys.stdout.flush()


def _logVerbose(data):
	pp.pprint(data)
	sys.stdout.flush()


def _zipdir(path, ziph):
	# Zip a directory
	# ziph is a zipfile handle
	for root, dirs, files in os.walk(path):
		for file in files:
			ziph.write(os.path.join(root, file))


#
# Locals
#

class TestResult():
	"""
	Stores result from one test
	"""

	def __init__(self, test_name, status=False, compile_duration='', package_duration='', solve_duration=''):
		self.test_name = test_name
		self.test_status = status # False = failed; True = passed
		self.run_times = {'compile': compile_duration, 'packager': package_duration, 'solver': solve_duration }


	def getDict(self):
		return {'test_name': self.test_name, 'test_status': self.test_status, 'run_times': self.run_times}


class TestReport():
	"""
	Stores report from testing
	"""
	

	def __init__(self):
		self.metaData = dict()
		self.test_results = list()
		self.summary = dict()


	@classmethod
	def fromArchivedResult(cls, pathToJSONFile):
		with open(pathToJSONFile) as jf:
			jsondict = json.load(jf)
		obj = cls()
		obj.metaData = jsondict['metaData']
		obj.summary = jsondict['summary']
		for tr in jsondict['test_results']:
			obj.test_results.append(TestResult(test_name=tr['test_name'], status=tr['test_status'], compile_duration=tr['run_times']['compile'],
				package_duration=tr['run_times']['packager'], solve_duration=tr['run_times']['solver']))
		return obj

	def addTestResult(self, test_name):
		tr = TestResult(test_name)
		self.test_results.append(tr)


	def setTestResult(self, test_status):
		self.test_results[-1].test_status = test_status


	def setRunTime(self, category, duration):
		self.test_results[-1].run_times[category] = duration


	def setSummaryPassed(self, number_tests, duration):
		self.summary['number_tests'] = number_tests
		self.summary['duration'] = duration

		if len(self.test_results) != number_tests:
			print "WARNING: Some tests not parsed correctly"


	def setSummaryFailed(self, number_tests):
		self.summary['number_failed'] = number_tests


	def getDict(self):
		d = dict()
		d['metaData'] = self.metaData
		d['test_results'] = list()
		for tr in self.test_results:
			d['test_results'].append(tr.getDict())
		d['summary'] = self.summary
		return d