
import matplotlib.pyplot as plt
import glob
import os
import re
from lxml.html import soupparser as sp
import datetime as dt
from optparse import OptionParser
import plotly.offline as ply
import plotly.graph_objs as plygo
import shutil


#
# TODO
#  1. Add option to generate a plot for specified test(s)
#


def run(testGroups, outputFileName, numTestsToUse=-1):
	"""
	This function creates the html file
	"""
	
	# Try to make sure we are in the right directory
	curDir = os.getcwd()
	curDirList = curDir.split(os.path.sep)
	if 'archivedTestResults' not in curDirList:
		if 'DGD' not in curDirList:
			raise Exception("Could not figure out path to archivedTestResults")
		else:
			i = curDirList.index('DGD')
			arhcivedTestDir = os.path.sep.join(curDirList[:i+1]+['archivedTestResults'])
			os.chdir(arhcivedTestDir)
	
	
	# Get a list of the html files in the archive directory
	files = glob.glob('*html')
	files.sort(key=lambda x: os.path.getmtime(x))

	# Limit tests if needed
	if numTestsToUse > 0:
		files = files[-numTestsToUse:]

	# Dictionary to store data
	tests = dict()
	# PLACEHOLDER: example key value pair
	# tests[<testName>] = [{'date': <date>, 'commit': <>, 'runTime': <testRunTime>, 'passed': <bool>}]


	# Parse the files
	for f in files:

		print "Parsing " + f

		# Get the date and commit hash from the filename
		matches = re.match(r'.*DGD_(.*)_(.*)\.html$', f)
		if matches:
			grps = matches.groups()
			if len(grps) != 2:
				raise Exception("Failed while attempting to parse file name")
		
			commitHash = grps[0]
			testDate = dt.datetime.strptime(grps[1], '%Y-%b-%d').date()
	
			# Load the file into lxml
			html = sp.parse(f)
		
			pattern = re.compile("^test_.*")
		
			# Loop through each row in the table
			rows = html.xpath('//tr')
			for row in rows:
		
				cols = row.getchildren()
			
				# Skip tests that are not run
				if len(cols) < 4:
					continue
			
				# Attempt to parse out data from the row
				if pattern.match(cols[0].text):
					testName = cols[0].text
					m = re.match(r'(.*) \(.*', testName)
					if not m:
						raise Exception("Failed while attempting to parse file name")
					if len(m.groups()) != 1:
						raise Exception("Failed while attempting to parse file name")
					testName = m.groups()[0]
				
					# Parse out the testTime
					testTime = cols[-2].text
					#print repr(testTime)
					m = re.match(r'(.*) s', testTime)
					if not m:
						#print "WARNING: failed to parse testTime {0}".format(repr(testTime))
						#print "\t\tRow: {0}".format([col.text for col in cols])
						#print "\t\tFile: {0}".format(f)
						continue
					if len(m.groups()) != 1:
						raise Exception("Failed while attempting to parse file name")
					testTime = float(m.groups()[0])
				
					# Get test status
					statusText = [text for text in cols[-1].itertext()].pop()
					if statusText == 'ok':
						testStatus = True
					else:
						testStatus = False
				
					# Add the test if its not already in tests dictionary
					if testName not in tests:
						tests[testName] = list()
				
					# Add the test result
					tests[testName].append({'date': testDate, 'commit': commitHash, 'runTime': testTime, 'passed': testStatus})


	# Initiate plotly data object
	# FigNum is key to dictionary
	ply_data = dict()

	# Iterate through each test and plot it
	for testName in tests.keys():

		# Group similar tests
		currentGroup = 'SingleElementTests'
		currentFigNum = len(testGroups)-1
		for testGroup in testGroups:
			if testGroup in testName:
				currentGroup = testGroup
				currentFigNum = testGroups.index(testGroup)
	
		# Collect the data
		x = [item['date'] for item in tests[testName]]
		y = [item['runTime'] for item in tests[testName]]
	
		# Add the data to the figure
		# Plotly
		if currentFigNum not in ply_data:
			ply_data[currentFigNum] = list()
		ply_data[currentFigNum].append(
					plygo.Scatter(x=x, y=y, 
									mode="lines", 
									name=testName, 
									text=testName, 
									hoverinfo="text+x+y"))
	
		
		## Matlab static plots
		#if options.matlab:
		#	plt.figure(currentFigNum)
		#	plt.plot(x,y)

	# Save the plots
	with open(outputFileName, 'w') as ply_html:
		ply_html.write('<html><body>\n')
		#for i in range(0, 4):
		for i in range(0, len(testGroups)):
			# Plotly
		
			# Formatting
			layout = dict(title = testGroups[i], 
		              yaxis = dict(title = 'Solver run time [s]'), 
					  showlegend=False, 
					  height=800,
					  width=1200,)
		
			# Only include plotly js once
			if i==0:
				include_plotlyjs=True
			else:
				include_plotlyjs=False
		
			fig = dict(data=ply_data[i], layout=layout)
			html = ply.plot(fig, output_type='div', include_plotlyjs=include_plotlyjs)
			ply_html.write(html+'\n\n')

		# Close the html tags
		ply_html.write("\n</body></html>\n")


	# Move the html file to the original CurDir
	shutil.move(outputFileName, os.path.join(curDir, outputFileName))
	
	os.chdir(curDir)
	
	
		
if __name__ == "__main__":

	# Parse options
	parser = OptionParser()
	#parser.add_option("-m", "--matlab", action="store_true", dest="matlab", default=False, help="Plot with matlibplot")
	parser.add_option("-n", "--number", type="int", action="store", dest="numTestsToUse", default=-1, help="Number of tests to use")
	(options, args) = parser.parse_args()
	
	testsToGroup = ['test_C3D8R_failureEnvelope_sig11sig22', 
				'test_S4R_failureEnvelope_sig11sig22', 
				'test_C3D8R_failureEnvelope_sig12sig22',
				'test_S4R_failureEnvelope_sig12sig22',
				'test_C3D8R_failureEnvelope_sig12sig23',
				'test_C3D8R_mixedModeMatrix',
				'SingleElementTests']
				
	htmlFileName = 'runtime_plotly.html'
	
	run(testGroups=testsToGroup, outputFileName=htmlFileName, numTestsToUse=options.numTestsToUse)

	

