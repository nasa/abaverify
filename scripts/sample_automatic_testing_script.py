#!/usr/bin/python

# Sample script for automatically running abaverify verification tests
# Use a utility like cron or a git hook to call this script as needed

import abaverify as av


# Set options
av_auto = av.Automatic('path/to/test/dir', options={})

# Run the tests
av_auto.run()

# Email the results
html_summary = av_auto.generateReport('template_email_summary')
av_auto.emailResults(recipients=['you@example.com', ], 
                     sender='noreply@example.com', template='template_email_summary')
