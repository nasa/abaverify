"""
This module provides functionality to run abaverify tests automatically.

The intended use case of this module is for automatic verification testing of
user subroutines during development. A script (see
sample_automatic_testing_script.py for example) can be setup with cron for
execution of verification tests at regular intervals.

The functionality provided in this module includes generating reports of test
results and run times, generating plots of current and archived run times (to
show trends in run times), archiving results, and delivering reports via email.

"""

import os
import sys
import subprocess
import contextlib
import re
import json
import time
import zipfile
import shutil
import inspect
import socket
import datetime as dt
import plotly.offline as ply
import plotly.graph_objs as plygo
import smtplib
from email.mime.text import MIMEText
from email.MIMEBase import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import Encoders

import pprint
pp = pprint.PrettyPrinter(indent=4)


class Automatic():
    """
    Main functionality for the automatic module.

    See `/scripts/sample_automatic_testing_script.py` and
    `tests/tests/automatic_testing_script.py` for example of how to use the
    functionality provided in this class.

    Attributes
    ----------
    test_directory : :obj:`str`
        Path to the directory with the tests to execute.
    archive_directory : :obj:`str`
        Path to the directory to use for storing the test results.
    repository_name : :obj:`str`
        Name of the user subroutine repository. This is used for naming files 
        and reports.
    repository_remote : :obj:`str`
        Name of git remote for the upstream repository. Used for automatically 
        executing `git pull` to ensure that the repo is up to date.
    repository_branch : :obj:`str`
        Name of the git branch for the upstream repository. Used for 
        automatically executing `git pull` to ensure that the repo is up to date.
    update_repo : bool
        Determines if a `git pull` is executed.
    test_runner_file_name : :obj:`str`
        Name of the file that defines the tests. For example: test_runner.py
    time_tests : bool
        Record test durations if true.
    precompile : bool
        Compile the subroutine once before running all tests. Equivalent to abaverify 
        -c command line option.
    cpus : int
        Run tests with the specified number of cpus.
    force_tests : bool
        Runs tests even if there are no changes to the repo.
    verbose : bool
        Logs details of parsing files. Useful for debugging.
    tests_to_run : list
        Tests to run. Defaults to all tests in test_runner_file_name.
    test_report : :obj:`TestReport`
        Test report instance.
    formatted_reports : dict
        Dictionary with each entry being a test results report formatted for 
        humans.
    run_time_plot_file_path : :obj:`str`
        Path to the run time plots file.

    """

    #
    # Public API
    #
    def __init__(self, test_directory, archive_directory, repository=None, test_runner_file_name='test_runner.py',
                 time_tests=True, precompile=False, cpus=1, force_tests=False, verbose=False, tests_to_run=[], abaqus_cmd='abaqus'):
        """
        Creates an instance of Automatic.

        Most of the arguments correspond with public attributes and can be set in
        the constructor or by modifying the attribute directly. 

        """

        # ----------------------------------------------------------------------
        # Required arguments
        self.test_directory = test_directory
        self.archive_directory = archive_directory

        # Execute from the test directory
        os.chdir(test_directory)

        # Make sure the archive directory exists
        if not os.path.isdir(archive_directory):
            os.makedirs(archive_directory)

        # ----------------------------------------------------------------------
        # Load options

        # Get the repository information
        # This attribute defines whether the code should attempt to git pull to
        # get new commits in the tested repo
        self.update_repo = False
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
            raise ValueError(
                "The argument repository for Automatic initialization must be a string or a dictionary.")

        # Update repo
        if self.update_repo:
            subprocess.check_output(
                "git pull " + self.repository_remote + " " + self.repository_branch, shell=True)

        # Name of the file that defines the tests
        self.test_runner_file_name = test_runner_file_name

        # Collect test durations?
        self.time_tests = time_tests

        # Abaverify -c option. Precompile abaqus subroutine before running
        # tests.
        self.precompile = precompile

        # Run with multiple cpus
        self.cpus = cpus

        # Runs tests even if there are no changes to the repo
        self.force_tests = force_tests

        # Log parsing data
        self.verbose = verbose
        self.verbose_parse_log = ''

        # List of tests to run [default is an empty list, in which case all
        # tests are run]
        if not(type(tests_to_run) is list):
            raise ValueError(
                "The argument tests_to_run for Automatic must be a list")
        self.tests_to_run = tests_to_run

        # Abaqus cmd (allows override to run a nondefault version of abaqus)
        self.abaqus_cmd = abaqus_cmd

        # ----------------------------------------------------------------------
        # Initialize a new test report

        # Test report init
        self.test_report = TestReport()

        # Initialize a dict to store formated reports
        self.formatted_reports = dict()

        # Initialize attribute that stores the path to the run time plot file
        self.run_time_plot_file_path = ""

        # Print configuration if verbose is on
        if self.verbose:
            _logVerbose(self.__dict__)

        return

    def run(self):
        """
        Run the tests and build a testReport object with the results.

        This function runs the tests using the current configuration. Once the
        configuration has been setup using the object constructor and/or by
        modifying the attributes, use this function to run the analysis test
        cases.

        """

        # Get the sha of the current commit
        sha = subprocess.check_output(
            "git rev-parse --short HEAD", shell=True).rstrip()
        self.test_report.metaData['sha'] = sha

        # Check if there are uncommitted changes
        try:
            subprocess.check_call('git diff --quiet', shell=True)
            self.test_report.metaData['uncommited_changes'] = False
        except Exception:
            self.test_report.metaData['uncommited_changes'] = True
            if self.verbose:
                _logVerbose("Found uncommitted changes")

        # Check if the current commit has been tested (and directory there are
        # no uncommitted changes)
        if not self.force_tests and _currentCommitTested(self.archive_directory, self.verbose):
            print "No new commits"
            return False

        # Get abaqus version
        abq_version_response = subprocess.check_output(
            self.abaqus_cmd + " information=release", shell=True)
        self.abaqus_version = abq_version_response.split('\n')[1]
        self.test_report.metaData['abaqus_version'] = self.abaqus_version
        if self.verbose:
            _logVerbose("Running on abaqus version: " + self.abaqus_version)

        # Build the command to run the tests
        cmd = ["python", self.test_runner_file_name,
               "--abaqusCmd", self.abaqus_cmd]
        if self.time_tests:
            cmd.append("-t")
        if self.precompile:
            cmd.append("-c")
        if self.cpus > 1:
            cmd.append("-C " + self.cpus)
        if self.tests_to_run:
            cmd = cmd + self.tests_to_run
        if self.verbose:
            _logVerbose("Running abaverify: " + " ".join(cmd))
        # Run the tests
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, universal_newlines=True)

        # Parse output lines & save to a log file
        for line in _outputStreamer(p):
            self._parseLine(line)

        # Set file name
        self.base_file_name = self.repository_name + \
            '_' + sha + '_' + time.strftime("%Y-%b-%d")
        if self.test_report.metaData['uncommited_changes']:
            self.base_file_name = 'uc_' + self.base_file_name

        # Archive the report
        trpath = os.path.join(self.archive_directory,
                              self.base_file_name + '.json')
        with open(trpath, 'w') as outfile:
            json.dump(self.test_report.getDict(), outfile)
        if self.verbose:
            _logVerbose("Archived test report at: " + trpath)

        # Parsing log
        if self.verbose:
            parseing_log_name = os.path.join(self.archive_directory,
                self.base_file_name + '.log')
            with open(parseing_log_name, 'w+') as f:
                f.write(self.verbose_parse_log)

        # zip job files and copy to the archive directory
        zipf = zipfile.ZipFile(self.base_file_name +
                               ".zip", 'w', allowZip64=True)
        _zipdir('testOutput', zipf)
        zipf.close()

        # Move the archive to storage
        shutil.move(self.base_file_name + ".zip",
                    os.path.join(self.archive_directory, self.base_file_name + ".zip"))

        # Return the report obj
        return True

    def generateReport(self, template):
        """
        Returns a report (string) containing the test results.

        This function uses a basic templating approach to generate a report
        using the test results and the supplied report template. The report
        template file is used to format the report. It is presumed that the
        report is formatted with html, though other mark up languages should be
        compatible.

        Parameters
        ----------
        template : :obj:`str`
            String specifying the name of python file (without the .py
            extension). The template file must be located in the `templates`
            directory, the current directory, or somewhere else in the python 
            path. The template file should follow the pattern of the sample
            report template `template_email_summary`.

        Returns
        -------
        string
            String containing the complete report with results substituted.

        """

        # Build the report
        ptat = os.path.join(self.archive_directory, self.base_file_name)
        rpt_str = _generateReport(
            template=template, report=self.test_report, path_to_archived_tests=ptat)

        # Name for report file
        saveAs = os.path.join(self.archive_directory,
                              self.base_file_name + '.html')

        # Write report to file
        with open(saveAs, 'w') as outfile:
            outfile.write(rpt_str)
        self.formatted_reports[template] = saveAs
        return rpt_str

    @classmethod
    def generateReport2(cls, template, report, saveAs):
        """
        Static call to generateReport. Here for debugging purposes.
        """
        rpt_str = _generateReport(template=template, report=report)
        with open(saveAs, 'w') as outfile:
            outfile.write(rpt_str)
        return rpt_str

    def generateRunTimePlots(self, template):
        """
        Create run time plots using the plotly library.

        This function uses a templating approach to generate an html file
        containing plotly plots of run time. The run times of historical tests
        are used to show the trends in run time. The file is returned as a
        string.

        Parameters
        ----------
        template : :obj:`str`
            String specifying the name of python file (without the .py
            extension). The template file must be located in the `templates`
            directory, the current directory, or somewhere else in the python 
            path. The template file should follow the pattern of the sample
            report template `template_run_time_plots`.

        Returns
        -------
        string
            String containing the html file with the plots.

        Notes
        -----
        See the CompDam_DGD repository for a full-featured implementation of the 
        run time plot functionality.

        """

        plt_str = _generateRunTimePlots(
            template=template, path_to_archived_tests=self.archive_directory, verbose=self.verbose)

        # Name for report file
        saveAs = os.path.join(self.archive_directory,
                              self.base_file_name + '_' + template + '.html')

        # Write report to file
        with open(saveAs, 'w') as outfile:
            outfile.write(plt_str)

        # Store a reference to the run time plots
        self.run_time_plot_file_path = saveAs

        return plt_str

    @classmethod
    def generateRunTimePlots2(cls, template, path_to_archived_tests, saveAs, verbose=False):
        """
        Static call to generateRunTimePlots. Here for debugging purposes.
        """
        plt_str = _generateRunTimePlots(
            template=template, path_to_archived_tests=path_to_archived_tests, verbose=verbose)
        with open(saveAs, 'w') as outfile:
            outfile.write(plt_str)
        return plt_str

    def emailResults(self, recipients, sender, template, attachments=[]):
        """
        Email test results.

        This function is useful to alert people of the test results immediately
        when the tests complete.

        Parameters
        ----------
        recipients : list of str or str
            Email addresses of recipients.
        sender : :obj:`str`
            Email sender. For example: noreply@domain.com
        template : :obj:`str`
            String specifying the name of python file (without the .py
            extension). The template file must be located in the `templates`
            directory, the current directory, or somewhere else in the python 
            path. The template file should follow the pattern of the sample
            report template `template_email_summary`.
        attachments : list, optional
            List of paths to files that should be included as attachments in the 
            email.

        """

        # If the report has already been run, use it
        if template in self.formatted_reports:
            body_path = self.formatted_reports[template]

        # Otherwise run the report
        else:
            self.generateReport(template=template)
            body_path = self.formatted_reports[template]

        if self.verbose:
            _logVerbose("Path to html file for email body: " + body_path)
            _logVerbose("Sending email to " + str(recipients))

        # Package repository info to pass to _emailResults
        repo_info = {'name': self.repository_name,
                     'branch': self.repository_branch}

        # Add run time plot file as attachment to email
        if self.run_time_plot_file_path:
            attachments.append(self.run_time_plot_file_path)

        if self.verbose:
            _logVerbose("Attachments: " + str(attachments))

        # Call helper to send the email
        _emailResults(recipients=recipients, sender=sender, body=body_path,
                      attachments=attachments, repository_info=repo_info)
        return

    @classmethod
    def emailResults2(cls, recipients, sender, body, attachments=[], repository_info=None):
        """
        Static call to emailResults. Here for debugging purposes.
        """
        if repository_info is None:
            repository_info = {'name': 'repo_name_placeholder',
                               'branch': 'repo_branch_placeholder'}

        _emailResults(recipients, sender, body, attachments, repository_info)
        return

    #
    # Locals
    #

    def _getRepoName(self):
        repo_path = subprocess.check_output(
            "git rev-parse --show-toplevel", shell=True).strip()
        return repo_path.split('/').pop()

    def _parseLine(self, line):
        """
        Parses output from test_runner.py
        """

        # Match 'ok'
        if re.match(r'.*ok$', line):
            if self.verbose:
                self.verbose_parse_log += _logParsing("MATCHED", line)
            self.test_report.setTestResult(True)

        # Match 'fail'
        elif re.match(r'.*FAIL$', line):
            if self.verbose:
                self.verbose_parse_log += _logParsing("MATCHED", line)
            self.test_report.setTestResult(False)

        # Match lines starting with test_
        # These lines indicate the start of a new test
        elif re.match(r'^test_.*', line):
            if '...' in line:
                if self.verbose:
                    self.verbose_parse_log += _logParsing("MATCHED", line)
                sl = line.split('...')
                s2 = sl[0].split(' (')
                self.test_report.addTestResult(s2[0])

            else:
                if self.verbose:
                    self.verbose_parse_log += _logParsing("MATCHED", line)
                s2 = line.split(' (')
                self.test_report.addTestResult(s2[0])

        # Match time:
        elif re.match(r'.*time:.*$', line):
            if self.verbose:
                self.verbose_parse_log += _logParsing("MATCHED", line)
            match = re.search(r'^([a-zA-Z]*)[\w ]*: ([0-9\.]*) s$', line)
            self.test_report.setRunTime(category=match.group(
                1).lower(), duration=match.group(2))

        # Match summary
        elif re.match(r'Ran ([0-9]*) test[s]* in ([0-9\.]*)s$', line):
            match = re.search(r'Ran ([0-9]*) test[s]* in ([0-9\.]*)s$', line)
            self.test_report.setSummaryPassed(
                int(match.group(1)), match.group(2))

        # Failed summary
        elif re.match(r'FAILED', line):
            match = re.search(r'FAILED \([a-z]*=([0-9]*)[, =a-z1-9]*\)$', line)
            if match:
                if self.verbose:
                    self.verbose_parse_log += _logParsing("MATCHED", line)
                self.test_report.setSummaryFailed(int(match.group(1)))
            else:
                if self.verbose:
                    self.verbose_parse_log += _logParsing("NOT MATCHED", line)
                self.test_report.setSummaryFailed(-1)

        # Other lines
        else:
            if self.verbose:
                self.verbose_parse_log += _logParsing("NOT MATCHED", line)


