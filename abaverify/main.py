"""
This is the main API for the abaverify package.
"""
import unittest

#
# Public facing API
#

class TestCase(unittest.TestCase):
	def runTest(self, name):
		print 'Calling ' + name
		self.assertEqual(4,4)

def runTests():
	unittest.main()