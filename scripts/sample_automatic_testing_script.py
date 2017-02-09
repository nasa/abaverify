#!/usr/bin/python

# Sample script for automatically running abaverify verification tests
# Use a utility like cron or a git hook to call this script as needed

import abaverify as av


# Set options
av_auto = av.Automatic('path/to/test/dir', options={})

# Run the tests
av_auto.run()

# Post the results to github
html_test_list = av_auto.generateReport('my_cool_template_file')
html_plots = av_auto.generateRunTimePlots('a_template_for_plotting')
av_auto.commitReportToGitHub([html_test_list, html_plots], github_info)

# Post the results
html_summary = av_auto.generateReport('template_email_summary')
av_auto.emailReport(html_summary, email_info)