#
# Helper functions
#

def _currentCommitTested(archive_directory, verbose=False):
    """
    Checks if the current SHA has an archived result
    """

    # Get current SHA
    currentSHA = subprocess.check_output(
        "git rev-parse --short HEAD", shell=True).strip()
    if verbose:
        _logVerbose("Current SHA: {0}".format(currentSHA))

    # Get most recent SHA in archive dir
    mostRecentTestResultsSHA = ''
    files = [os.path.join(archive_directory, f)
             for f in os.listdir(archive_directory)]
    if len(files) > 0:
        files.sort(key=lambda x: os.path.getmtime(x))
        pathToMostRecent = files.pop()

        if verbose:
            _logVerbose(
                "Most recent results file name: {0}".format(pathToMostRecent))

        match = re.search(
            r'.*([a-zA-Z0-9]{7})_.*\.(html|json|zip)$', pathToMostRecent.split('/').pop())
        if match:
            if len(match.groups()) != 2:
                raise Exception(
                    "Error parsing file names in archive directory")

            mostRecentTestResultsSHA = match.groups()[0]
            if verbose:
                _logVerbose("Most recently tested SHA: {0}".format(
                    mostRecentTestResultsSHA))

    # Compare SHAs
    if (currentSHA == mostRecentTestResultsSHA):
        return True
    else:
        return False


