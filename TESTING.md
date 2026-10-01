# Release-preparation verification

Verified locally on **2026-10-01** with **Python 3.14.6**, using only the standard library:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 mri_validation_audit.py --demo
```

The final local run passed **20 tests**. It includes a 100-case independent graph/BFS comparison, deliberate leaking assignments, empty-fold rejection, input-order determinism, fingerprint boundaries, complete coverage and CLI privacy/error checks. The recorded 0.374-second test-suite duration is an execution observation, not a scalability benchmark.

The synthetic demonstration has 10 records, six connected components and three validation folds of sizes 4, 3 and 3. Report, scanner-proxy and component crossing counts are all zero. [demo_output.txt](examples/demo_output.txt) was generated in this verification session.

An independent review identified an API case where empty observations or empty validation folds could pass the overlap check. The release fixes that case and adds direct regression tests. Existing leaking splits with nonempty folds still produce detailed aggregate overlap counts.

No real medical input, source competition notebook, training recipe or model was run during these checks. Source-notebook runtime/PASS records belong to earlier work and are not evidence for this implementation. The GitHub Actions matrix is configured for Python 3.10, 3.12 and 3.14; configuring it does not claim a completed CI run.
