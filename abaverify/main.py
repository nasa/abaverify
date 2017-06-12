"""
This is the main API for the abaverify package.
"""
import unittest
from optparse import OptionParser
import sys
import platform
import os
import re
import shutil
import subprocess
import contextlib
import itertools as it
import time
import inspect
import getpass
import datetime
import pprint

#
# Local
#

class _measureRunTimes:
    """
    Measures run times during unit tests
    """

    def __init__(self):
        self.runtimes = dict()


    def processLine(self, line):
        """ Helper function to mark the start and end times """

        if re.match(r'Begin Linking', line):
            self.Compile_start = time.time()
        elif re.match(r'End Linking', line):
            self.Compile_end = time.time()
            self.compile_time = self.Compile_end - self.Compile_start
            sys.stderr.write("\nCompile run time: {:.2f} s\n".format(self.compile_time))

        elif re.match(r'Begin Abaqus/Explicit Packager', line):
            self.packager_start = time.time()
        elif re.match(r'End Abaqus/Explicit Packager', line):
            self.packager_end = time.time()
            self.package_time = self.packager_end - self.packager_start
            sys.stderr.write("Packager run time: {:.2f} s\n".format(self.package_time))

        elif re.match(r'Begin Abaqus/Explicit Analysis', line):
            self.solver_start = time.time()
        elif re.match(r'End Abaqus/Explicit Analysis', line) or re.match(r'.*Abaqus/Explicit Analysis exited with an error.*', line):
            self.solver_end = time.time()
            self.solver_time = self.solver_end - self.solver_start
            sys.stderr.write("Solver run time: {:.2f} s\n".format(self.solver_time))


def _versiontuple(v):
    """
    Converts a version string to a tuple
    """
    return tuple(map(int, (v.split("."))))


def _callAbaqus(cmd, log, timer=None, shell=True):
    """
    Logic for calls to abaqus. Support streaming the output to the log file.
    """

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, shell=shell)

    # Parse output lines & save to a log file
    for line in _outputStreamer(p):

        # Time tests
        if options.time:
            if timer != None:
                timer.processLine(line)

        # Log data
        log.write(line + "\n")
        if options.interactive:
            print line


def _callAbaqusOnRemote(cmd, log, timer=None):
    """
    Logic for calls to abaqus on a remote server. Support streaming the output to the log file.
    """

    if options.verbose: print "Calling abaqus on the remote host"
    stdin, stdout, stderr = options.ssh.exec_command('cd ' + options.remote_run_directory + '; ' + cmd + ' >& /dev/stdout')
    stdin.close()
    for line in iter(lambda: stdout.readline(2048), ""):

        # Time tests
        if options.time:
            if timer != None:
                timer.processLine(line)

        # Log data
        log.write(line)
        if options.interactive:
            print line
            sys.stdout.flush()


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


def _compileCode(libName):
    """
    Default procedure to pre-compile a subroutine using abaqus make
    """

    # Put a copy of the environment file in the /for directory
    shutil.copyfile(os.path.join(os.getcwd(), 'abaqus_v6.env'), os.path.join(os.getcwd(), os.pardir, 'for', 'abaqus_v6.env'))

    # Change directory to /for
    os.chdir(os.path.join(os.pardir, 'for'))

    # Run abaqus make
    if (platform.system() == 'Linux'):
        shell = False
    else:
        shell = True
    try:
        f = open(os.path.join(os.getcwd(), os.pardir, 'tests', 'testOutput', 'compile.log'), 'a')
        _callAbaqus(cmd=['abaqus', 'make', 'library='+libName], log=f, shell=shell)
    finally:
        f.close()

    # Remove env file from /for
    os.remove(os.path.join(os.getcwd(), 'abaqus_v6.env'))

    # Make sure build directory exists
    if not os.path.isdir(os.path.join(os.pardir, 'build')):
        os.makedirs(os.path.join(os.pardir, 'build'))

    # Copy binaries into /build
    numBinariesFound = 0
    pattern  = re.compile('.*(\.dll|\.obj|\.so|\.o)$')
    for f in os.listdir(os.getcwd()):
        if pattern.match(f):
            numBinariesFound += 1
            shutil.copyfile(os.path.join(os.getcwd(), f), os.path.join(os.pardir, 'build', f))
            os.remove(os.path.join(os.getcwd(), f))

    if numBinariesFound < 4:
        raise Exception("ERROR: Abaqus make failed")

    # Change directory to /tests/
    os.chdir(os.path.join(os.pardir, 'tests'))



#
# Public facing API
#