def _generateReport(template, report, path_to_archived_tests=""):
    """
    Return the template with the test report data substituted 
    """

    # Add the templates directory to the path
    pathForThisFile = os.path.dirname(os.path.abspath(
        inspect.getfile(inspect.currentframe())))
    sys.path.append(os.path.join(pathForThisFile, os.pardir, 'templates'))

    # Load the template file
    templ = __import__(template)

    # Build string of test results
    test_result_formatted_str = ""
    for tr in report.test_results:
        c = 'green' if tr.test_status else 'red'
        test_result_formatted_str += templ.test_result.format(test_name=tr.test_name, packager_time=tr.run_times['packager'],
                                                              solver_time=tr.run_times['solver'], status_color=c, status_text=tr.test_status)

    # Build string for body
    ntestspass = report.summary['number_tests'] - \
        report.summary['number_failed']
    body_formatted_str = templ.body.format(fqdn=socket.getfqdn(), path_to_archived_tests=path_to_archived_tests, git_sha=report.metaData['sha'], test_results=test_result_formatted_str,
                                           number_of_tests_run=report.summary['number_tests'], total_duration=report.summary[
                                               'duration'], num_tests_passed=ntestspass,
                                           num_tests_failed=report.summary['number_failed'], abaqus_version=report.metaData['abaqus_version'])

    return body_formatted_str


