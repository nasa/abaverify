#!/usr/bin/python

# Sample script for automatically running abaverify verification tests
# Use a utility like cron or a git hook to call this script as needed

import os
import abaverify as av

import pprint
pp = pprint.PrettyPrinter(indent=4)

# Location for storing automatic test results
archive_dir = os.path.join(os.getcwd(), 'autoTestArchive')

# Initialize the automatic tester
av_auto = av.Automatic(test_directory=os.getcwd(), 
                       archive_directory=archive_dir, 
                       repository={
                           'name': 'abaverify-dev',
                           'remote': 'origin',
                           'branch': 'master'},
                       tests_to_run=['SingleElementTests', ],
                       force_tests=True,
                       verbose=True)


# Run the tests
result = av_auto.run()

# PNG files in testOutpu
attach = [os.path.join(os.getcwd(), 'testOutput', x) for x in os.listdir(os.path.join(os.getcwd(), 'testOutput')) if x.endswith(".dat")]


# Process the results
if result:
    av_auto.generateRunTimePlots(template='template_run_time_plots')

    av_auto.emailResults(recipients="andrew.c.bergan@nasa.gov", sender="noreply@nasa.gov", 
                         template='template_email_summary', attachments=attach)
