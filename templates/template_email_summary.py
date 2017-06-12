test_result = """<tr>
    <td>{test_name}</td>
    <td>{packager_time} s</td>
    <td>{solver_time} s</td>
    <td><font color='{status_color}'><b>{status_text}</b></font></td>
</tr>"""

body = """
<body>For more details, see the testOutput directory archive: <br>
<font color='blue'>{fqdn}:{path_to_archived_tests}.zip</font><br><br>
Git hash: {git_sha}
<br><br>
{abaqus_version}
<br><br>
Summary:<br>
Number of tests that passed: {num_tests_passed} <br>
Number of tests that failed: {num_tests_failed} <br>
Ran {number_of_tests_run} tests in {total_duration}s<br>
<br>
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
</table>
<br>
</body>
"""