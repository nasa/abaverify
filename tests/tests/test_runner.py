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
    parameters = {'mass_factor': [1e3, 1e4]}


class SingleElementTests(av.TestCase):

    def test_CPS4R_tension(self):
        self.runTest('test_CPS4R_tension')

    def test_CPS4R_compression(self):
        self.runTest('test_CPS4R_compression')

    @av.unittest.skip('Shear test is work in progress')
    def test_CPS4R_shear(self):
        self.runTest('test_CPS4R_shear')

    def test_CPS4R_tension_tabular(self):
        '''
        Confirm that the tabular query works as expected.
        This input deck checks both forms of the tabular input (list tolerance
        and a single tuple tolerance)
        '''
        self.runTest('test_CPS4R_tension_tabular')

    def test_CPS4R_tension_tabular_with_eval(self):
        '''
        Confirm that the tabular query works with eval statements.
        Eval statements allow you to assign a label_name to the results
        defined by an identifying dict and then use those results in some
        algebraic combination. 
        
        For example, if there was a label = '1' and '2' these could be summed
        using the eval statement d['1'] + d['2'] (where d is an implicitly
        defined dictionary with keys of labels defined inside a ident dict using
        the "av_id" key
        '''
        self.runTest('test_CPS4R_tension_tabular_with_eval')
    
    def test_CPS4R_compression_with_eval(self):
        self.runTest('test_CPS4R_compression_with_eval')

# That's it for setup. Add as many tests as you want!

# This last line is critical, it calls the abaverify code so that when you run this script
# abaverify is executed. The function takes one optional argument: a function to call to compile
# the subroutine code with abaqus make (not shown here).
if __name__ == "__main__":
    av.runTests(relPathToUserSub='../for/vumat', double=True)
