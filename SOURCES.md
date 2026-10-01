# Sources and rights boundaries

| Source | How this release uses it | Boundary |
|---|---|---|
| [Ou, Y. K., Could Your MRI CV Be Learning the Scanner?](https://www.kaggle.com/code/yangkuangou/could-your-mri-cv-be-learning-the-scanner) | Attribution for exact-report/scanner-proxy transitive grouping and the limits of that method. The local teaching package explicitly declares Apache-2.0. | No notebook input, output, DICOM adapter, real field values or competition-derived parameters are copied. |
| [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt) | Full license text for this release. | Does not license input data or unrelated upstream code. |
| [Python `unicodedata`](https://docs.python.org/3/library/unicodedata.html), [`hashlib`](https://docs.python.org/3/library/hashlib.html), [`json`](https://docs.python.org/3/library/json.html) | Standard-library normalization, fingerprints and structured serialization. | There are no vendored dependencies. |
| [scikit-learn `GroupKFold`](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html) | Background on grouped cross-validation; the source notebook uses it. | This release does not import or copy its implementation. The greedy allocator has its own documented behavior. |
| [RSNA Knee competition rules](https://www.kaggle.com/competitions/rsna-knee-abnormality-detection/rules) | Context for the source notebook and data-sharing restrictions. | Data-access or competition-sharing permissions are not granted by this repository. |

All rows in `examples/synthetic_records.json` were invented for this release. They are not sampled, redacted, renamed or transformed from any real dataset. The `synthetic-*` identifiers and `toy-*` fields have no medical or site meaning. `examples/demo_output.txt` is the output of that synthetic example only.

Publication scope is this standalone repository. The original competition workspace, experiment logs, training modules, upstream clones, images, reports, labels, metadata tables, model files and submissions remain outside the release.
