# Attribution and modifications

MRI Validation Audit is a standalone, AI-assisted adaptation of the validation-grouping idea documented in:

> Ou, Y. K. (2026). *Could Your MRI CV Be Learning the Scanner? A copy-ready DICOM audit for RSNA Knee MRI.* Kaggle Notebook. https://www.kaggle.com/code/yangkuangou/could-your-mri-cv-be-learning-the-scanner

The source notebook's original code and prose have an Apache License 2.0 declaration. This release retains that attribution and uses Apache License 2.0 for its original code and prose.

Changes made for this release: a generic standard-library record interface; structured scanner fingerprint serialization; a deterministic greedy component allocator in place of the notebook's scikit-learn splitter; aggregate-only command output; input validation; a fictitious example; independently checked regression tests; explicit input/privacy limitations. There is no bundled copy of the source notebook, DICOM reader, training recipe, report-labeling code, or competition output.

OpenAI Codex assisted with the implementation, documentation, synthetic example and tests. Project provenance does not establish that every line was manually written or establish a novel algorithmic contribution.

The source notebook's license does not extend to competition inputs or third-party libraries. No competition data or third-party code are redistributed here. The Apache License 2.0 text is reproduced in LICENSE.
