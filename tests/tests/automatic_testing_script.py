#!/usr/bin/python

# Sample script for automatically running abaverify verification tests
# Use a utility like cron or a git hook to call this script as needed

import os
from optparse import OptionParser
import abaverify as av

import pprint
pp = pprint.PrettyPrinter(indent=4)

# Location for storing automatic test results
archive_dir = os.path.join(os.getcwd(), 'autoTestArchive')

# Initialize the automatic tester
av_auto = av.Automatic(test_directory=os.getcwd(), 
						archive_directory=archive_dir, 
						repository = {
							'name': 'abaverify-dev',
							'remote': 'origin',
							'branch': 'master'
						},
						tests_to_run=['SingleElementTests', ],
						force_tests=True,
						verbose=True)


# Run the tests
result = av_auto.run()

# Process the results
if result:
	av_auto.emailResults(recipients="andrew.c.bergan@nasa.gov", sender="noreply@nasa.gov", 
		template='template_email_summary')


# TODO - implement below:

# # Post the results to github
# html_test_list = av_auto.generateReport('my_cool_template_file')
# html_plots = av_auto.generateRunTimePlots('a_template_for_plotting')
# av_auto.commitReportToGitHub([html_test_list, html_plots], github_info)