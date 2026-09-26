"""
This is the main API for the abaverify package.
"""
import unittest
from optparse import OptionParser
import sys
import platform
import os
import filecmp
import ast
import re
import shutil
import subprocess
import contextlib
import itertools as it
import time
import inspect
import datetime
import pprint
from threading import Timer

#
# Local
#


class _measureRunTimes:
    """
    Measures run times during unit tests

    This is a helper class for recording the run times of abaqus jobs based on
    the abaqus log file. The duration for linking, packaging, and the solver are
    printed to the log file.

    Attributes
    ----------
    Compile_start : :obj:`time`
        Time at which the compiler started
    Compile_end : :obj:`time`
        Time at which the compiler ended 
    packager_start : :obj:`time`
        Time at which the packager started 
    packager_end : :obj:`time`
        Time at which the packager ended 
    solver_start : :obj:`time`
        Time at which the solver started
    solver_end : :obj:`time`
        Time at which the solver ended

    """

    def __init__(self, precompile=False):
        self.Compile_start = None
        self.Compile_end = None
        self.packager_start = None
        self.packager_end = None
        self.solver_start = None
        self.solver_end = None
        self.precompile=precompile

    def processLine(self, line):
        """
        This method should be called on the output from abaqus and is used to
        identify the start and end times for the compiler, packager, and solver.

        """

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
            prefix = '\n' if self.precompile else ''
            sys.stderr.write(prefix+"Packager run time: {:.2f} s\n".format(self.package_time))

        elif re.match(r'Begin Abaqus/Explicit Analysis', line):
            self.solver_start = time.time()
        elif re.match(r'End Abaqus/Explicit Analysis', line) or re.match(r'.*Abaqus/Explicit Analysis exited with an error.*', line):
            self.solver_end = time.time()
            self.solver_time = self.solver_end - self.solver_start
            sys.stderr.write("Solver run time: {:.2f} s\n".format(self.solver_time))


def _versiontuple(v):
    """
    Converts a version string to a tuple.

    Parameters
    ----------
    v : :obj:`str`
        Version number as a string. For example: '1.1.1'

    Returns
    -------
    tuple
        Three element tuple with the version number. For example: (1, 1, 1)

    """

    return tuple(map(int, (v.split("."))))


def _terminate_job(jobName, abaqusCmd, logFileHandle):
    """
    Terminates an abaqus job

    Parameters
    ----------
    jobName : :obj:`str`
        The name of the abaqus input deck (without the .inp file extension).
    logFileHandle : :obj:`file`
        A file handle to the file used for storing output.
    """

    logFileHandle.write("\n\n\nABAVERIFY INTERUPT: Job expiration time reached; terminating the analysis.\n\n\n")
    subprocess.call([abaqusCmd, 'job=' + jobName, 'terminate'], shell=True)


def _callAbaqus(cmd, log, timer=None, shell=True):
    """
    Calls abaqus and streams the output to the log file.

    Parameters
    ----------
    cmd : :obj:`str`
        Command to call abaqus. For example: 'abq6141'
    log : filehandle
        Filehandle for the log file.
    timer : :obj:`_measureRunTimes`, optional
        _measureRunTimes instance.
    shell : bool, optional
        Passed directly to subprocess.Popen.

    """

    if options.verbose:
        print("Calling abaqus with command: ", cmd)

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, shell=shell)

    # Parse output lines & save to a log file
    for line in _outputStreamer(p):

        # Time tests
        if options.time:
            if timer is not None:
                timer.processLine(line)

        # Log data
        log.write(line + "\n")
        if options.interactive:
            print(line)


