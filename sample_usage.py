"""
This file contains a sample of how you might use the abaverify module.

This file is a python script that is meant as a sample of what you would include
in your project. The assumed directory structure of your project is:

project/
	for/
		usub.for                        <-- User subroutine
	test/
		abaverify/
		test_model1.inp                 <-- A verification model
		test_model1.json                <-- Instructs abaverify what the nominal results should be 
		test_model2.inp
		test_model2.json
		...
		sample_usage.py                 <-- This script. We suggest you rename it something like 'test_runner.py'


This script should be called from the command line in the test/ directory. The conventions used with unittest
apply. To run a single test type:

	test $  python sample_usage.py SingleElementTests.test_model1

To run all tests in a class:

	test $  python sample_usage.py SingleElementTests

To run all tests:

	test $  python sample_usage.py
"""

# Import the module
import abaverify as av


# Create a classs to group your tests. Follow the same pattern as unittest.
# You need to create atleast one test class and add atleast one test to it in order to do anything useful with this module.
# The assumption is that there is one 'test_' function defined for each model. Assertions are run for each nominal expected
# result defined in the corresponding json file.
class SingleElementTests(av.TestCase):

	def test_model1(self):
		self.runTest('test_model1')

	def test_model2(self):
		self.runTest('test_model2')


# Optionally, create parametric tests by defininging a dicitionary of parameters to vary
class ParametricMixedModeMatrix(av.TestCase):

    # Specify meta class (Don't change this line)
    __metaclass__ = av.ParametricMetaClass

    # Refers to the template input file name
    baseName = "test_C3D8R_mixedModeMatrix"

    # Range of parameters to test; all combinations are tested
    # alpha is the angle of the crack normal
    # beta defines the direction of tensile loading in Step-1 and compressive loading in Step-2
    parameters = {'alpha': range(0,50,10), 'beta': range(0,210,30), 'friction': [0.00, 0.15, 0.30, 0.45, 0.60]}



# That's it for setup. Add as many tests as you want!

# This last line is critical, it calls the abaverify code so that when you run this script
# abaverify is executed. The function takes one optional argument: a function to call to compile
# the subroutine code with abaqus make (not shown here).
if __name__ == "__main__":
	av.runTests()