class TestCase(unittest.TestCase):
    """
    Base class that includes generic functionality to run verification tests.

    This class adds functionality that is specific to abaqus verification tests
    to the unittests.Testcase class.

    """

    def tearDown(self):
        """
        Removes Abaqus temp files. This function is called by unittest.
        """
        files = os.listdir(os.getcwd())
        patterns = [re.compile('.*abaqus.*\.rpy.*'), re.compile('.*abaqus.*\.rec.*'), re.compile('.*pyc')]
        [os.remove(f) for f in files if any(regex.match(f) for regex in patterns)]


    def runTest(self, jobName):
        """
        Run a verification test.

        This method should be called to run a verification test. A verification
        tests includes running an abaqus analysis, post-processing the results,
        and running assertions on the results. This method includes logic that 
        performs each of these three steps.

        Parameters
        ----------
        jobName : str
            The name of the abaqus input deck (without the .inp file extension). 
            Abaverify assumes that there is a corresponding file named 
            <jobName>_expected.py that defines the expected results.

        """

        if options.verbose or options.interactive: print ""

        # Save output to a log file
        with open(os.path.join(os.getcwd(), 'testOutput', jobName + '.log'), 'w') as f:

            # Time tests
            if options.time:
                timer = _measureRunTimes()
            else:
                timer = None

            # Execute the solver
            if not options.useExistingResults:
                self._runModel(jobName=jobName, logFileHandle=f, timer=timer)

            # Execute process_results script load ODB and get results
            if options.host == "localhost":
                if not os.path.isfile(os.path.join(os.getcwd(), 'testOutput', jobName + '.odb')):
                    raise Exception("Error: Abaqus odb was not generated. Check the log file in the testOutput directory.")
                pathForProcessResultsPy = '"' + os.path.join(ABAVERIFY_INSTALL_DIR, 'processresults.py') + '"'
                _callAbaqus(cmd=options.abaqusCmd + ' cae noGUI=' + pathForProcessResultsPy + ' -- -- ' + jobName, log=f, timer=timer)

            else: # Remote host
                self.callAbaqusOnRemote(cmd=options.abaqusCmd + ' cae noGUI=processresults.py -- -- ' + jobName, log=f, timer=timer)
                try:
                    ftp = options.ssh.open_sftp()
                    ftp.chdir(options.remote_run_directory)
                    try:
                        ftp.get(jobName + '_results.py', 'testOutput/' + jobName + '_results.py')
                    except:
                        pass
                    if options.remote['copy_results_to_local']:
                        for ext in options.remote['file_extensions_to_copy_to_local']:
                            try:
                                ftp.get(jobName + ext, 'testOutput/' + jobName + ext)
                            except:
                                pass
                        for fn in options.remote['files_to_copy_to_local']:
                            try:
                                ftp.get(fn, 'testOutput/' + fn)
                            except:
                                pass
                finally:
                    ftp.close()

        # Run assertions
        self._runAssertionsOnResults(jobName)


    def _runModel(self, jobName, logFileHandle, timer):
        """
        Submits the abaqus job.

        This method handles preparing and submitting the abaqus job. The abaqus
        command is built with the options specified at run time. The job files
        are copied to a directory called testOutput. 

        Parameters
        ----------
        jobName : str
            The name of the abaqus input deck (without the .inp file extension).
        logFileHandle : :obj:`file`
            A file handle to the file used for storing output
        timer : :obj:`_measureRunTimes`

        """

        if not options.precompileCode:
            # Platform specific file extension for user subroutine
            if options.host == "localhost":
                if platform.system() == 'Linux':
                    subext = '.f'

                    # Make sure .f exists, if not create a symbolic link
                    if not os.path.isfile(os.path.join(os.getcwd(), options.relPathToUserSub + subext)):
                        os.symlink(os.path.join(os.getcwd(), options.relPathToUserSub + '.for'), os.path.join(os.getcwd(), options.relPathToUserSub + subext))
                else:
                    subext = '.for'
            else:
                subext = '.f'

            # Path to user subroutine
            if options.host == "localhost":
                userSubPath = os.path.join(os.getcwd(), options.relPathToUserSub + subext)
            else:
                userSubPath = os.path.basename(options.relPathToUserSub) + subext
            if options.verbose: print "Using subroutine: " + userSubPath

        # Copy input deck
        if options.host == "localhost":
            shutil.copyfile(os.path.join(os.getcwd(), jobName + '.inp'), os.path.join(os.getcwd(), 'testOutput', jobName + '.inp'))
        else:
            try:
                ftp = options.ssh.open_sftp()
                ftp.chdir(options.remote_run_directory)
                ftp.put(jobName + '.inp', jobName + '.inp')
                if options.verbose: print "Copying: " + jobName + '.inp'
                ftp.put(jobName + '_expected.py', jobName + '_expected.py')
                if options.verbose: print "Copying: " + jobName + '_expected.py'
            finally:
                ftp.close()

        # build abaqus cmd
        cmd = options.abaqusCmd + ' job=' + jobName
        if not options.precompileCode:
            cmd += ' user="' + userSubPath + '"'
        if options.cpus > 1:
            cmd += ' cpus=' + str(options.cpus)
        cmd += ' double=both interactive'
        if options.verbose: print "Abaqus command: " + cmd

        # Copy parameters file, if it exists
        if options.host == "localhost":
            parameterName = 'CompDam.parameters'
            parameterPath = os.path.join(os.getcwd(), parameterName)
            if os.path.exists(parameterPath):
                shutil.copyfile(parameterPath, os.path.join(os.getcwd(), 'testOutput', parameterName))

        # Run the test from the testOutput directory
        if options.host == "localhost":
            os.chdir(os.path.join(os.getcwd(), 'testOutput'))
            _callAbaqus(cmd=cmd, log=logFileHandle, timer=timer)
            os.chdir(os.pardir)
        else:
            _callAbaqusOnRemote(cmd=cmd, log=logFileHandle, timer=timer)


    def _runAssertionsOnResults(self, jobName):
        """
        Runs assertions on each result specified in the <jobName>_results.py file.

        Applies the appropriate unittest assertion based on the data in the 
        <jobName>_results.py file. The <jobName>_results.py file is generated by 
        the processresults.py module.

        Parameters
        ----------
        jobName : str
            The name of the abaqus input deck (without the .inp file extension).

        """

        outputFileName = jobName + '_results.py'
        outputFileDir = os.path.join(os.getcwd(), 'testOutput')
        if (os.path.isfile(os.path.join(outputFileDir, outputFileName))):
            sys.path.insert(0, outputFileDir)
            results = __import__(outputFileName[:-3]).results

            for r in results:

                # Loop through values if there are more than one
                if hasattr(r['computedValue'], '__iter__'):
                    for i in range(0, len(r['computedValue'])):
                        self.assertAlmostEqual(r['computedValue'][i], r['referenceValue'][i], delta=r['tolerance'][i])

                else:
                    if "tolerance" in r:
                        self.assertAlmostEqual(r['computedValue'], r['referenceValue'], delta=r['tolerance'])
                    elif "referenceValue" in r:
                        self.assertEqual(r['computedValue'], r['referenceValue'])
                    else:
                        # No data to compare with, so pass the test
                        pass
        else:
            self.fail('No results file provided by process_results.py')


