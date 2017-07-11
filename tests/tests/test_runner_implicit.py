import abaverify as av


class SingleElementTests(av.TestCase):

    def test_CPS4R_tension(self):
        self.runTest('test_CPS4R_tension_implicit')

    def test_CPS4R_compression(self):
        self.runTest('test_CPS4R_compression_implicit')


# That's it for setup. Add as many tests as you want!
# See test_runner.py for a few other examples of how test cases can be setup.

# This last line is critical, it calls the abaverify code so that when you run this script
# abaverify is executed. The function takes one optional argument: a function to call to compile
# the subroutine code with abaqus make (not shown here).
if __name__ == "__main__":
    av.runTests(relPathToUserSub='../for/umat')
