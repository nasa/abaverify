"""
Opens an abaqus odb and gets requested results

Arguments:
 1. jobName: name of the abaqus job (code expects an odb and a results json file with this name 
 	in the working dir)

Sample usage:
$ abaqus cae noGUI=model_runner.py -- jobName

Output:
This code writes a file jobName_results.json with the reference value and the results collected from the job

Test types:
1. max, min:
    Records the maximum or minimum value of the specified identifier. Assumes that only one identifier is specified.
2. continuous:
    Records the maximum change in the specified identifier value between each increment. This test should fail
    when a discontinuity occurs that is larger than the reference value + tolerance. Assumes that only one
    identifier is specified.
3. xy_infl_pt:
    Records the location of an inflection point in an x-y data set. Assumes two identifiers are specified where 
    the first is the x-data and the second is the y-data. To speed up the search, a window can be specified
    as [min, max] where only values in x withing the bounds of the window are used in searching for the inflection
    point. The reference value and tolerance are specified as pairs corresponding to the x and y values [x, y].
    Numerical derivatives are calculated to find the inflection point. A Butterworth filter is used to smooth the data.
    It is possible that this test could produce errorneous results if the data is too noisy for the filter settings.
4. disp_at_zero_y:
5. log_stress_at_failure_init:
    Writes specified stresses (stressComponents) when first failure index in failureIndices indicates failure (>= 1.0). 
    This test assumes that the input deck terminates the analysis shortly after failure is reached by using the *Filter card.
    All of the failure indices to check for failure should be included in the failureIndices array. The option
    additionalIdenitifiersToStore can be used to record additional outputs at the increment where failure occurs
    (e.g., alpha). Stress in stressComponents and other data in additionalIdenitifiersToStore are written to a log
    file that is named using the test base name.
"""


from abaqus import *
import abaqusConstants
from abaqusConstants import *
from caeModules import *
import job

import sys
import json
import re
import shutil
import numpy as np
from operator import itemgetter

# This is a brittle hack. TODO: use a different json parsing package, or put the existing code into a python package
import inspect
pathForThisFile = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
sys.path.insert(0, pathForThisFile)
import jsonparser


# Throw-away debugger
def debug(obj):
    if True:   # Use to turn off debugging
        sys.__stderr__.write("DEBUG - " + __name__ + ":  " + str(obj) + '\n')


def interpolate(x, xp, fp):
    """
    Augmentation to np.interp to handle negative numbers. This is a hack, needs improvement.
    """
    if np.all(np.diff(xp) > 0):
        return np.interp(x, xp, fp)
    else:
        if all([i<0 for i in xp]):
            xpos = np.absolute(xp)
            return np.interp(-1*x, xpos, fp)
        else:
            raise Exception("Functionality to interpolate datasets that traverse 0 or are unsorted is not implemented")
        
    
def resample(data, numPts):
    """
    Re-samples an xy data set to have the number of points specified and a linear space in x
    """
    x, y = zip(*data)
    if x[0] < x[-1]:
        xMin = x[0]
        xMax = x[-1]
    else:
        xMin = x[-1]
        xMax = x[0]
    xNew = np.linspace(xMin, xMax, numPts)
    yNew = interpolate(xNew, x, y)
    return zip(xNew, yNew)


def listOfHistoryOutputSymbols():
    """
    Generates a list of the history output symbols in the odb
    """
    outputs = list()
    for s in odb.steps.keys():
        for hr in odb.steps[s].historyRegions.keys():
            for ho in odb.steps[s].historyRegions[hr].historyOutputs.keys():
                if ho not in outputs:
                    outputs.append(ho)
    return outputs


def parseJobName(name):
    """
    Parses job name of paramtric tests
    """

    s = name.split("_")

    output = dict()

    # Find the index of the first integer (value of paramter)
    idxFirstInt = 0
    while True:
        try:
            int(s[idxFirstInt])
            break
        except ValueError:
            idxFirstInt += 1

    # Everything before the first integer is the basename
    output["baseName"] = "_".join(s[0:idxFirstInt-1])

    # Assume everything after the basename is paramters and values
    for n in range(idxFirstInt-1, len(s), 2):
        output[s[n]] = s[n+1]

    return output


