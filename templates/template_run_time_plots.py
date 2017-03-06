# Specify either 'commit' (to label the x-axis with commit sha) or 'date' (to label the x-axis with the date the test was run)
x_axis_qty = 'date'

# Plot dims in pixels
plot_height = 400
plot_width = 1200

# For grouping tests together on same axes
# test_group_prefixes = []

# Formatting for each plt
plot = """
{plot}
<br><br>
"""

# Overall page formatting
body = """
<html>
<body>
{plots}
</body>
</html>
"""