def _generateRunTimePlots(template, path_to_archived_tests, verbose=False):
    """
    Populate the plot template with data from the path_to_archived_tests
    Returns a string containing the html
    """

    # Add the templates directory to the path
    pathForThisFile = os.path.dirname(os.path.abspath(
        inspect.getfile(inspect.currentframe())))
    sys.path.append(os.path.join(pathForThisFile, os.pardir, 'templates'))

    # Load the template file
    templ = __import__(template)

    # Read the json files into test_data
    # tests[<test_name>] = [{'date': <date>, 'commit': <>, 'runTime':
    # <testRunTime>, 'passed': <bool>}, ...]
    test_data = dict()
    jsonfiles = [f for f in os.listdir(
        path_to_archived_tests) if f.endswith('.json')]
    # jsonfiles = glob.glob('path_to_archived_tests/*json')
    jsonfiles.sort(key=lambda x: os.path.getmtime(
        os.path.join(path_to_archived_tests, x)))
    for jsonfile in jsonfiles:
        if verbose:
            _logVerbose("processing file " + jsonfile)

        # Parse file name to get testDate
        matches = re.match(
            r'.*_([0-9]{4}-[a-zA-Z]{3}-[0-9]+)\.json$', jsonfile)
        if matches:
            grps = matches.groups()
            if len(grps) != 1:
                raise Exception("Failed while attempting to parse file name")
            # Get the date
            test_date = dt.datetime.strptime(grps[0], '%Y-%b-%d').date()

        # Load test report as a dictionary
        test_report = TestReport.fromArchivedResult(
            os.path.join(path_to_archived_tests, jsonfile)).getDict()

        # Loop through tests results and gather the run times
        for test_result in test_report['test_results']:
            # Add test result to collection of data
            test_name = test_result['test_name']
            if test_name not in test_data:
                test_data[test_name] = list()
            test_data[test_name].append({'date': test_date, 'commit': test_report['metaData'][
                                        'sha'], 'runTime': test_result['run_times']['solver'], 'passed': test_result['test_status']})

    # Storage for plotly data, key is figure title
    plotly_data_dict = dict()

    # Create an empty dict if the test_groups option is not used in the
    # template
    if not hasattr(templ, 'test_group_prefixes'):
        templ.test_group_prefixes = []

    # Loop through the collection of run times and build the data structures
    # to plot
    for test_name in test_data.keys():

        # Sort the data into the appropriate figure accounting for the
        # test_group_prefixes
        fig_title = ''
        for test_group in templ.test_group_prefixes:
            if test_group in test_name:
                fig_title = test_group
                if verbose:
                    _logVerbose("Adding {} to figure number {}".format(
                        str(test_name), str(fig_title)))
                break
        if not fig_title:
            fig_title = test_name

        # Collect the data
        x = [item[templ.x_axis_qty] for item in test_data[test_name]]
        y = [item['runTime'] for item in test_data[test_name]]

        # Create a dictionary entry if it doesn't exist already
        if fig_title not in plotly_data_dict:
            plotly_data_dict[fig_title] = list()

        # Add the run time data to plotly_data_dict
        plotly_data_dict[fig_title].append(plygo.Scatter(
            x=x, y=y, mode="lines", name=test_name, text=test_name, hoverinfo="text+x+y"))

    # Initializations
    include_plotlyjs = True      # Only need to include plotlyjs once
    plot_html_str = ""           # Build html string to return
    toc = ""

    # Create an empty dict if the test_groups option is not used in the
    # template
    if not hasattr(templ, 'chart_groups'):
        templ.chart_groups = {}

    # Loop trhough chart_groups
    for chart_group_key in templ.chart_groups.keys():

        subsection_toc = ""
        subsection_plots = ""

        # Load each chart in the subsection
        for chart_name in templ.chart_groups[chart_group_key]['charts']:

            if chart_name not in plotly_data_dict.keys():
                raise ValueError(
                    'The chart name {0} specified in the template file is not valid'.format(chart_name))

            # Generate plot html
            subsection_plots += _plotly_helper(template=templ, chart_name=chart_name,
                                               plotly_data_dict=plotly_data_dict, include_plotlyjs=include_plotlyjs)

            # Only include plotly js once
            if include_plotlyjs:
                include_plotlyjs = False

            subsection_toc += templ.toc.format(plot_title=chart_name)

            # Remove chart from plotly_data_dict
            del plotly_data_dict[chart_name]

        # Subsection heading
        plot_html_str += templ.subsection.format(section_name_dashes=chart_group_key,
                                                 section_name=templ.chart_groups[chart_group_key]['name_pretty'], plots=subsection_plots)

        # Add section to table of contents
        toc += templ.subsection_toc_wrapper.format(section_name_dashes=chart_group_key,
                                                   section_name=templ.chart_groups[chart_group_key]['name_pretty'], toc_entries=subsection_toc)

    # Loop through charts that are not in chart_groups
    for chart_name in plotly_data_dict.keys():
        # Generate plot html
        plot_html_str += _plotly_helper(template=templ, chart_name=chart_name,
                                        plotly_data_dict=plotly_data_dict, include_plotlyjs=include_plotlyjs)

        # Only include plotly js once
        if include_plotlyjs:
            include_plotlyjs = False

        if hasattr(templ, 'toc'):
            toc += templ.toc.format(plot_title=chart_name)

    # Final substitution
    html_str = templ.body.format(plots=plot_html_str, toc=toc)

    return html_str