def _historyOutputNameHelperNode(prefixString, identifier, steps):
    """ Helper to prevent repeated code in historyOutputNameFromIdentifier """

    i = str(identifier["symbol"])
    if "position" in identifier and "nset" in identifier:
        return prefixString + i + " at " + str(identifier["position"]) + " in NSET " + str(identifier["nset"])
    elif "nset" in identifier:
        if len(steps) > 1:
            raise Exception("_historyOutputNameHelperNode: Must specify position if analysis has multiple steps")
        else:
            step = steps[0]
        for historyRegions in odb.steps[step].historyRegions.keys():
            regionLabels = [x for x in odb.steps[step].historyRegions.keys() if odb.steps[step].historyRegions[x].historyOutputs.has_key(i)]
            if len(regionLabels) == 1:
                labelSplit = regionLabels[0].split(' ')
                if labelSplit[0] == 'Node' and len(labelSplit) == 2:
                    nodeNumber = labelSplit[1].split('.')[1]
                    return prefixString + i + " at Node " + nodeNumber + " in NSET " + str(identifier["nset"])
                else:
                    raise Exception("Must specify a position for " + i)
            else:
                raise Exception("Found multiple candidate positions. Must specify a position for " + i)
    else:
        raise ValueError("Missing nset definition in RF identifier")

    raise Exception("Error getting history Output name in _historyOutputNameHelperNode")


def _historyOutputNameHelperElement(prefixString, identifier, steps):
    """ Helper to prevent repeated code in historyOutputNameFromIdentifier """

    i = str(identifier["symbol"])
    if "position" in identifier and "elset" in identifier:
        if i not in listOfHistoryOutputSymbols():
            for sym in listOfHistoryOutputSymbols():
                if i.lower() == sym.lower():
                    i = sym
        return prefixString + i + " at " + str(identifier["position"]) + " in ELSET " + str(identifier["elset"])
    else:
        raise ValueError("Must define position in element identifier")


def historyOutputNameFromIdentifier(identifier, steps=None):
    """
    Returns a well-formated history output name from the identifier. The identifier can be in any of a variety of 
    formats. A list of identifiers can be provided in which case this function returns a tuple of history output names.

    The step is the name of the step of interest.

    
    Accepted identifier formats (JSON):
    # Specify the complete identifier
    - "identifier": "Reaction force: RF1 at Node 9 in NSET LOADAPP"
    # Specify the complete identifier piecemeal
    - "identifier": {
                "symbol": "RF1",
                "position": "Node 9",
                "nset": "LOADAPP"
            }
    # For element output data, "elset" can be used
    - "identifier": {
                "symbol": "S11",
                "position": "Element 1 Int Point 1",
                "elset": "DAMAGEABLEROW"
            }
    # Specify the identifier without a position. In this case, the code looks through the available history outputs for a 
    # valid match. If a single match is found, it is used. Otherwise an exception is raised. The step argument must be specified.
    - "identifier": {
                "symbol": "RF1",
                "nset": "LOADAPP"
            }
    # Not implemented for an element (yet)
    """

    # Handle case of a list of identifiers
    if type(identifier) == type(list()):
        out = list()
        for i in identifier:
            out.append(historyOutputNameFromIdentifier(identifier=i, steps=steps))
        return tuple(out)
    
    # Case when identifier is a dictionary
    elif type(identifier) == type(dict()):
        if "symbol" in identifier:
            i = str(identifier["symbol"])

            # Parse the symbol. Known symbols (RF, U, S, LE, E, SDV)
            # RF
            if re.match(r'^RF\d', i):
                return _historyOutputNameHelperNode(prefixString="Reaction force: ", identifier=identifier, steps=steps)

            # U
            elif re.match(r'^U\d', i):
                return _historyOutputNameHelperNode(prefixString="Spatial displacement: ", identifier=identifier, steps=steps)

            # S
            elif re.match(r'^S\d+', i):
                return _historyOutputNameHelperElement(prefixString="Stress components: ", identifier=identifier, steps=steps)

            # LE
            elif re.match(r'^LE\d+', i):
                return _historyOutputNameHelperElement(prefixString="Logarithmic strain components: ", identifier=identifier, steps=steps)

            # E
            elif re.match(r'^E\d+', i):
                raise NotImplementedError()

            # SDV
            elif re.match(r'^SDV\w+', i):
                return _historyOutputNameHelperElement(prefixString="Solution dependent state variables: ", identifier=identifier, steps=steps)

            else:
                raise ValueError("Unrecognized symbol " + i + " found")
        else:
            raise ValueError("Identifier missing symbol definition")

    # Case when the identifer is specified directly
    elif type(identifier) == type(str()) or type(identifier) == type(unicode()):
        return str(identifier)
    else:
        raise ValueError("Expecting that the argument is a list, dict, or str. Found " + str(type(identifier)))



