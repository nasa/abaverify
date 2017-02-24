import abaverify as av


class ParametricTests(av.TestCase):
	"""
	Simple example of parametric tests
	"""

	# Specify meta class
	__metaclass__ = av.ParametricMetaClass

	# Refers to the template input file name
	baseName = "test_CPS4R_parametric"

	# Range of parameters to test; multiple can be specified and all combinations are tested
	parameters = {'mass_factor':  [1e3, 1e4]}


class SingleElementTests(av.TestCase):

	def test_CPS4R_tension(self):
		self.runTest('test_CPS4R_tension')

	def test_CPS4R_compression(self):
		self.runTest('test_CPS4R_compression')

	@av.unittest.skip('Shear test is work in progress')
	def test_CPS4R_shear(self):
		self.runTest('test_CPS4R_shear') # TODO


# That's it for setup. Add as many tests as you want!

# This last line is critical, it calls the abaverify code so that when you run this script
# abaverify is executed. The function takes one optional argument: a function to call to compile
# the subroutine code with abaqus make (not shown here).
if __name__ == "__main__":
	av.runTests(relPathToUserSub='../for/vumat')