class ParametricMetaClass(type):
    """
    Provides functionality for parametric testing.

    Classes that inherit this class may have models defined inp decks or python 
    scripts.

    Expects that the inheriting class defines:

    __metaclass__ = av.ParametricMetaClass

    baseName: The name of the input deck to use as a template (without the .inp)

    parameters: a dictionary with each parameter to vary. For example: 
    {'alpha': range(-40,10,10), 'beta': range(60,210,30)}

    [optional] expectedpy_parameters: a dictionary with the result for each 
    parameter value
    
    More info on meta classes: http://stackoverflow.com/a/20870875

    """

    def __new__(mcs, name, bases, dct):

        def make_test_function(testCase):
            """
            Creates test_ function for the particular test case passed in
            """

            items = testCase.items()

            jobName = testCase['name']
            baseName = testCase['baseName']
            parameters = {k: v for k, v in items if not k in ('baseName', 'name')}


            def test(self):

                if options.verbose or options.interactive: print ""

                try:
                    # Create the input deck
                    # Copy the template input file
                    if 'pythonScriptForModel' in testCase:
                        inpFilePath = os.path.join(os.getcwd(), jobName + '.py')
                        shutil.copyfile(os.path.join(os.getcwd(), baseName + '.py'), inpFilePath)
                    else:
                        inpFilePath = os.path.join(os.getcwd(), jobName + '.inp')
                        shutil.copyfile(os.path.join(os.getcwd(), baseName + '.inp'), inpFilePath)

                    # Update all of the relevant *Parameter terms in the Abaqus input deck
                    with file(inpFilePath, 'r') as original:
                        data = original.readlines()
                    for p in parameters.keys():
                        for line in range(len(data)):
                            if re.search('.{0,}' + str(p) + '.{0,}=.{0,}$', data[line]) is not None:
                                data[line] = data[line].split('=')[0] + '= ' + str(parameters[p]) + '\n'
                                break
                    with file(inpFilePath, 'w') as modified:
                        modified.writelines(data)

                    # Generate an expected results Python file with jobName
                    expectedResultsFile = os.path.join(os.getcwd(), jobName + '_expected.py')
                    shutil.copyfile(os.path.join(os.getcwd(), baseName + '_expected.py'), expectedResultsFile)

                    # Update expected results if needed
                    with file(expectedResultsFile, 'r') as original:
                        data = original.readlines()
                    for p in parameters.keys():
                        for line in range(len(data)):
                            if re.search('.{0,}' + str(p) + '.{0,}=.{0,}$', data[line]) is not None:
                                data[line] = data[line].split('=')[0] + '= ' + str(parameters[p]) + '\n'
                                break
                    with file(expectedResultsFile, 'w') as modified:
                        modified.writelines(data)

                    # Save output to a log file
                    with open(os.path.join(os.getcwd(), 'testOutput', jobName + '.log'), 'w') as f:

                        # Generate input file from python script
                        if 'pythonScriptForModel' in testCase:
                            _callAbaqus(cmd=options.abaqusCmd + ' cae noGUI=' + inpFilePath, log=f)

                        # Time tests
                        if options.time:
                            timer = _measureRunTimes()
                        else:
                            timer = None

                        # Execute the solver
                        if not options.useExistingResults:
                            self._runModel(jobName=jobName, logFileHandle=f, timer=timer)

                        # Execute process_results script load ODB and get results
                        if options.host == "localhost":
                            if not os.path.isfile(os.path.join(os.getcwd(), 'testOutput', jobName + '.odb')):
                                raise Exception("Error: Abaqus odb was not generated. Check the log file in the testOutput directory.")
                            pathForProcessResultsPy = '"' + os.path.join(ABAVERIFY_INSTALL_DIR, 'processresults.py') + '"'
                            _callAbaqus(cmd=options.abaqusCmd + ' cae noGUI=' + pathForProcessResultsPy + ' -- -- ' + jobName, log=f, timer=timer)

                        else: # Remote host
                            _callAbaqusOnRemote(cmd=options.abaqusCmd + ' cae noGUI=processresults.py -- -- ' + jobName, log=f, timer=timer)
                            try:
                                ftp = options.ssh.open_sftp()
                                ftp.chdir(options.remote_run_directory)
                                try:
                                    ftp.get(jobName + '_results.py', 'testOutput/' + jobName + '_results.py')
                                except:
                                    pass
                                if options.remote['copy_results_to_local']:
                                    for ext in options.remote['file_extensions_to_copy_to_local']:
                                        try:
                                            ftp.get(jobName + ext, 'testOutput/' + jobName + ext)
                                        except:
                                            pass
                                    for fn in options.remote['files_to_copy_to_local']:
                                        try:
                                            ftp.get(fn, 'testOutput/' + fn)
                                        except:
                                            pass
                            finally:
                                ftp.close()

                    # Run assertions
                    self._runAssertionsOnResults(jobName)

                finally:  # Make sure temporary files are removed
                    os.remove(jobName + '.inp')  # Delete temporary parametric input file
                    os.remove(jobName + '_expected.py') # Delete temporary parametric expected results file
                    if 'pythonScriptForModel' in testCase:
                        os.remove(jobName + '.py')


            # Rename the test method and return the test
            test.__name__ = jobName
            return test

        # Store input arguments
        try:
            baseName = dct['baseName']
            parameters = dct['parameters']
        except:
            print "baseName and parameters must be defined by the sub class"

        # Get the cartesian product to yield a list of all the potential test cases
        testCases = list(dict(it.izip(parameters, x)) for x in it.product(*parameters.itervalues()))

        # Loop through each test
        for i in range(0,len(testCases)):

            # Add a name to each test case
            # Generate portion of test name based on particular parameter values
            pn = '_'.join(['%s_%s' % (key, value) for (key, value) in testCases[i].items()])
            # Replace periods with commas so windows doesn't complain about file names
            pn = re.sub('[.]','',pn)
            # Add the test case name; concatenate the base name and parameter name
            testCases[i].update({'name': baseName + '_' + pn})
            testCases[i].update({'baseName': baseName})
            if 'pythonScriptForModel' in dct:
                testCases[i].update({'pythonScriptForModel': dct['pythonScriptForModel']})
            if 'expectedpy_parameters' in dct:
                exp_dict = {}
                for k, v in  dct['expectedpy_parameters'].iteritems():
                    exp_dict[k] = v[i]
                testCases[i].update(exp_dict)

            # Add test functions to the testCase class
            dct[testCases[i]['name']] = make_test_function(testCases[i])

        return type.__new__(mcs, name, bases, dct)


