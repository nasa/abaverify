test_result = """
<tr>
	<td>{test_name}</td>
	<td>{packager_time} s</td>
	<td>{solver_time} s</td>
	<td><font color='{status_color}'><b>{status_text}</b></font></td>
</tr>
<tr>
"""

body = """
<body>For more details, see the test output archive <br>
<font color='blue'>LASDW40006690.ndc.nasa.gov:C:\Users\abergan\Documents\Research\ACP\CDMDevelopment\DGD\tests\archivedTestResults\DGD_193e028_2016-Jun-06.zip</font><br><br>
Git hash: {git_sha}
<br><br>
<table border='1' cellpadding='3'>
<tr><b>
	<td></td>
	<td colspan='2' align='center'>Runing times</td>
	<td></td>
</b></tr>
<tr><b>
	<td>Test name & description</td>
	<td>Packager</td>
	<td>Solver</td>
	<td>Status</td>
</b></tr>
{test_results}
<br>
</table><br>----------------------------------------------------------------------<br>
Ran {number_of_tests_run} tests in {total_duration}s<br>
<br>
</body>
"""