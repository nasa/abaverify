#!/usr/bin/python
#
# Script for automated testing. Designed to be called by Cron.
#

import os
import sys
import contextlib
import subprocess
import smtplib
import email.utils
from email.mime.text import MIMEText
from email.MIMEBase import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import Encoders
import re
import inspect
import zipfile
import time
import shutil
import socket
from optparse import OptionParser


# Make sure the working directory is set appropriately (this is needed for cron)
pathForThisFile = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
os.chdir(pathForThisFile)

# Results file name
shortHash = subprocess.check_output("git rev-parse --short HEAD", shell=True).rstrip()
outputFileName = "DGD_" + shortHash + "_" + time.strftime("%Y-%b-%d")


def zipdir(path, ziph):
    # Zip a directory
    # ziph is a zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))


def run(outfile, mailTo):
    
    # Open file for output
    try:
        f = open(outfile + ".html", 'w')
        f.write("<body>")

        # Get the commit hash
        sha = subprocess.check_output("git rev-parse HEAD", shell=True)
        f.write("For more details, see the test output archive <br>\n<font color='blue'>" + socket.getfqdn() + ":" + os.path.join(os.getcwd(), "archivedTestResults", outfile + ".zip") + "</font><br><br>\n")
        f.write("Git hash: " + sha + "<br><br>\n")

        # Run the tests
        cmd = ["python", "test_runner.py", "-t"]
        if options.specifiedTest:
            cmd = cmd + [options.specifiedTest]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

        # Format results into a table
        f.write("<table border='1' cellpadding='3'>\n")
        # Headings
        f.write("<tr><b>\n")
        f.write("\t<td></td>\n")
        f.write("\t<td colspan='2' align='center'>Runing times</td>\n")
        f.write("\t<td></td>\n")
        f.write("</b></tr>\n")
        f.write("<tr><b>\n")
        f.write("\t<td>Test name & description</td>\n")
        f.write("\t<td>Packager</td>\n")
        f.write("\t<td>Solver</td>\n")
        f.write("\t<td>Status</td>\n")
        f.write("</b></tr>\n")

        # Flags for parsing
        timeCounter = 0
        endOfTable = False

        # Parse output lines & save to a log file
        for line in outputStreamer(p):

            # Formatting for HTML email

            # Match 'ok'
            if re.match(r'.*ok$', line):
                f.write("\t<td><font color='green'><b>" + line + "</b></font></td></tr>\n")

            # Match 'fail'
            elif re.match(r'.*FAIL$', line):
                f.write("\t<td><font color='red'><b>" + line + "</b></font></td></tr>\n")

            # Match lines starting with test_
            elif re.match(r'^test_.*', line):
                f.write("<tr>\n")
                if '...' in line:
                    sl = line.split('...')
                    f.write("\t<td>" + sl[0])
                    f.write("\t<td>" + sl[1].split('time: ').pop() +  "</td>\n")
                else:
                    f.write("\t<td>" + line)

            # Match ...
            elif re.match(r'.*\.\.\..*$', line):
                if 'time:' in line:
                    sl = line.split('time: ')
                    f.write("</td>\n\t<td>" + sl[1] + "</td>\n")
                else:
                    f.write(" " + line +  "</td>\n")

            # Match time:
            elif re.match(r'.*time:.*$', line):
                f.write("\t<td>" + line.split('time: ').pop() +  "</td>\n")

            # Match ----- (occurs before summary)
            elif re.match(r'^-{10,}$', line):
                if not endOfTable:
                    f.write("</table><br>")
                    endOfTable = True
                f.write(line + "<br>\n")

            # Match ===== (occurs before summary of failures)
            elif re.match(r'^={10,}$', line):
                if not endOfTable:
                    f.write("</table><br>")
                    endOfTable = True
                f.write(line + "<br>\n")

            # Other lines
            else: 
                f.write(line + "<br>\n")
    
        f.write("</body>\n")
        f.close()

    except IOError:
        print "FILE ERROR"
    
    # Put a copy of the html file in the archivedTestResults directory
    if not options.forceOverwrite:
        shutil.copy2(outfile + ".html", os.path.join('..', 'archivedTestResults', outfile + ".html"))
    

    # Generate plots of run time ----------------------
    if options.generatePlots:
        import runtimeplots as rtplots
        testsToGroup = ['test_C3D8R_failureEnvelope_sig11sig22', 
                    'test_S4R_failureEnvelope_sig11sig22', 
                    'test_C3D8R_failureEnvelope_sig12sig22',
                    'test_S4R_failureEnvelope_sig12sig22',
                    'test_C3D8R_failureEnvelope_sig12sig23',
                    'test_C3D8R_mixedModeMatrix',
                    'SingleElementTests']
        htmlFileName = 'runtime_plotly.html'
        rtplots.run(testGroups=testsToGroup, outputFileName=htmlFileName, numTestsToUse=-1)
    

    # Email report ------------------------------------
    if options.emailreport:
        msg = MIMEMultipart('alternative')
        # Read the file containing the unittest output
        with open(outfile + ".html", 'rb') as f:
            html_body = MIMEText(f.read(), "html")
            msg.attach(html_body)

        # Setup the message
        msg["from"] = 'noreply@nasa.gov'
        msg["To"] = ", ".join(mailTo)
        msg["Subject"] = "[UnitTest] DGD, Test results on master"

        # Attach image files
        imgFileNames = [x for x in os.listdir(os.path.join(os.getcwd(), 'testOutput')) if x.endswith(".png")]
        for imgFileName in imgFileNames:
            imgPath = os.path.join(os.getcwd(), 'testOutput', imgFileName)
            with open(imgPath, 'rb') as i:
                img = MIMEBase('application', 'octect-stream')
                img.set_payload(i.read())
                Encoders.encode_base64(img)
                img.add_header('Content-Disposition', 'attachment; filename=%s' % os.path.basename(imgFileName))
                msg.attach(img)

        # Attach the html plot file
        with open(htmlFileName, 'rb') as h:
            htmlFileAttachment = MIMEBase('application', 'octect-stream')
            htmlFileAttachment.set_payload(h.read())
            Encoders.encode_base64(htmlFileAttachment)
            htmlFileAttachment.add_header('Content-Disposition', 'attachment; filename=%s' % htmlFileName)
            msg.attach(htmlFileAttachment)
            
        # Attach the CompDam.parameters file
        with open(os.path.join('testOutput', 'CompDam.parameters'), 'rb') as h:
            paraFileAttachment = MIMEBase('application', 'octect-stream')
            paraFileAttachment.set_payload(h.read())
            Encoders.encode_base64(paraFileAttachment)
            paraFileAttachment.add_header('Content-Disposition', 'attachment; filename=CompDam.parameters')
            msg.attach(paraFileAttachment)
        
        # Send
        s = smtplib.SMTP('localhost')
        try:
            s.sendmail('noreply@nasa.gov', mailTo, msg.as_string())         
        finally:
            s.quit()
        
        

        # Move the html log file to the testOutput directory
        shutil.move(outfile + ".html", os.path.join('testOutput', outfile + ".html"))
        
        # Move the html plot file to the testOutput directory
        shutil.move(htmlFileName, os.path.join('testOutput', htmlFileName))

        # Copy results to an archive for backup ------------------------------------
        zipf = zipfile.ZipFile(outfile + ".zip", 'w', allowZip64=True)
        zipdir('testOutput', zipf)
        zipf.close()

        # Move the archive to storage
        if options.forceOverwrite:
            shutil.move(outfile + ".zip", os.path.join('testOutput', outfile + ".zip"))
        else:
            shutil.move(outfile + ".zip", os.path.join('..', 'archivedTestResults', outfile + ".zip"))
    