def _outputStreamer(proc, stream='stdout'):
    """
    Parses the streaming process output from subprocess.popen into strings for each line.

    From: http://blog.thelinuxkid.com/2013/06/get-python-subprocess-output-without.html
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


def _compileCode(libPath):
    """
    Pre-compiles a subroutine using abaqus make.

    This function is called when the user specifies that the subroutine should
    be pre-compiled into a shared library object, but no function is provide to
    compile the code. This is a default procedure for compiling subroutines with
    abaqus make that is intended to be relatively general.  

    Parameters
    ----------
    libPath : :obj:`str`
        Path to the subroutine fortran file.

    """
    subroutine_directory = os.path.dirname(libPath)
    subroutine_name = os.path.splitext(os.path.basename(libPath))[0]
    starting_directory = os.getcwd()
    if options.verbose:
        print('Running builtin _compileCode()')
        print('subroutine_directory: ', subroutine_directory)
        print('subroutine_name: ', subroutine_name)

    # Put a copy of the environment file in the /for directory
    src = os.path.join(os.getcwd(), 'abaqus_v6.env')
    dst = os.path.join(subroutine_directory, 'abaqus_v6.env')
    if not os.path.isfile(dst):
        shutil.copyfile(src, dst)
    elif not filecmp.cmp(src, dst):
        shutil.copyfile(src, dst)

    # Change directory to /for
    os.chdir(subroutine_directory)

    # Run abaqus make
    if (platform.system() == 'Linux'):
        shell = False
    else:
        shell = True
    try:
        f = open(os.path.join(options.outputDirectory, 'compile.log'), 'a')
        _callAbaqus(cmd=[options.abaqusCmdCompile, 'make', 'library=' + subroutine_name], log=f, shell=shell)
    finally:
        f.close()

    # # Remove env file from /for
    # os.remove(os.path.join(os.getcwd(), 'abaqus_v6.env'))

    # Make sure build directory exists
    if not os.path.isdir(os.path.join(os.pardir, 'build')):
        os.makedirs(os.path.join(os.pardir, 'build'))

    # Copy binaries into /build
    numBinariesFound = 0
    pattern = re.compile('.*(\.dll|\.obj|\.so|\.o)$')
    for f in os.listdir(os.getcwd()):
        if pattern.match(f):
            numBinariesFound += 1
            shutil.copyfile(os.path.join(os.getcwd(), f), os.path.join(os.pardir, 'build', f))
            os.remove(os.path.join(os.getcwd(), f))

    if numBinariesFound < 4:
        raise Exception("ERROR: Abaqus make failed")

    # Change directory to back to starting directory
    os.chdir(starting_directory)


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
        patterns = [re.compile(r'.*abaqus.*\.rpy.*'), re.compile(r'.*abaqus.*\.rec.*'), re.compile(r'.*pyc')]
        try:
            [os.remove(f) for f in files if any(regex.match(f) for regex in patterns)]
        except:
            pass

    def runTest(self, jobName, func=None, arguments=None, substitutions=[], expected_substitutions=[],
                inpName=None, expectedpyName=None, datacheck=False, pythonScriptForModel=False,
                pythonScriptArguments=[]):
        """
        Run a verification test.

        This method should be called to run a verification test. A verification
        test includes running an abaqus analysis, post-processing the results,
        and running assertions on the results. This method includes logic that 
        performs each of these three steps.

        Parameters
        ----------
        jobName : :obj:`str`
            The name of the abaqus input deck (without the .inp file extension). 
            Abaverify assumes that there is a corresponding file named 
            <jobName>_expected.py that defines the expected results.
        func : function
            A function to evaluate external assertions. The function is passed
            self and jobName as arguments.
        arguments : list
            A list of arguments to pass to the func
        substitutions : nested list of re.sub() arguments
            Provide a list of substitutions to be applied to the input deck
            prior to running the analysis.
        expected_substitutions : nested list of re.sub() arguments
            Provide a list of substitutions to be applied to the expected.py
            file prior to running the assertions.
        inpName : :obj:`str`
            Optional name of input deck to use if different from jobName.
            Intended to be used with substitutions argument.
        expectedpyName : :obj:`str`
            Optional name of expected.py file. Assumes there is no file
            in the working directory named <jobName>_expected.py.
        datacheck : bool
            Run a data check instead of an analysis job.
        pythonScriptForModel : bool
            Indicates that the model is defined in a python script instead of
            an abaqus input deck.
        pythonScriptArguments : list
            List of arguments to pass to the python script that defines the model.
            Note inpName is used to define the script name and jobName is should be
            consistent with the python script.
        """

        if options.verbose or options.interactive:
            print("")

        if pythonScriptForModel and (substitutions or expected_substitutions):
            raise ValueError('Substitutions are not supported for pythonScriptForModel=True')

        generated_expected_py = False
        try:
            # Save output to a log file
            log_file_path = os.path.join(options.outputDirectory, jobName + '.log')
            if options.verbose:
                print("Logging to: ", log_file_path)
            with open(log_file_path, 'w') as f:

                if not inpName:
                    inpName = jobName
                if inpName == jobName:
                    if len(substitutions):
                        raise ValueError('To use substitutions requires inpName != None and inpName != jobName')
                    if len(expected_substitutions) == 0: 
                        if expectedpyName:
                            shutil.copyfile(expectedpyName + '_expected.py', jobName + '_expected.py')
                            generated_expected_py = True
                    else:
                        raise ValueError('To use expected_substitutions requires inpName != None and inpName != jobName')
                    
                elif inpName != jobName:
                    if len(substitutions):
                        apply_substitutions(inpName+'.inp', jobName+'.inp', substitutions)
                    else:
                        if not pythonScriptForModel:
                            shutil.copyfile(inpName + '.inp', jobName + '.inp')
                    # if os.path.isfile(jobName + '_expected.py'):
                    #     raise Exception('File {} already exists'.format(jobName + '_expected.py'))
                    if len(expected_substitutions) == 0:
                        if expectedpyName:
                            if options.verbose: print('Copy {} to {}'.format(expectedpyName + '_expected.py', jobName + '_expected.py'))
                            shutil.copyfile(expectedpyName + '_expected.py', jobName + '_expected.py')
                            generated_expected_py = True
                        elif not os.path.isfile(jobName + '_expected.py'):
                            if options.verbose: print('Copy {} to {}'.format(inpName + '_expected.py', jobName + '_expected.py'))
                            shutil.copyfile(inpName + '_expected.py', jobName + '_expected.py')
                            generated_expected_py = True
                        else:
                            if options.verbose: print('Using existing expected.py file: {}'.format(jobName + '_expected.py'))
                    else:
                        if expectedpyName:
                            apply_substitutions(expectedpyName + '_expected.py', jobName+'_expected.py', expected_substitutions)
                        else:
                            apply_substitutions(inpName+'_expected.py', jobName+'_expected.py', expected_substitutions)
                        generated_expected_py = True
                
                # if inpName:
                #     if inpName != jobName and not expectedpyName:
                #         if not os.path.isfile(jobName + '_expected.py'):
                #             generated_expected_py = True
                #             shutil.copyfile(inpName + '_expected.py', jobName + '_expected.py')
                #             expectedpyName = jobName + '_expected.py'
                # else:
                #     inpName = jobName
                # if not expectedpyName:
                #     expectedpyName = inpName + '_expected.py'


                # if len(substitutions):
                #     apply_substitutions(inpName+'.inp', jobName+'.inp', substitutions)
                # elif inpName != jobName:
                #     shutil.copyfile(inpName + '.inp', jobName + '.inp')

                # if len(expected_substitutions):
                #     apply_substitutions(inpName+'_expected.py', jobName+'_expected.py', expected_substitutions)

                # Generate input file from python script
                if pythonScriptForModel:
                    if hasattr(self, 'model_builder_path'):
                        script_file_path = self.model_builder_path
                    else:
                        script_file_path = os.path.join(os.getcwd(), inpName + '.py')
                    arguments_str = ' -- -- ' + ' '.join(pythonScriptArguments)
                    _callAbaqus(cmd=options.abaqusCmdCae + ' cae noGUI=' + script_file_path + arguments_str, log=f)

                # Time tests
                if options.time:
                    timer = _measureRunTimes(precompile=options.precompileCode)
                else:
                    timer = None

                # Check for job-specific expiration time
                if os.path.isfile(jobName + '_expected.py'):
                    para = __import__(jobName + '_expected').parameters
                    if "expiration" in para:
                        options.expiration = para["expiration"]
                    if options.expiration != None:
                        if options.expiration < 0:
                            options.expiration = None
                else:
                    print("Warning: No expected.py file found for job {}. Job expiration time will not be applied.".format(jobName))

                if options.genPes:
                    datacheck = True

                # Execute the solver
                if not options.useExistingResults:
                    self._runModel(jobName=jobName, logFileHandle=f, timer=timer, expiration=options.expiration, datacheck=datacheck)

                # Execute process_results script load ODB and get results
                process_results_args = " ".join([jobName, options.outputDirectory, str(options.doNotSave)])
                if options.verbose:
                    print("Running post processing script ...")
                if datacheck:
                    self._process_datacheck(jobName, options.outputDirectory)
                else:
                    if not os.path.isfile(os.path.join(options.outputDirectory, jobName + '.odb')):
                        raise Exception("Error: Abaqus odb was not generated. Check the log file in the options.outputDirectory directory.")
                    pathForProcessResultsPy = '"' + os.path.join(ABAVERIFY_INSTALL_DIR, 'processresults.py') + '"'
                    _callAbaqus(cmd=options.abaqusCmdCae + ' cae noGUI=' + pathForProcessResultsPy + ' -- -- ' + process_results_args, log=f, timer=timer)

        except Exception as e:
            print("Exception occurred while running the test:")
            print(e)
        finally:  # Make sure temporary files are removed
            if inpName != jobName:
                os.remove(os.path.join(os.getcwd(), jobName + '.inp'))  # Delete temporary parametric input file
                if generated_expected_py: os.remove(os.path.join(os.getcwd(), jobName + '_expected.py'))  # Delete temporary parametric expected results file

        if options.genPes:
            pes_dir = os.path.join(os.getcwd(), 'pes')
            if not os.path.isdir(pes_dir): os.mkdir(pes_dir)
            shutil.copyfile(os.path.join(options.outputDirectory, jobName + '.pes'), os.path.join(pes_dir, jobName + '.pes'))
            return

        # Run assertions
        self._runAssertionsOnResults(jobName, func, arguments)

    def _runModel(self, jobName, logFileHandle, timer, expiration=None, datacheck=False):
        """
        Submits the abaqus job.

        This method handles preparing and submitting the abaqus job. The abaqus
        command is built with the options specified at run time. The job files
        are copied to a directory called options.outputDirectory. 

        Parameters
        ----------
        jobName : :obj:`str`
            The name of the abaqus input deck (without the .inp file extension).
        logFileHandle : :obj:`file`
            A file handle to the file used for storing output.
        timer : :obj:`_measureRunTimes`
            An instance of `_measureRunTimes` to use for recording run times.
        expiration : int
            Time in seconds after which the test should 'expire' i.e. be killed.
        datacheck : bool
            Run a data check instead of an analysis job.
        """

        if not (options.precompileCode or options.useExistingBinaries):
            # Path to user subroutine
            userSubPath = os.path.abspath(options.relPathToUserSub)
            if options.verbose:
                print("Using subroutine: " + userSubPath)

        # Copy input deck
        from_ = os.path.join(os.getcwd(), jobName + '.inp')
        to_ = os.path.join(options.outputDirectory, jobName + '.inp')
        if options.verbose:
            print("Copying from {} to {}".format(from_, to_))
        shutil.copyfile(from_, to_)

        # build abaqus cmd
        cmd = options.abaqusCmdJob + ' job=' + jobName
        if not (options.precompileCode or options.useExistingBinaries) and options.relPathToUserSub:
            cmd += ' user="' + userSubPath + '"'
        if options.cpus > 1:
            cmd += ' cpus=' + str(options.cpus)
        if options.double:
            cmd += ' double=both'
        if datacheck:
            cmd += ' datacheck'
        cmd += ' interactive verbose=2'
        if options.verbose:
            print("Abaqus command: " + cmd)

        # Run the test from the options.outputDirectory directory
        starting_directory = os.getcwd()
        try:
            os.chdir(os.path.join(options.outputDirectory))
            if options.verbose:
                print('Running abaqus job from: {}'.format(os.getcwd()))
            if expiration:
                exp = Timer(expiration, _terminate_job, [jobName, options.abaqusCmdJob, logFileHandle])
                exp.start()
            _callAbaqus(cmd=cmd, log=logFileHandle, timer=timer)
            if expiration:
                exp.cancel()
        finally:
            os.chdir(starting_directory)
    
    def _process_datacheck(self, jobName, outputDirectory):
        """
        Parse outputs from datacheck and prepare the <jobName>_results.py file.

        Parameters
        ----------
        jobName : :obj:`str`
            The name of the abaqus input deck (without the .inp file extension).
        outputDirectory : :obj:`str`
            Location of the job files.
        """
        para = __import__(jobName + '_expected').parameters
        with open(jobName + '_expected.py', 'r') as file:
            results_py = file.readlines()
        with open(os.path.join(outputDirectory, jobName+'.sta'), 'r') as file:
            sta_content = file.read()
        with open(os.path.join(outputDirectory, jobName+'.log'), 'r') as file:
            log_content = file.read()
        for iii, r in enumerate(para['results']):
            if 'file' in r:
                
                if r['file'] == 'sta':
                    if r['identifier'] == "Total mass (unscaled)":
                        # Use regular expressions to find the values
                        match = re.search(r"Total mass \(unscaled\) in model = ([\d.Ee+-]+)", sta_content)
                    elif r['identifier'] == "Initial time increment":
                        match = re.search(r"Initial time increment = ([\d.Ee+-]+)", sta_content)
                    else:
                        continue

                    # Find location to add computed value
                    index = r['index']
                    potent_line_num = [(i, line) for i, line in enumerate(results_py) if f'"index": {index}' in line]
                    if len(potent_line_num) == 1:
                        line_num, line = potent_line_num[0]
                        computedValue = match.group(1) if match else None
                        num_leading_spaces = len(line) - len(line.lstrip(' '))
                        new_line = ' '*num_leading_spaces + f'"computedValue": {computedValue},\n' 
                        results_py.insert(line_num + 1, new_line)
                    else:
                        self.fail(f"Failed parsing {r['file']} file.")
        
        # Reformat in the format required by _runAssertionsOnResults()
        match = re.search(r'"results":\s*(\[.*\])', ''.join(results_py), re.DOTALL)
        if not match:
            raise self.fail(f"Error parsing {r['file']} file")
        results_py = match.group(1)
        results_py = [line[4:] for line in results_py.split('\n') if line.startswith('    ')]
        results_py.insert(0, "results = [")
        results_py.append("]")
        # Write to file
        fileName = os.path.join(outputDirectory, jobName + '_results.py')
        with open(fileName, 'w') as f:
            f.write('\n'.join(results_py))

    def _runAssertionsOnResults(self, jobName, func, arguments):
        """
        Runs assertions on each result specified in the <jobName>_results.py file.

        Applies the appropriate unittest assertion based on the data in the 
        <jobName>_results.py file. The <jobName>_results.py file is generated by 
        the processresults.py module.

        Parameters
        ----------
        jobName : :obj:`str`
            The name of the abaqus input deck (without the .inp file extension).
        func : function
            A function to evaluate external assertions. The function is passed
            self and jobName as arguments.
        arguments : list
            A list of arguments to pass to the func

        """

        outputFileName = jobName + '_results.py'
        outputFileDir = os.path.join(os.getcwd(), options.outputDirectory)
        outputFilePath = os.path.join(outputFileDir, outputFileName)
        if func:
            func(self, jobName, arguments)
        else:
            if os.path.isfile(outputFilePath):
                sys.path.insert(0, outputFileDir)
                results = __import__(outputFileName[:-3]).results

                for r in results:

                    # Loop through values if there are more than one
                    if hasattr(r['computedValue'], '__iter__'):
                        self.assertEqual(len(r['computedValue']), len(r['referenceValue']),
                                         "Computed and reference results must have the same length")
                        for i in range(0, len(r['computedValue'])):
                            computed_val = r['computedValue'][i]
                            reference_val = r['referenceValue'][i]

                            if isinstance(reference_val, tuple):
                                tolerance_for_result_obj = r['tolerance']
                                # when there exists a tuple as a reference val then all other results and deltas
                                # should also be tuples
                                self.assertEqual(len(computed_val), len(reference_val),
                                                 "Specified reference value should be same length as Computed value")
                                # tolerance may be specified as a single tuple or a list of tuples. If its the latter
                                # then index and return the tuple
                                if isinstance(tolerance_for_result_obj, tuple):
                                    tolerance = tolerance_for_result_obj
                                else:
                                    tolerance = tolerance_for_result_obj[i]
                                self.assertEqual(len(reference_val), len(tolerance),
                                                 "Specified tolerance tople should be the same length as the ref")
                                # loop through entries in tuple (x and y)
                                for (cv, rv, tolerance) in zip(computed_val, reference_val, tolerance):
                                    self.assertAlmostEqual(cv, rv, delta=tolerance)
                            else:
                                tolerance_for_result_obj = r['tolerance'][i]
                                self.assertAlmostEqual(computed_val, reference_val, delta=tolerance_for_result_obj)

                    else:
                        if "tolerance" in r:
                            self.assertAlmostEqual(r['computedValue'], r['referenceValue'], delta=r['tolerance'])
                        elif "referenceValue" in r:
                            self.assertEqual(r['computedValue'], r['referenceValue'])
                        else:
                            # No data to compare with, so pass the test
                            pass
            else:
                self.fail('No results file provided by process_results.py. Looking for "%s"' % outputFilePath)


class ParametricMetaClass(type):
    """
    Provides functionality for parametric testing.

    Classes that inherit this class may have models defined as input decks or python 
    scripts.

    Expects that the inheriting class defines:

    __metaclass__ = av.ParametricMetaClass

    baseName: The name of the input deck to use as a template (without the .inp)

    parameters: a dictionary with each parameter to vary. For example: 
    {'alpha': range(-40,10,10), 'beta': range(60,210,30)}

    [optional] expectedpy_parameters: a dictionary with the result for each 
    parameter value

    [optional] expectedpy_name: Name of alternate expected.py file. 

    [optional] dependent_parameters: a nested dictionary with parameters that 
    dependend on the particular value of other parameters in each test. For example
    to prescribe delta based on alpha values:
    {'alpha': { -40: {'delta': 1.0}, -30: {'delta': 1.5}, ... }
    To prescribe the same value to a dependent parameter for all cases:
    {'baseName': {'<name of input deck>': {'mass_scaling_factor': 1.0}}, }

    [optional] inp_sub: argument list for re.sub() that is applied to each
    line in the input deck (does not propagate to include files currently)

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
            inp_sub = testCase['inp_sub'] if 'inp_sub' in testCase.keys() else []
            parameters = {k: v for k, v in items if k not in ('baseName', 'name', 'inp_sub', 'expectedpy_parameters')}
            if 'expectedpy_parameters' in testCase:
                expectedpy_parameters = testCase['expectedpy_parameters']
            else:
                expectedpy_parameters = {}
            if 'expectedpy_name' in testCase:
                expectedpy_name = testCase['expectedpy_name'] + '.py'
            else:
                expectedpy_name = baseName + '_expected.py'

            def test(self):

                if options.verbose or options.interactive:
                    print("")
                    print("parameters: ", parameters)

                try:
                    # Create the input deck
                    # Copy the template input file
                    if 'pythonScriptForModel' in testCase:
                        inpFilePath = os.path.join(os.getcwd(), jobName + '.py')
                        shutil.copyfile(os.path.join(os.getcwd(), baseName + '.py'), inpFilePath)
                    else:
                        inpFilePath = os.path.join(os.getcwd(), jobName + '.inp')
                        shutil.copyfile(os.path.join(os.getcwd(), baseName + '.inp'), inpFilePath)

                    # Read input deck
                    with open(inpFilePath, 'r') as original:
                        data = original.readlines()
                    # Apply inp_sub
                    if len(inp_sub):
                        if not (isinstance(inp_sub[0], list) or isinstance(inp_sub[0], tuple)):
                            inp_sub_nested_list = [inp_sub, ]
                        else:
                            inp_sub_nested_list = inp_sub
                        for line_num in range(len(data)):
                            for inp_sub_ in inp_sub_nested_list:
                                updated_line = re.sub(*inp_sub_, data[line_num])
                                if updated_line != data[line_num]:
                                    data[line_num] = updated_line
                                    if options.verbose:
                                        print('Updated input deck line {} to: {}'.format(line_num, updated_line.strip()))
                    # Update all of the relevant *Parameter terms in the Abaqus input deck
                    if options.verbose:
                        print('Attempting to update input deck {} with {}'.format(inpFilePath, parameters))
                    for p in parameters.keys():
                        updated_parameter = False
                        updated_parameter_nested = False
                        for line_num in range(len(data)):
                            # Handle include files
                            if data[line_num].lower().startswith('*include'):
                                incl_file_name = os.path.join(options.outputDirectory, data[line_num].split('=')[1].strip())
                                with open(incl_file_name, 'r') as incl_file:
                                    incl_file_data = incl_file.readlines()
                                for iline_num in range(len(incl_file_data)):
                                    if incl_file_data[iline_num].lower().startswith('*include'):
                                        raise Exception('Nested include files are not supported')
                                    if re.search('.{0,}' + str(p) + '.{0,}=.{0,}$', incl_file_data[iline_num]) is not None:
                                        incl_file_data[iline_num] = incl_file_data[iline_num].split('=')[0] + '= ' + str(parameters[p]) + '\n'
                                        updated_parameter_nested = True
                                        break
                                if updated_parameter_nested:
                                    with open(incl_file_name, 'w') as modified:
                                        modified.writelines(incl_file_data)
                                        if options.verbose:
                                            print("Updated {} with {} = {}".format(incl_file_name, p, parameters[p]))
                            elif re.search('.{0,}' + str(p) + '.{0,}=.{0,}$', data[line_num]) is not None:
                                data[line_num] = data[line_num].split('=')[0] + '= ' + str(parameters[p]) + '\n'
                                updated_parameter = True
                                break
                            if updated_parameter or updated_parameter_nested: break
                        if updated_parameter:
                            if options.verbose:
                                print('Updated parameter {} = {} '.format(p, parameters[p]))
                    with open(inpFilePath, 'w') as modified:
                        modified.writelines(data)

                    # Generate an expected results Python file with jobName
                    if options.verbose:
                        print(f'Using {expectedpy_name}')
                    expectedResultsFile = os.path.join(os.getcwd(), jobName + '_expected.py')
                    shutil.copyfile(os.path.join(os.getcwd(), expectedpy_name), expectedResultsFile)

                    # Update expected results if needed
                    if len(expectedpy_parameters):
                        if options.verbose:
                            print('Attempting to update {} with {}'.format(expectedResultsFile, expectedpy_parameters))
                        with open(expectedResultsFile, 'r') as original:
                            data = original.readlines()
                        for p in expectedpy_parameters.keys():
                            updated_parameter = False
                            for line in range(len(data)):
                                if re.search('.{0,}' + str(p) + '.{0,}=.{0,}$', data[line]) is not None:
                                    data[line] = data[line].split('=')[0] + '= ' + str(expectedpy_parameters[p]) + '\n'
                                    updated_parameter = True
                                    break
                            if updated_parameter:
                                if options.verbose:
                                    print('Updated parameter {} = {} '.format(p, expectedpy_parameters[p]))
                        with open(expectedResultsFile, 'w') as modified:
                            modified.writelines(data)

                    # Save output to a log file
                    with open(os.path.join(os.getcwd(), options.outputDirectory, jobName + '.log'), 'w') as f:

                        # Generate input file from python script
                        if 'pythonScriptForModel' in testCase:
                            _callAbaqus(cmd=options.abaqusCmdCae + ' cae noGUI=' + inpFilePath, log=f)

                        # Time tests
                        if options.time:
                            timer = _measureRunTimes(precompile=options.precompileCode)
                        else:
                            timer = None

                        # Check for job-specific expiration time
                        try:
                            if options.verbose:
                                print("Attempting to import {}, cwd: {}".format(jobName + '_expected', os.getcwd()))
                            para = __import__(jobName + '_expected').parameters
                            if "expiration" in para:
                                options.expiration = para["expiration"]
                            if options.expiration != None:
                                if options.expiration < 0:
                                    options.expiration = None
                        except:
                            print("WARNING: failed to import _expected.py file, assuming no expiration")
                            options.expiration = None

                        # Execute the solver
                        if not options.useExistingResults:
                            self._runModel(jobName=jobName, logFileHandle=f, timer=timer, expiration=options.expiration)

                        # Execute process_results script load ODB and get results
                        process_results_args = " ".join([jobName, options.outputDirectory, str(options.doNotSave)])
                        if not os.path.isfile(os.path.join(os.getcwd(), options.outputDirectory, jobName + '.odb')):
                            raise Exception("Error: Abaqus odb was not generated. Check the log file in the options.outputDirectory directory.")
                        pathForProcessResultsPy = '"' + os.path.join(ABAVERIFY_INSTALL_DIR, 'processresults.py') + '"'
                        _callAbaqus(cmd=options.abaqusCmdCae + ' cae noGUI=' + pathForProcessResultsPy + ' -- -- ' + process_results_args, log=f, timer=timer)

                    # Run assertions
                    self._runAssertionsOnResults(jobName, None, None)

                finally:  # Make sure temporary files are removed
                    os.remove(os.path.join(os.getcwd(), jobName + '.inp'))  # Delete temporary parametric input file
                    os.remove(os.path.join(os.getcwd(), jobName + '_expected.py'))  # Delete temporary parametric expected results file
                    if os.path.isfile(os.path.join(os.getcwd(), jobName + '_expected.pyc')):
                        os.remove(os.path.join(os.getcwd(), jobName + '_expected.pyc'))  # Delete temporary parametric expected results file
                    if 'pythonScriptForModel' in testCase:
                        os.remove(os.path.join(os.getcwd(), jobName + '.py'))

            # Rename the test method and return the test
            test.__name__ = jobName
            return test

        # Store input arguments
        try:
            baseName = dct['baseName']
            parameters = dct['parameters']
        except Exception:
            print("baseName and parameters must be defined by the sub class")

        # Get the Cartesian product to yield a list of all the potential test cases
        testCases = list(dict(zip(parameters, x)) for x in it.product(*parameters.values()))

        # Loop through each test
        for i in range(0, len(testCases)):

            # Add a name to each test case
            # Generate portion of test name based on particular parameter values
            pn = '_'.join(['%s_%s' % (key, value) for (key, value) in testCases[i].items()])
            # Replace periods with commas so windows doesn't complain about file names
            pn = re.sub('[.]', 'p', pn)
            # Add the test case name; concatenate the base name and parameter name
            testCases[i].update({'name': baseName + '_' + pn})
            testCases[i].update({'baseName': baseName})
            dep_props = {}
            if 'dependent_parameters' in dct:
                for k, v in testCases[i].items():
                    if k in dct['dependent_parameters'].keys():
                        if v in dct['dependent_parameters'][k].keys():
                            dep_props.update(dct['dependent_parameters'][k][v])
                testCases[i].update(dep_props)
                # print('testCases', testCases[i])
            if 'pythonScriptForModel' in dct:
                testCases[i].update({'pythonScriptForModel': dct['pythonScriptForModel']})
            if 'expectedpy_parameters' in dct:
                exp_dict = {}
                if isinstance(dct['expectedpy_parameters'], dict):
                    for k, v in dct['expectedpy_parameters'].items():
                        if isinstance(v, list):
                            exp_dict[k] = v[i]
                        else:
                            exp_dict[k] = v
                elif dct['expectedpy_parameters'] == 'parameters':
                    exp_dict = testCases[i]
                testCases[i].update({'expectedpy_parameters': exp_dict})
            if 'inp_sub' in dct:
                testCases[i].update({'inp_sub': dct['inp_sub']})
            if 'expectedpy_name' in dct:
                testCases[i].update({'expectedpy_name': dct['expectedpy_name']})

            # Add test functions to the testCase class
            dct[testCases[i]['name']] = make_test_function(testCases[i])

        return type.__new__(mcs, name, bases, dct)


def runTests(relPathToUserSub, double=False, compileCodeFunc=None, requireEnv=True):
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
    double : boolean
        If true, abaqus jobs are submitted with the double=both option. There is 
        a command line option for double precision as well. Setting double here 
        overrides the command line option so that double can be hard-coded on for 
        explicit subroutines.
    compileCodeFunc : function, optional
        The function called to compile subroutines via abaqus make. This 
        functionality is used when compiling the subroutine once before running 
        several tests is desired. By default, when the -c option is specified, 
        a generic call to abaqus make is used, which should work most of the 
        time. If the default behavior is not satisfactory, override it with this 
        argument.
    requireEnv : boolean, optional
        If true, the environment is required for the tests. Default is True.

    """

    global ABAVERIFY_INSTALL_DIR
    global options

    # Directory where this file is located
    ABAVERIFY_INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))

    # Command line options
    parser = OptionParser()
    parser.add_option("-i", "--interactive", action="store_true", dest="interactive", default=False, help="Print output to the terminal; useful for debugging")
    parser.add_option("-t", "--time", action="store_true", dest="time", default=False, help="Calculates and prints the time it takes to run each test")
    parser.add_option("-c", "--precompileCode", action="store_true", dest="precompileCode", default=False, help="Compiles the subroutine before running each tests; binaries located in /build (hard coded)")
    parser.add_option("-e", "--useExistingBinaries", action="store_true", dest="useExistingBinaries", default=False, help="Uses existing binaries in `--pathToBinaries` (default is /build)")
    parser.add_option("--pathToBinaries", action="store", type="string", dest="pathToBinaries", default='build', help="Path to existing binaries (use with -e); use absolute path")
    parser.add_option("-r", "--useExistingResults", action="store_true", dest="useExistingResults", default=False, help="Uses existing results in /options.outputDirectory; useful for debugging postprocessing")
    parser.add_option("-s", "--specifyPathToSub", action="store", dest="relPathToUserSub", default=relPathToUserSub, help="Override path to user subroutine")
    parser.add_option("-A", "--abaqusCmd", action="store", type="string", dest="abaqusCmd", default='abaqus', help="Override abaqus command for both job submission and post cae; e.g. abq6141")
    parser.add_option("--abaqusCmdCae", action="store", type="string", dest="abaqusCmdCae", default='abaqus', help="Override abaqus command for cae; e.g. abq6141")
    parser.add_option("--abaqusCmdJob", action="store", type="string", dest="abaqusCmdJob", default='abaqus', help="Override abaqus command for job submission; e.g. abq6141")
    parser.add_option("--abaqusCmdCompile", action="store", type="string", dest="abaqusCmdCompile", default='abaqus', help="Override abaqus command for compiling into library; e.g. abq6141")
    parser.add_option("-k", "--keepExistingOutputFiles", action="store_true", dest="keepExistingOutputFile", default=False, help="Does not delete existing files in the /options.outputDirectory directory")
    parser.add_option("-C", "--cpus", action="store", type="int", dest="cpus", default=1, help="Specify the number of cpus to run abaqus jobs with")
    parser.add_option("-V", "--verbose", action="store_true", dest="verbose", default=False, help="Print information for debugging")
    parser.add_option("-d", "--double", action="store_true", dest="double", default=False, help="Run with double precision (double=both)")
    parser.add_option("-n", "--doNotSaveODB", action="store_true", dest="doNotSave", default=False, help="Does not save x-y data to the ODB")
    parser.add_option("-x", "--expiration", action="store", type="int", default=-1, help="Time in seconds to allow jobs to run before killing them. Defaults to -1 for no time limit.")
    parser.add_option("-o", "--outputDirectory", action="store", type="string", dest="outputDirectory", default='testOutput', help="Directory where job is run and output is generated")
    parser.add_option("-L", "--listTests", action="store_true", dest="listTests", default=False, help="Print a list of the specified tests to the terminal; useful for getting parametric test names")
    parser.add_option("--genPes", action="store_true", dest="genPes", default=False, help="Generate flat input (.pes) files and copy into /pes directory")
    (options, args) = parser.parse_args()

    # Remove custom args so they do not get sent to unittest
    # http://stackoverflow.com/questions/1842168/python-unit-test-pass-command-line-arguments-to-setup-of-unittest-testcase
    # Loop through known options
    short_opts = [h._short_opts[0] if len(h._short_opts) else '' for h in parser.option_list]
    long_opts = [h._long_opts[0] for h in parser.option_list]
    for x in sum([h._long_opts + h._short_opts for h in parser.option_list], []):
        # Check if the known option is an argument 
        if x in sys.argv:
            # Get the option object
            if x in short_opts:
                idx = short_opts.index(x)
                option = parser.option_list[idx]
            elif x in long_opts:
                idx = long_opts.index(x)
                option = parser.option_list[idx]

            # If the option has additional info (e.g. -A abq6141), remove both from argv
            if option.type in ["string", "int"]:
                idx = sys.argv.index(x)
                del sys.argv[idx:idx + 2]
            else:
                sys.argv.remove(x)
    if options.verbose:
        pp = pprint.PrettyPrinter(indent=4)
        print("Options:")
        pp.pprint(options.__dict__)
        print("Arguments passed to unittest:")
        pp.pprint(sys.argv)

    # list tests
    if options.listTests:
        raise Exception('TODO: implement me')

    # Double precision
    if double:
        options.double = True

    # Abaqus command
    if options.abaqusCmd != 'abaqus':
        if options.abaqusCmdCae != 'abaqus':
            print("WARNING: Received both --abaqusCmd and --abaqusCmdCae, using --abaqusCmd")
        if options.abaqusCmdJob != 'abaqus':
            print("WARNING: Received both --abaqusCmd and --abaqusCmdJob, using --abaqusCmd")
        if options.abaqusCmdCompile != 'abaqus':
            print("WARNING: Received both --abaqusCmd and --abaqusCmdCompile, using --abaqusCmd")
        options.abaqusCmdCae = options.abaqusCmd
        options.abaqusCmdJob = options.abaqusCmd
        options.abaqusCmdCompile = options.abaqusCmd

    # Path to binaries
    if options.pathToBinaries == 'build':
        options.pathToBinaries = os.path.join(os.pardir, 'build')
    else:
        if options.precompileCode:
            raise Exception("Option --precompileCode requires --pathToBinaries is the default value = `build`")
        if not os.path.isabs(options.pathToBinaries):
            raise Exception(f"Option --pathToBinaries requires an absolute path, received: {options.pathToBinaries}")

    # Remove rpy files
    testPath = os.getcwd()
    pattern = re.compile(r'^abaqus\.rpy(\.)*([0-9])*$')
    for f in os.listdir(testPath):
        if pattern.match(f):
            try:
                os.remove(os.path.join(os.getcwd(), f))
            except:
                if options.verbose:
                    print("Unable to remove " + f + " skipping it")

    # Remove old binaries
    if not options.useExistingBinaries:
        if os.path.isdir(options.pathToBinaries):
            for f in os.listdir(options.pathToBinaries):
                os.remove(os.path.join(options.pathToBinaries, f))

    # If options.outputDirectory doesn't exist, create it
    options.outputDirectory = os.path.abspath(options.outputDirectory)
    if not os.path.isdir(options.outputDirectory) and options.useExistingResults:
        raise Exception("There must be results in the options.outputDirectory directory to use the --useExistingResults (-r) option")
    if not os.path.isdir(options.outputDirectory):
        os.makedirs(options.outputDirectory)

    # Remove old job files
    if options.useExistingResults:
        # Remove _results.py if it exists
        for f in os.listdir(options.outputDirectory):
            if f.endswith('_results.py'):
                try:
                    os.remove(os.path.join(options.outputDirectory, f))
                except:
                    if options.verbose:
                        print("Unable to remove " + f + " skipping it")

    else:
        if not options.keepExistingOutputFile:
            pattern = re.compile(r'.*v6\.env$|__pycache__')
            for f in os.listdir(options.outputDirectory):
                if not pattern.match(f):
                    try:
                        os.remove(os.path.join(options.outputDirectory, f))
                    except:
                        if options.verbose:
                            print("Unable to remove " + f + " skipping it")
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

            # 4. Get test_ methods list explicitly in the arguments
            for arg in sys.argv[1:]:
                if len(arg.split('.')) == 2:
                    testName = arg.split('.')[1]
                    if 'test' in testName:
                        calledMethods.append(testName)

            # Now we have a list of the test methods that will be called
            # print calledMethods

            # Get a list of unique file names beginning with 'test' in options.outputDirectory directory (w/o file extensions)
            uniquefileNames = list(set([f.split('.')[0] for f in os.listdir(options.outputDirectory) if 'test_' in f]))

            # Check if any files exist in options.outputDirectory with these test names
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
                        _compileCode(options.relPathToUserSub)
                except Exception:
                    print("ERROR: abaqus make failed.", sys.exc_info()[0])
                    raise Exception("Error compiling with abaqus make. Look for 'compile.log' in the options.outputDirectory directory. Or try running 'abaqus make library=CompDam_DGD' from the /for directory to debug.")
                    os.chdir(wd)

        # Make sure
        # 1) environment file exists
        # 2) usub_lib_dir is the location where the binaries reside
        # 3) a copy is in options.outputDirectory
        if os.path.isfile(os.path.join(os.getcwd(), 'abaqus_v6.env')):
            # Make sure it has usub_lib_dir
            if options.precompileCode or options.useExistingBinaries:
                _update_usub_lib_dir()

            # Copy to /test/options.outputDirectory
            else:
                from_ = os.path.join(os.getcwd(), 'abaqus_v6.env')
                to_ = os.path.join(options.outputDirectory, 'abaqus_v6.env')
                if not os.path.isfile(to_):
                    shutil.copyfile(from_, to_ )
                elif not os.path.samefile(from_, to_):
                    shutil.copyfile(from_, to_ )
        else:
            if requireEnv:
                raise Exception("Missing environment file. Please configure a local abaqus environment file. See getting started in readme.")

    print("Running unittest")
    unittest.main(verbosity=3)


def copyFiles(files, substitutions=[], append=[], apply_to_outputDirectory=False):
    """
    Copy files to testOuput directory.

    Parameters
    ----------
    files : str or [str,]
        Name(s) of files in current working director that should be copied to 
        the testOutput directory
    substitutions : [tuple, ]
        List of tuples with re.sub() arguments. Must be the same length as files.
    append : [str, ]
        List of strings to append to the end of each file. Must be the same length as files.
    apply_to_outputDirectory : bool
        Applies the substitutions to the files already in the output directory
    """
    path = options.outputDirectory
    # If the path doesn't exist, create it
    if not os.path.isdir(path):
        os.makedirs(path)

    if apply_to_outputDirectory:
        source_directory = options.outputDirectory
    else:
        source_directory = None
    # Copy files
    if isinstance(files, str):
        files = [files,]
    n_substitutions = len(substitutions)
    if n_substitutions:
        assert n_substitutions == len(files)
    n_appends = len(append)
    if n_appends:
        assert n_appends == len(files)
    for i, f in enumerate(files):
        dst = os.path.join(path, f)
        # Apply substitions
        if n_substitutions:
            apply_substitutions(f, dst, substitutions[i], source_directory)            
        # Copy with no substitutions or appends
        else:
            try:
                shutil.copyfile(f, dst)
            except:
                print(f"WARNING: failed attempt to copy {f} to {dst}")
        if n_appends:
            if len(append[i]):
                with open(dst, 'a') as fp:
                    fp.write(append[i])

def apply_substitutions(orig, updated, substitutions, source_directory=None):
    # Read input deck
    if options.verbose: print('\nRuninng apply_substitutions to: {}'.format(orig))
    if source_directory:
        fp = os.path.join(source_directory, orig)
    else:
        fp = os.path.join(os.getcwd(), orig)
    with open(fp, 'r') as original:
        data = original.readlines()
    for line_num in range(len(data)):
        for sub in substitutions:
            updated_line = re.sub(*sub, data[line_num])
            if updated_line != data[line_num]:
                if options.verbose: print('Updating line {} from: {} to: {}'.format(
                    line_num, data[line_num].strip(), updated_line.strip()))
                data[line_num] = updated_line
                break
    if os.path.isabs(updated):
        fp = updated
    else:
        fp = os.path.join(os.getcwd(), updated)
    with open(fp, 'w') as modified:
        modified.writelines(data)

def getOptions():
    """
    Get the global options object.

    Returns
    -------
    options : object
        The global options object parsed from command line arguments.
    """
    global options
    return options

def _update_usub_lib_dir():
    with open(os.path.join(os.getcwd(), 'abaqus_v6.env'), 'r+') as envFile:
        pattern_usub = re.compile('usub_lib_dir.*')
        lines = []
        found_usub_lib_dir = False
        for line in envFile:
            if pattern_usub.search(line):
                if options.verbose:
                    print("Updating usub_lib_dir in env file")
                # Replace with build location
                new_path = '/'.join(os.path.abspath(options.pathToBinaries).split('\\'))  # Note that this nonsense is because abaqus wants '/' as os.sep even on windows
                lines.append(f'usub_lib_dir = "{new_path}"')
                found_usub_lib_dir = True
            else:
                lines.append(line)
    if not found_usub_lib_dir:
        raise Exception("usub_lib_dir not found in environment file; please make sure it is defined in the env file and try again.")
    with open(os.path.join(options.outputDirectory, 'abaqus_v6.env'), 'w') as envFile:
        envFile.writelines(lines)
