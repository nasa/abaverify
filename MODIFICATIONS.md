# Modifications

## 2026-09-26

Modification by Sylvester Kaczmarek, derived from the Original Software Abaverify
provided by NASA under the NASA Open Source Agreement 1.3 in `LICENSE.txt`.

The result assertion path now rejects computed sequences with a different length
from their reference sequences. This prevents incomplete output from passing a
verification test and reports extra output as an assertion failure instead of an
indexing error. Scalar comparisons, element tolerances and custom callbacks are
unchanged.

Added solver-independent regression tests using generated local result files.
Run them after installing Abaverify's dependencies with:

```bash
python -m unittest discover -s tests/unit -v
```
