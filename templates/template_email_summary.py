test_result = """<tr>
    <td>{test_name}</td>
    <td>{packager_time} s</td>
    <td>{solver_time} s</td>
    <td><font color='{status_color}'><b>{status_text}</b></font></td>
</tr>"""

body = """
<body>
<h3>Test configuration</h3>
<ul style="margin-top:0;">
  <li><b>Git hash:</b> {git_sha}</li>
  <li><b>Abaqus version:</b> {abaqus_version}</li>
  <li><b>Machine:</b> {fqdn}</li>
</ul>

<h3>Summary</h3>
<ul style="margin-top:0;">
  <li><b>Passed:</b> {num_tests_passed}</li>
  <li><b>Failed:</b> {num_tests_failed}</li>
  <li><b>Total:</b> {number_of_tests_run}</li>
  <li><b>Total runtime:</b> {total_duration}</li>
</ul>
<br>
{not_matched_lines}
<br>
{image_html}
<br>
<table border='1' cellpadding='3'>
<tr><b>
    <td></td>
    <td colspan='2' align='center'>Running times</td>
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