# Arguments
jobName = sys.argv[-1]
# jobName = "test_C3D8R_fiberMaimiLoadReversal"      # For debugging

# Load parameters
fileName = os.path.join(os.getcwd(), jobName + '.json')
para = jsonparser.parse(fileName)

# Change working directory to testOutput and put a copy of the input file in testOutput
os.chdir(os.path.join(os.getcwd(), 'testOutput'))

# Load ODB
odb = session.openOdb(name=os.path.join(os.getcwd(), jobName + '.odb'), readOnly=False)

# Report errors
if odb.diagnosticData.numberOfAnalysisErrors > 0:
    # Ignore excessive element distortion errors when generating failure envelopes
    resultTypes = [r["type"] for r in para["results"]]
    if "log_stress_at_failure_init" in resultTypes:
        for e in odb.diagnosticData.analysisErrors:
            if e.description != 'Excessively distorted elements':
                raise Exception("\nERROR: Errors occurred during analysis")
    if "ignoreAnalysisErrors" in para:
        if not para["ignoreAnalysisErrors"]:
            raise Exception("\nERROR: Errors occurred during analysis")
    else:
        raise Exception("\nERROR: Errors occurred during analysis")

# Report warnings
if "ignoreWarnings" in para and not para["ignoreWarnings"]:
    if odb.diagnosticData.numberOfAnalysisWarnings > 0:
        raise Exception("\nERROR: Warnings occurred during analysis")


# Initialize dict to hold the results -- this will be used for assertions in the test_runner
testResults = list()