def _plotly_helper(template, chart_name, plotly_data_dict, include_plotlyjs):
    # Formatting
    layout = dict(title=chart_name, yaxis=dict(title='Solver run time [s]'), showlegend=False,
                  height=template.plot_height, width=template.plot_width,)

    # Create the figure
    fig = dict(data=plotly_data_dict[chart_name], layout=layout)
    plotlyhtml = ply.plot(fig, output_type='div',
                          include_plotlyjs=include_plotlyjs)
    return template.plot.format(plot=plotlyhtml, plot_title=chart_name)


def _emailResults(recipients, sender, body, attachments, repository_info):
    """
    Emails results
    recipients = list
    body = path to file containing body of email (assumes the file is html)
    attachments = ['path_to_file', ]
    repository_info = {'name': , 'branch': }
    """

    if type(recipients) is str:
        recipients = [recipients, ]

    msg = MIMEMultipart('alternative')

    # Read the file containing the unittest output
    with open(body, 'rb') as f:
        html_body = MIMEText(f.read(), "html")
        msg.attach(html_body)

    # Setup the message
    msg["from"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = "[abaverify] Repository: " + \
        repository_info['name'] + "; Branch: " + repository_info['branch']

    # Process attachments
    for attachment in attachments:
        with open(attachment, 'rb') as h:
            file_attachment = MIMEBase('application', 'octect-stream')
            file_attachment.set_payload(h.read())
            Encoders.encode_base64(file_attachment)
            file_attachment.add_header(
                'Content-Disposition', 'attachment; filename=%s' % os.path.basename(attachment))
            msg.attach(file_attachment)

    # Send
    s = smtplib.SMTP('localhost')
    try:
        s.sendmail(sender, recipients, msg.as_string())
    finally:
        s.quit()


def _outputStreamer(proc, stream='stdout'):
    """
    Handles streaming of subprocess.
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
    msg = status + ": " + line
    print msg
    sys.stdout.flush()
    return msg + '\n'


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
        self.test_status = status  # False = failed; True = passed
        self.run_times = {'compile': compile_duration,
                          'packager': package_duration, 'solver': solve_duration}

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
        self.summary['number_tests'] = 0
        self.summary['number_failed'] = 0

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
