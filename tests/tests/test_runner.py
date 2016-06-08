# This is a crude hack so that we can import the abaverify module for testing purposes
import inspect
import os
import sys
pathForThisFile = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
pathToAbaverifyDir = os.path.join(pathForThisFile, os.pardir, os.pardir)
sys.path.insert(0, pathToAbaverifyDir)

# Normal import line
import abaverify as av


class SingleElementTests(av.TestCase):

	def test_CPS4R_tension(self):
		self.runTest('test_CPS4R_tension')



# That's it for setup. Add as many tests as you want!

# This last line is critical, it calls the abaverify code so that when you run this script
# abaverify is executed. The function takes one optional argument: a function to call to compile
# the subroutine code with abaqus make (not shown here).
if __name__ == "__main__":
	av.runTests(relPathToUserSub='../for/vumat')