# Collect results
for r in para["results"]:

    # Get the steps to consider. Default to "Step-1"
    if "step" in r:
        steps = (str(r["step"]), )
    else:
        steps = ("Step-1", )
    
    # Debugging
    debug(steps)
    debug(r)

    # Collect data from odb for each type of test

    # Max, min
    if r["type"] in ("max", "min"):

        # This trys to automatically determine the appropriate position specifier
        varName = historyOutputNameFromIdentifier(identifier=r["identifier"], steps=steps)

        # Get the history data
        n = str(r["identifier"]["symbol"]) + '_' + steps[0] + '_' + str(r["type"])
        xyDataObj = session.XYDataFromHistory(name=n, odb=odb, outputVariableName=varName, steps=steps)
        xy = session.xyDataObjects[n]
        odb.userData.XYData(n, xy)

        # Get the value calculated in the analysis (last frame must equal to 1, which is total step time)
        if r["type"] == "max":
            r["computedValue"] = max([pt[1] for pt in xyDataObj])
        else:
            r["computedValue"] = min([pt[1] for pt in xyDataObj])
        testResults.append(r)
    

    # Enforce continuity
    elif r["type"] == "continuous":

        # This trys to automatically determine the appropriate position specifier
        varName = historyOutputNameFromIdentifier(identifier=r["identifier"], steps=steps)

        # Get the history data
        xyDataObj = session.XYDataFromHistory(name='XYData-1', odb=odb, outputVariableName=varName, steps=steps)

        # Get the maximum change in the specified value
        r["computedValue"] = max([max(r["referenceValue"], abs(xyDataObj[x][1] - xyDataObj[x-1][1])) for x in range(2,len(xyDataObj))])
        testResults.append(r)


    elif r["type"] == "xy_infl_pt":
        varNames = historyOutputNameFromIdentifier(identifier=r["identifier"], steps=steps)

        # Get xy data
        x = session.XYDataFromHistory(name=str(r["identifier"][0]["symbol"]), odb=odb, outputVariableName=varNames[0], steps=steps)
        y = session.XYDataFromHistory(name=str(r["identifier"][1]["symbol"]), odb=odb, outputVariableName=varNames[1], steps=steps)

        # Combine the x and y data
        xy = combine(x, y)
        tmpName = xy.name
        session.xyDataObjects.changeKey(tmpName, 'ld')
        xy = session.xyDataObjects['ld']
        odb.userData.XYData('ld', xy)

        # Locals
        xyData = xy
        windowMin=r["window"][0]
        windowMax=r["window"][1]
        
        # Select window
        windowed = [x for x in xyData if x[0] > windowMin and x[0] < windowMax]
        if len(windowed) == 0: raise Exception("No points found in specified window")
        if min([abs(windowed[i][0]-windowed[i-1][0]) for i in range(1, len(windowed))]) == 0:
            raise "ERROR"
        session.XYData(data=windowed, name="windowed")
        ldWindowed = session.xyDataObjects['windowed']
        odb.userData.XYData('windowed', ldWindowed)

        # Calcuate the derivative using a moving window
        xy = differentiate(session.xyDataObjects['windowed'])
        xy = resample(data=xy, numPts=10000)
        
        # Filter
        if "filterCutOffFreq" in r["identifier"][1]:
            session.XYData(data=xy, name="temp")
            xy = butterworthFilter(xyData=session.xyDataObjects['temp'], cutoffFrequency=int(r["identifier"][1]["filterCutOffFreq"]))
            tmpName = xy.name
            session.xyDataObjects.changeKey(tmpName, 'slope')
        else:
            session.XYData(data=xy, name="slope")
        slopeXYObj = session.xyDataObjects['slope']
        odb.userData.XYData('slope', slopeXYObj)

        # Differentiate again
        xy = differentiate(session.xyDataObjects['slope'])
        tmpName = xy.name
        session.xyDataObjects.changeKey(tmpName, 'dslope')

        # Get peak from dslope
        dslope = session.xyDataObjects['dslope']
        odb.userData.XYData('dslope', dslope)
        x, y = zip(*dslope)
        y = np.absolute(y)
        dslope = zip(x,y)
        xMax, yMax = max(dslope, key=itemgetter(1))

        # Store the x, y pair at the inflection point
        x, y = zip(*session.xyDataObjects['windowed'])
        r["computedValue"] = (xMax, interpolate(xMax, x, y))
        testResults.append(r)


    elif r["type"] == "disp_at_zero_y":
        varNames = historyOutputNameFromIdentifier(identifier=r["identifier"], steps=steps)

        # Get xy data
        x = session.XYDataFromHistory(name=str(r["identifier"][0]["symbol"]), odb=odb, outputVariableName=varNames[0], steps=steps)
        y = session.XYDataFromHistory(name=str(r["identifier"][1]["symbol"]), odb=odb, outputVariableName=varNames[1], steps=steps)
        xy = combine(x, y)

        # Window definition
        if "window" in r:
            windowMin = r["window"][0]
            windowMax = r["window"][1]
        else:
            windowMin = r['referenceValue'] - 2*r['tolerance']
            windowMax = r['referenceValue'] + 2*r['tolerance']

        # Use subset of full traction-separation response
        windowed = [x for x in xy if x[0] > windowMin and x[0] < windowMax]

        # Tolerance to zero
        if "zeroTol" not in r:
            r["zeroTol"] = 1e-6

        # Find pt where stress goes to target
        disp_crit = 0
        for pt in windowed:
            if abs(pt[1]) <= r["zeroTol"]:
                disp_crit = pt[0]
                break

        # Issue error if a value was not found
        if disp_crit == 0:
            raise ValueError("disp_at_zero_y: Could not find a point where y data goes to zero")

        r["computedValue"] = disp_crit
        testResults.append(r)


    elif r["type"] == "log_stress_at_failure_init":
        
        # Load history data for failure indices and store xy object to list 'failed' if the index is failed at last increment
        failed = list()
        varNames = historyOutputNameFromIdentifier(identifier=r["failureIndices"], steps=steps)
        for i in range(0, len(varNames)):
            n = str(r["failureIndices"][i]["symbol"])
            xy = session.XYDataFromHistory(name=n, odb=odb, outputVariableName=varNames[i], steps=steps)
            xy = session.xyDataObjects[n]
            odb.userData.XYData(n, xy)
            if xy[-1][1] >= 1.0:
                failed.append(xy)

        # Make sure at least one failure index has reached 1.0
        if len(failed) <= 0:
            raise Exception("No failure occurred in the model")

        # Find the increment number where failure initiated
        i = len(failed[0])
        while True:
            i = i - 1
            if len(failed) > 1:
                for fi in failed:
                    if fi[i][1] < 1.0:
                        failed.remove(fi)
                if len(failed) < 1:
                    raise NotImplementedError("Multiple failure modes occurred at the same increment")
                continue
            else:
                if failed[0][i][1] >= 1.0:
                    continue
                elif failed[0][i][1] < 1.0:
                    inc = i + 1
                    break

        # Get values of stress at final failure
        stressAtFailure = dict()
        varNames = historyOutputNameFromIdentifier(identifier=r["stressComponents"], steps=steps)
        for i in range(0, len(varNames)):
            n = str(r["stressComponents"][i]["symbol"])
            xy = session.XYDataFromHistory(name=n, odb=odb, outputVariableName=varNames[i], steps=steps)
            xy = session.xyDataObjects[n]
            odb.userData.XYData(n, xy)
            stressAtFailure[n] = xy[inc][1]

        # Get additionalIdentifiersToStore data
        additionalData = dict()
        varNames = historyOutputNameFromIdentifier(identifier=r["additionalIdentifiersToStore"], steps=steps)
        for i in range(0, len(varNames)):
            n = str(r["additionalIdentifiersToStore"][i]["symbol"])
            xy = session.XYDataFromHistory(name=n, odb=odb, outputVariableName=varNames[i], steps=steps)
            xy = session.xyDataObjects[n]
            odb.userData.XYData(n, xy)
            additionalData[n] = xy[inc][1]

        
        # Get job name
        jnparsed = parseJobName(jobName)

        # Format string of data to write
        dataToWrite = jnparsed["loadRatio"] + ', ' + ', '.join([str(x[1]) for x in sorted(stressAtFailure.items(), key=itemgetter(0))])
        dataToWrite += ', ' + ', '.join([str(x[1]) for x in sorted(additionalData.items(), key=itemgetter(0))]) + '\n'

        # Write stresses to file for plotting the failure envelope
        # Write heading if this is the first record in the file
        logFileName = jnparsed["baseName"] + "_" + "failure_envelope.txt"
        if not os.path.isfile(logFileName):
            heading = 'Load Ratio, ' + ', '.join([str(x[0]) for x in sorted(stressAtFailure.items(), key=itemgetter(0))])
            heading += ', ' + ', '.join([str(x[0]) for x in sorted(additionalData.items(), key=itemgetter(0))]) + '\n'
            dataToWrite = heading + dataToWrite
        with open(logFileName, "a") as f:
            f.write(dataToWrite)


    elif r["type"] == "slope":
        varNames = historyOutputNameFromIdentifier(identifier=r["identifier"], steps=steps)

        # Get xy data
        x = session.XYDataFromHistory(name=str(r["identifier"][0]["symbol"]), odb=odb, outputVariableName=varNames[0], steps=steps)
        y = session.XYDataFromHistory(name=str(r["identifier"][1]["symbol"]), odb=odb, outputVariableName=varNames[1], steps=steps)

        # Combine the x and y data
        xy = combine(x, y)
        tmpName = xy.name
        session.xyDataObjects.changeKey(tmpName, 'slope_xy')
        xy = session.xyDataObjects['slope_xy']
        odb.userData.XYData('slope_xy', xy)

        # Locals
        xyData = xy
        windowMin=r["window"][0]
        windowMax=r["window"][1]
        
        # Select window
        windowed = [x for x in xyData if x[0] > windowMin and x[0] < windowMax]
        if len(windowed) == 0: raise Exception("No points found in specified window")
        if min([abs(windowed[i][0]-windowed[i-1][0]) for i in range(1, len(windowed))]) == 0:
            raise "ERROR"
        session.XYData(data=windowed, name="windowed")
        ldWindowed = session.xyDataObjects['windowed']
        odb.userData.XYData('windowed', ldWindowed)

        # Calcuate the derivative
        xy = differentiate(session.xyDataObjects['windowed'])
        tmpName = xy.name
        session.xyDataObjects.changeKey(tmpName, 'slope_xy_diff')
        odb.userData.XYData('slope_xy_diff', session.xyDataObjects['slope_xy_diff'])

        # Get the average value of the slope
        x, y = zip(*session.xyDataObjects['slope_xy_diff'])
        r["computedValue"] = np.mean(y)
        testResults.append(r)
        

    else:
        raise NotImplementedError("test_case result data not recognized: " + str(r))

# Save the odb
odb.save()

# Write the results to a json file for assertions by test_runner
fileName = os.path.join(os.getcwd(), jobName + '_results.json')
with open(fileName, 'w') as outfile:
    json.dump(testResults, outfile, indent=4, separators=(',', ': '))