#----------------------------------------------------------------
# Copied from: http://blog.thelinuxkid.com/2013/06/get-python-subprocess-output-without.html
def outputStreamer(proc, stream='stdout'):
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


# Parse args
parser = OptionParser()
parser.add_option('-f', "--force", action="store_true", dest="forceOverwrite", default=False, help="Force overwrite of existing test results")
parser.add_option('-s', "--specifyTest", action="store", dest="specifiedTest", default="", help="Only runs the specified tests")
parser.add_option('-r', "--recipient", action="store", dest="recipient", default="", help="Specify single recipient")
parser.add_option('-n', "--noEmail", action="store_false", dest="emailreport", default=True, help="Do not attempt to send an email report")
parser.add_option('-p', "--noPlots", action="store_false", dest="generatePlots", default=True, help="Do not generate run time plots")
(options, args) = parser.parse_args()

# Distribution list for reporting the results
if options.recipient:
    recipients = [options.recipient]
else:
    recipients = ["andrew.c.bergan@nasa.gov", "frank.a.leone@nasa.gov"]

# Execute from tests directory
os.chdir(os.path.join(os.getcwd(), os.pardir, os.pardir))

# Make sure the archivedTestResults folder exists
archiveDir = os.path.join(os.getcwd(), os.pardir, 'archivedTestResults')
if not os.path.isdir(archiveDir):
    os.makedirs(archiveDir)

# Overwritting behavior
if options.forceOverwrite:
    # Prevent overwriting
    p = os.path.join(archiveDir, outputFileName + '.zip')
    if (os.path.isfile(p)):
        outputFileName = "f_" + outputFileName    
    run(outputFileName, recipients)
        
else:
    # Check to see if the current commit has been tested
    # Get the most recent test result
    files = [os.path.join(archiveDir, f) for f in os.listdir(archiveDir)]
    if len(files) > 0:
        files.sort(key=lambda x: os.path.getmtime(x))
        pathToMostRecent = files.pop()

        # Filter for files that match the naming convention
        pattern = re.compile('.*DGD_.*\.html$')
        filteredFiles = [fileName.split('/').pop() for fileName in files if pattern.match(fileName)]
        
        # Get the SHAs
        fileName = filteredFiles[-1]
        print "Most recent file " + fileName
        regex = re.compile('DGD_(.*)_')
        match = regex.search(fileName)
        if match:
            if len(match.groups()) < 1 or len(match.groups()) > 1:
                raise Exception("Error parsing file names")
            else:
                mostRecentTestResultsSHA = match.groups()[0]
            currentSHA = subprocess.check_output("git rev-parse --short HEAD", shell=True).strip()
            if (currentSHA != mostRecentTestResultsSHA):
                # Check which files have been modified. Only run tests if files in for/ or /tests have been modified
                modifiedFiles = subprocess.check_output("git diff --name-only " + mostRecentTestResultsSHA + " " + currentSHA, shell=True).strip().split('\n')
                modifiedFileParentDirs = [f.split('/')[0] for f in modifiedFiles]
                if 'for' in modifiedFileParentDirs or 'tests' in modifiedFileParentDirs:
                    print "Going to run tests"
                    run(outputFileName, recipients)
                else:
                    print "New commits, but no modifications in for/ or tests/"
                    print "git diff --name-only: "
                    print subprocess.check_output("git diff --name-only " + mostRecentTestResultsSHA + " " + currentSHA, shell=True).strip()
            else:
                print "No new commits"
    else: # case of empty archiveDir
        run(outputFileName, recipients)