#!/usr/bin/python

# Script for debugging features of automatic.py

import os
from optparse import OptionParser
import abaverify as av


def reportGenerator(archiveTestResultsJSONFile, templateName):
	report = av.TestReport.fromArchivedResult(archiveTestResultsJSONFile)
	html_summary = av.Automatic.generateReport2(template=templateName, report=report)
	fp = os.path.join('testOutput', 'report_generator_test.html')
	with open(fp, 'w') as outfile:
		outfile.write(html_summary)
	return fp

def email(archiveTestResultsJSONFile, templateName, recipient):
	fp = reportGenerator(archiveTestResultsJSONFile, templateName)
	av.Automatic.emailResults2(recipients=[recipient, ], sender='noreply@nasa.gov', body=fp)
	return


if __name__ == '__main__':

	parser = OptionParser(usage="automatic_testing_debug.py feature [args]")
	parser.add_option('-r', "--reportJSONFile", action="store", dest="report_json_file", default="sample_archived_test_result.json", help="Specify a report object to use.")
	parser.add_option('-g', "--debugReportGenerator", action="store", dest="report_template", default="template_email_summary", help="Debug the report generator. Pass the name of the template. Requires a report object via -r.")
	parser.add_option('-e', "--emailRecipients", action="store", dest="email_recipients", default="", help="Specify recipients to email report to.")
	(options, args) = parser.parse_args()

	if len(args) != 1:
		raise ValueError("One argument required: Name of the feature to test. e.g.: reportGenerator")
	else:
		feature = args[0]

	# Call the feature specified
	if feature == 'reportGenerator':
		reportGenerator(options.report_json_file, options.report_template)
	elif feature == 'email':
		if len(options.email_recipients) < 1:
			raise ValueError("Must specify recipeints via the -e option to use the email feature.")
		email(archiveTestResultsJSONFile=options.report_json_file, templateName=options.report_template, 
			recipient=options.email_recipients)
	else:
		raise ValueError("Unknown feature specified.")