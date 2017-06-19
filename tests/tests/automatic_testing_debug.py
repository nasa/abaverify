#!/usr/bin/python

# Script for debugging features of automatic.py

import os
from optparse import OptionParser
import abaverify as av


def reportGenerator(archiveTestResultsJSONFile, templateName, outfile):
    report = av.TestReport.fromArchivedResult(archiveTestResultsJSONFile)
    fp = os.path.join('testOutput', outfile)
    av.Automatic.generateReport2(template=templateName, report=report, saveAs=fp)
    return fp

def email(archiveTestResultsJSONFile, templateName, recipient, saveAs):
    fp = reportGenerator(archiveTestResultsJSONFile, templateName, saveAs)
    av.Automatic.emailResults2(recipients=[recipient, ], sender='noreply@nasa.gov', body=fp)
    return

def runTimePlots(template, path_to_archived_tests, saveAs):
    av.Automatic.generateRunTimePlots2(template, path_to_archived_tests, saveAs)
    return


if __name__ == '__main__':

    parser = OptionParser(usage="automatic_testing_debug.py feature template [args]")
    parser.add_option('-r', "--reportJSONFile", action="store", dest="report_json_file", default="sample_archived_test_result.json", help="Specify a report object to use.")
    parser.add_option('-e', "--emailRecipients", action="store", dest="email_recipients", default="", help="Specify recipients to email report to.")
    parser.add_option('-o', "--output", action="store", dest="output", help="Name for output file. Required for feature=reportGenerator or runTimePlots.")
    parser.add_option('-a', "--archiveDir", action="store", dest="pathToArchiveDir", default=os.path.abspath('autoTestArchive'), help="Path to the archive directory where the test reports are stored as json. For use with runTimePlots.")
    (options, args) = parser.parse_args()

    if len(args) != 2:
        raise ValueError("Two arguments required. Found {0}".format(str(args)))
    else:
        feature = args[0]
        template = args[1]

    # Call the feature specified
    if feature == 'reportGenerator':
        if not options.output:
            parser.error("Output file name not specified.")
        reportGenerator(options.report_json_file, template, options.output)

    elif feature == 'email':
        if len(options.email_recipients) < 1:
            raise ValueError("Must specify recipients via the -e option to use the email feature.")
        email(archiveTestResultsJSONFile=options.report_json_file, templateName=template, 
            recipient=options.email_recipients, saveAs=options.output)

    elif feature == 'runTimePlots':
        if not options.output:
            parser.error("Output file name not specified.")
        runTimePlots(template, options.pathToArchiveDir, options.output)

    else:
        raise ValueError("Unknown feature specified.")