def runTests(relPathToUserSub, compileCodeFunc=None):
    """
    Main entry point for abaverify.

    This is the main entry point for abaverify. It should be called as follows 
    at the bottom of the script that imports abaverify: 
    
    if __name__ == "__main__":
        av.runTests(relPathToUserSub='../for/vumat')

    Parameters
    ----------
    relPathToUserSub : path
        The relative path to the user subroutine to use for the verification
        tests. Omit the file extension.
    compileCodeFunc : function, optional
        The function called to compile subroutines via abaqus make. This 
        functionality is used when compiling the subroutine once before running 
        several tests is desired. By default, when the -c option is specified, 
        a generic call to abaqus make is used, which should work most of the 
        time. If the default behavior is not satisfactory, override it with this 
        argument.

    """

    global ABAVERIFY_INSTALL_DIR
    global options


    # Directory where this file is located
    ABAVERIFY_INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))

    # Command line options
    parser = OptionParser()
    parser.add_option("-i", "--interactive", action="store_true", dest="interactive", default=False, help="Print output to the terminal; useful for debugging")
    parser.add_option("-t", "--time", action="store_true", dest="time", default=False, help="Calculates and prints the time it takes to run each test")
    parser.add_option("-c", "--precompileCode", action="store_true", dest="precompileCode", default=False, help="Compiles the subroutine before running each tests")
    parser.add_option("-e", "--useExistingBinaries", action="store_true", dest="useExistingBinaries", default=False, help="Uses existing binaries in /build")
    parser.add_option("-r", "--useExistingResults", action="store_true", dest="useExistingResults", default=False, help="Uses existing results in /testOutput; useful for debugging postprocessing")
    parser.add_option("-s", "--specifyPathToSub", action="store", dest="relPathToUserSub", default=relPathToUserSub, help="Override path to user subroutine")
    parser.add_option("-A", "--abaqusCmd", action="store", type="string", dest="abaqusCmd", default='abaqus', help="Override abaqus command; e.g. abq6141")
    parser.add_option("-k", "--keepExistingOutputFiles", action="store_true", dest="keepExistingOutputFile", default=False, help="Does not delete existing files in the /testOutput directory")
    parser.add_option("-C", "--cpus", action="store", type="int", dest="cpus", default=1, help="Specify the number of cpus to run abaqus jobs with")
    parser.add_option("-R", "--remoteHost", action="store", type="string", dest="host", default="localhost", help="Run on remote host; e.g. user@server.com[:port][/path/to/run/dir]. Default run dir is <login_dir>/abaverify_temp/")
    parser.add_option("-V", "--verbose", action="store_true", dest="verbose", default=False, help="Print information for debugging")
    (options, args) = parser.parse_args()

    # Remove custom args so they do not get sent to unittest
    # http://stackoverflow.com/questions/1842168/python-unit-test-pass-command-line-arguments-to-setup-of-unittest-testcase
    # Loop through known options
    for x in sum([h._long_opts+h._short_opts for h in parser.option_list],[]):
        # Check if the known option is an argument 
        if x in sys.argv:
            # Get the option object
            if x in [h._short_opts[0] for h in parser.option_list]:
                idx = [h._short_opts[0] for h in parser.option_list].index(x)
                option = parser.option_list[idx]
            elif  x in [h._long_opts[0] for h in parser.option_list]:
                idx = [h._long_opts[0] for h in parser.option_list].index(x)
                option = parser.option_list[idx]
            
            # If the option has additional info (e.g. -A abq6141), remove both from argv
            if option.type in ["string", "int"]:
                idx = sys.argv.index(x)
                del sys.argv[idx:idx+2]
            else:
                sys.argv.remove(x)
    if options.verbose:
        pp = pprint.PrettyPrinter(indent=4)
        print "Options:"
        pp.pprint(options.__dict__)
        print "Arguments passed to unittest:"
        pp.pprint(sys.argv)

    # Check version of script and notify the user if its out of date
    path_to_latest_ver_file = os.path.join(ABAVERIFY_INSTALL_DIR, 'latest.txt')
    lastModified = datetime.datetime.fromtimestamp(os.path.getmtime(path_to_latest_ver_file))
    if (datetime.datetime.now() - lastModified).days > 1:
        # Update version file
        try:
            import json
            import urllib2
            print "Attempting to connect to github to check if updates are available for abaverify"
            response = urllib2.urlopen('https://api.github.com/repos/nasa/abaverify/releases/latest')
            data = json.load(response)
            tag = data['tag_name']
            latest_version = tag[1:]
            with open(path_to_latest_ver_file, "w") as h:
                h.write(latest_version)
            # with open(os.path.join(ABAVERIFY_INSTALL_DIR, 'latest.txt'),'r') as f:
            #   output = f.read()
        except:
            if options.verbose:
                print "Error connecting to github to check version"
            else:
                pass

        # Load current version
        current_version = "v0.0.0"
        version_file_as_str = open(os.path.join(ABAVERIFY_INSTALL_DIR, "_version.py"), "rt").read()
        version_re = r"^__version__ = ['\"]([^'\"]*)['\"]"
        match = re.search(version_re, version_file_as_str, re.M)
        if match:
            current_version = match.group(1)

        # Compare versions
        if _versiontuple("0.3.0") > _versiontuple(current_version):
            print "  NOTICE: Version {0} of abaverify available, consider upgrading from your current version ({1})".format(latest_version, current_version)
        else:
            if options.verbose:
                print "Checked for updates; none found."

    # Remote host
    #
    # USE PARAMIKO for communication with remote host
    # Installation: 
    #   http://www.paramiko.org/installing.html
    #   http://stackoverflow.com/questions/20538685/install-paramiko-on-windows
    # Docs
    #   http://docs.paramiko.org/en/2.1/
    #   http://jessenoller.com/blog/2009/02/05/ssh-programming-with-paramiko-completely-different     <-- search google, doesn't load from url for some weird reason
    
    if options.host != "localhost":
        # Compatibility with other options
        if options.precompileCode:
            raise Exception("The -c option is not supported with -R")
        if options.useExistingBinaries:
            raise Exception("The -e option is not supported with -R")
        if options.useExistingResults:
            raise Exception("The -r option is not supported with -R")
        if options.keepExistingOutputFile:
            raise Exception("The -k option is not supported with -R")

        # Make sure running on windows and plink is available
        if platform.system() != "Windows":
            raise Exception("The -R option is only supported for Windows")
        try:
            import paramiko
            ssh = paramiko.SSHClient()
        except:
            raise Exception("Failed to load paramiko. The -R option requires Paramiko. Please make sure that paramiko is installed and configured")

        if options.verbose: print "Using remote host"

        # Load remote options
        try:
            import abaverify_remote_options as aro
            user_defined_attributes = [attr for attr in dir(aro) if '__' not in attr]
            remote_opts = {attr: getattr(aro, attr) for attr in user_defined_attributes}
        except:
            # Create dictionary to populate
            remote_opts = dict()

        # Set deaults
        if 'remote_run_directory' not in remote_opts:
            remote_opts['remote_run_directory'] = 'abaverify_temp'
        if 'local_files_to_copy_to_remote' not in remote_opts:
            remote_opts['local_files_to_copy_to_remote'] = []
        if 'source_file_regexp' not in remote_opts:
            remote_opts['source_file_regexp'] = r'.*\.for$'
        if 'copy_results_to_local' not in remote_opts:
            remote_opts['copy_results_to_local'] = False
        if 'file_extensions_to_copy_to_local' not in remote_opts:
            remote_opts['file_extensions_to_copy_to_local'] = ['.dat', '.inp', '.msg', '.odb', '.sta']
        if 'files_to_copy_to_local' not in remote_opts:
            remote_opts['files_to_copy_to_local'] = list()
        if 'environment_file_name' not in remote_opts:
            remote_opts['environment_file_name'] = 'abaqus_v6_remote.env'
        

        # Check for optional path to a run directory
        match = re.search(r'^([A-Za-z0-9\-\.]+)@([A-Za-z0-9\-\.]+):?([0-9]+)?(.*)$', options.host)
        if match:
            userName = match.group(1)
            fqdn = match.group(2)
            port = match.group(3)
            runDir = match.group(4)
        else:
            raise ValueError("Unable to understand the specified host " + options.host + "; please use proper formatting.")
        # Set default run directory
        if runDir:
            remote_opts['remote_run_directory'] = runDir
        else:
            runDir = remote_opts['remote_run_directory']
        if not port:
            port = 22
        setattr(options, 'remote', remote_opts)
        setattr(options, 'remote_run_directory', remote_opts['remote_run_directory'])

        if options.verbose:
            print "userName: " + userName
            print "fqdn: " + fqdn
            print "port: " + str(port)

        if options.verbose:
            print "remote_opts: "
            pp.pprint(remote_opts)

        # Gather required information
        pw = getpass.getpass('Enter the password for ' + userName + "@" + fqdn + ': ')

        # Connect to the remote host
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(fqdn, port=port, username=userName, password=pw)
        setattr(options, 'ssh', ssh)

        # Clear the run directory
        stdin, stdout, stderr = ssh.exec_command("ls " + runDir)
        err = stderr.readlines()
        if len(err):
            if "No such file or directory" in err[0]:
                stdin, stdout, stderr = ssh.exec_command("mkdir " + runDir)
            else:
                ssh.close()
                raise Exception("Unknown error on remote when searching for run directory.")
        stdin, stdout, stderr = ssh.exec_command("rm -rf " + runDir + "/*")
        if options.verbose: print "Run directory cleaned"

        # Transfer files to the run directory
        try:
            ftp = ssh.open_sftp()
            ftp.chdir(runDir)

            # Fortran source files
            source_file_dir = os.path.dirname(options.relPathToUserSub)
            pattern = re.compile(remote_opts['source_file_regexp'])
            sourceFiles = [os.path.join(os.path.dirname(options.relPathToUserSub), f) for f in os.listdir(source_file_dir) if pattern.match(f)]
            for sourceFile in sourceFiles:
                if options.verbose: print "Copying: " + os.path.abspath(sourceFile)
                ftp.put(sourceFile, os.path.basename(sourceFile))
                if options.verbose: print "... file copied."

            # Make sure there's a symbolic link on the remote so that abaqus doesn't complain about .f and .for
            subroutine_file_name = os.path.basename(options.relPathToUserSub)
            if options.verbose: print "Creating a symbolic link to the source file"
            ssh.exec_command('cd ' + options.remote_run_directory + '; ' + 'ln -s ' + subroutine_file_name + '.for ' + subroutine_file_name + '.f')
            if options.verbose: print "... symbolic link created."

            # Environment file (expects naming convention: abaqus_v6_remote.env)
            env_file_name = options.remote['environment_file_name']
            if os.path.isfile(os.path.join(os.getcwd(), env_file_name)):
                if options.verbose: print "Copying: " + os.path.abspath(env_file_name)
                ftp.put(env_file_name, 'abaqus_v6.env')

            # abaverify_remote_options
            if 'local_files_to_copy_to_remote' in options.remote:
                for f in options.remote['local_files_to_copy_to_remote']:
                    if options.verbose: print "Copying: " + os.path.abspath(f)
                    ftp.put(f, os.path.basename(f))

            # abaverify processresults.py
            pathForProcessResultsPy = os.path.join(ABAVERIFY_INSTALL_DIR, 'processresults.py')
            if options.verbose: print "Copying: " + pathForProcessResultsPy
            ftp.put(pathForProcessResultsPy, 'processresults.py')

        finally:
            ftp.close()

        # Make sure testOutput exists and that its empty.
        testOutputPath = os.path.join(os.getcwd(), 'testOutput')
        if not os.path.isdir(testOutputPath):
            os.makedirs(testOutputPath)
        for f in os.listdir(testOutputPath):
            os.remove(os.path.join(os.getcwd(), 'testOutput', f))


    else: # Run on local host

        # Remove rpy files
        testPath = os.getcwd()
        pattern = re.compile(r'^abaqus\.rpy(\.)*([0-9])*$')
        for f in os.listdir(testPath):
            if pattern.match(f):
                os.remove(os.path.join(os.getcwd(), f))

        # Remove old binaries
        if not options.useExistingBinaries:
            if os.path.isdir(os.path.join(os.pardir, 'build')):
                for f in os.listdir(os.path.join(os.pardir, 'build')):
                    os.remove(os.path.join(os.pardir, 'build', f))

        # If testOutput doesn't exist, create it
        testOutputPath = os.path.join(os.getcwd(), 'testOutput')
        if not os.path.isdir(testOutputPath) and options.useExistingResults:
            raise Exception("There must be results in the testOutput directory to use the --useExistingResults (-r) option")
        if not os.path.isdir(testOutputPath):
            os.makedirs(testOutputPath)

        # Remove old job files
        if not options.useExistingResults:
            if not options.keepExistingOutputFile:
                testOutputPath = os.path.join(os.getcwd(), 'testOutput')
                pattern = re.compile('.*\.env$')
                for f in os.listdir(testOutputPath):
                    if not pattern.match(f):
                        os.remove(os.path.join(os.getcwd(), 'testOutput', f))
            else:
                # Check for files with the same name to avoid overwriting
                # This is a bit of pain
                # Process:
                # 1. Check if args any are classes in the calling file that are specified as arguments
                classesInCallingFile = {}
                # Get the calling file
                frame = inspect.stack()[1]
                # Get the classes in the calling file
                for name, obj in inspect.getmembers(inspect.getmodule(frame[0])):
                    if inspect.isclass(obj) and issubclass(obj, TestCase):
                        classesInCallingFile[obj.__name__] = obj
                calledClasses = list(set(sys.argv[1:]).intersection(classesInCallingFile.keys()))

                # 2. Build a list of test_ methods that will be called
                calledMethods = []

                # 3. Get test_ methods from the class(es) that are called
                for c in calledClasses:
                    for name, obj in inspect.getmembers(classesInCallingFile[c], predicate=inspect.ismethod):
                        if 'test_' in name:
                            calledMethods.append(name)

                # 4. Get test_ methods list explicity in the arguments
                for arg in sys.argv[1:]:
                    if len(arg.split('.')) == 2:
                        testName = arg.split('.')[1]
                        if 'test' in testName:
                            calledMethods.append(testName)
                
                # Now we have a list of the test methods that will be called
                # print calledMethods

                # Get a list of unique file names begining with 'test' in testOutput directory (w/o file extensions)
                uniquefileNames = list(set([f.split('.')[0] for f in os.listdir(testOutputPath) if 'test_' in f]))

                # Check if any files exist in testOutput with these test names
                testsToBeOverwritten = list(set(uniquefileNames).intersection(calledMethods))
                if len(testsToBeOverwritten) > 0:
                    raise Exception("Cannot overwrite the following tests {0}".format(str(testsToBeOverwritten)))


            # Try to pre-compile the code
            if not options.useExistingBinaries:
                wd = os.getcwd()
                if options.precompileCode:
                    try:
                        # If an external function is provided use it; otherwise use builtin capability
                        if compileCodeFunc:
                            compileCodeFunc()
                        else:
                            _compileCode(os.path.basename(options.relPathToUserSub))
                    except:
                        print "ERROR: abaqus make failed.", sys.exc_info()[0]
                        raise Exception("Error compiling with abaqus make. Look for 'compile.log' in the testOutput directory. Or try running 'abaqus make library=CompDam_DGD' from the /for directory to debug.")
                        os.chdir(wd)

            # Make sure
            # 1) environment file exists
            # 2) it has usub_lib_dir
            # 3) usub_lib_dir is the location where the binaries reside
            # 4) a copy is in testOutput
            if os.path.isfile(os.path.join(os.getcwd(), 'abaqus_v6.env')):
                # Make sure it has usub_lib_dir
                if options.precompileCode:
                    with open(os.path.join(os.getcwd(), 'abaqus_v6.env'), 'r+') as envFile:
                        foundusub = False
                        pattern_usub = re.compile('^usub_lib_dir.*')
                        for line in envFile:
                            if pattern_usub.match(line):
                                print "Found usub_lib_dir"
                                pathInEnvFile = re.findall('= "(.*)"$', line).pop()
                                if pathInEnvFile:
                                    if pathInEnvFile == '/'.join(os.path.abspath(os.path.join(os.pardir, 'build')).split('\\')): # Note that this nonsense is because abaqus wants '/' as os.sep even on windows
                                        foundusub = True
                                        break
                                    else:
                                        raise Exception("ERROR: a usub_lib_dir is specified in the environment file that is different from the build location.")
                                else:
                                    raise Exception("ERROR: logic to parse the environment file looking for usub_lib_dir failed.")

                    # Add usub_lib_dir if it was not found
                    if not foundusub:
                        print "Adding usub_lib_dir to environment file."
                        with open(os.path.join(os.getcwd(), 'abaqus_v6.env'), 'a') as envFile:
                            pathWithForwardSlashes = '/'.join(os.path.abspath(os.path.join(os.pardir, 'build')).split('\\'))
                            print pathWithForwardSlashes
                            envFile.write('\nimport os\nusub_lib_dir = "' + pathWithForwardSlashes + '"\ndel os\n')

                # Copy to /test/testOutput
                shutil.copyfile(os.path.join(os.getcwd(), 'abaqus_v6.env'), os.path.join(os.getcwd(), 'testOutput', 'abaqus_v6.env'))
            else:
                raise Exception("Missing environment file. Please configure a local abaqus environement file. See getting started in readme.")


    try:
        unittest.main(verbosity=2)
    finally:
        if options.host != "localhost":
            ssh.close()
