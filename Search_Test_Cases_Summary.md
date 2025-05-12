# IggyAPI Search Test Cases Summary

This document summarizes the search test cases executed on IggyAPI, as captured in the logs from 2025-05-13. It analyzes the behavior of the `/igs/search` endpoint in `semantic` mode, focusing on the frequent fallback to RapidFuzz and the reasons behind SpaCy’s semantic similarity failures.

## Test Case Overview

The logs capture three search requests using `search_type=semantic`, with the following queries: "beda", "au core", and "core". Each search follows a two-step process:

1. **Pre-filtering**: Filters packages based on the presence of query words in the `package_name` or `author` fields.
2. **Similarity Matching**:
   - First attempts SpaCy semantic similarity (threshold: 0.3).
   - If SpaCy fails or the similarity score is below the threshold, falls back to RapidFuzz string matching (threshold: 70).

### Test Case 1: Query "beda"

- **Timestamp**: 2025-05-13 08:01:43
- **Pre-filtering**:
  - Total packages: 1023
  - Filtered packages: 4 (where "beda" appears in `package_name` or `author`)
  - Matching packages: `de.abda.eRezeptAbgabedaten`, `de.abda.eRezeptAbgabedatenBasis`, `de.abda.eRezeptAbgabedatenPKV`, `de.biv-ot.everordnungabgabedaten`
- **SpaCy Semantic Similarity**:
  - Failed with warning: `[W008] Evaluating Doc.similarity based on empty vectors`.
  - Likely cause: "beda" lacks a meaningful embedding in the `en_core_web_md` model, and the combined text (`package_name`, `description`, `author`) for these packages also lacks meaningful embeddings (e.g., empty `description`, technical `package_name` tokens like "abda").
- **Fallback to RapidFuzz**:
  - All 4 packages matched via RapidFuzz with a score of 100.0 (e.g., "beda" is a substring of "abda").
- **Results**:
  - Total matches: 4
  - SpaCy matches: 0 (0%)
  - RapidFuzz matches: 4 (100%)

### Test Case 2: Query "au core"

- **Timestamp**: 2025-05-13 08:02:37
- **Pre-filtering**:
  - Total packages: 1023
  - Filtered packages: 1 (where both "au" and "core" appear in `package_name` or `author`)
  - Matching package: `hl7.fhir.au.core`
- **SpaCy Semantic Similarity**:
  - No semantic match logged, indicating the similarity score was below 0.3.
  - Likely cause: "au" has a weak embedding, "core" is a common word, and the combined text ("hl7.fhir.au.core Martijn Harthoorn") includes noise from the `author` field. The `description` field is empty, providing no additional semantic context.
- **Fallback to RapidFuzz**:
  - Matched via RapidFuzz with a score of 85.71 ("au core" matches "au.core" in the package name).
- **Results**:
  - Total matches: 1
  - SpaCy matches: 0 (0%)
  - RapidFuzz matches: 1 (100%)

### Test Case 3: Query "core"

- **Timestamp**: 2025-05-13 08:02:58
- **Pre-filtering**:
  - Total packages: 1023
  - Filtered packages: 77 (where "core" appears in `package_name` or `author`)
  - Examples: `hl7.fhir.core`, `hl7.fhir.au.core`, `ch.fhir.ig.ch-core`, etc.
- **SpaCy Semantic Similarity**:
  - Succeeded for 14 packages with similarity scores above 0.3:
    - Examples: `ch.fhir.ig.ch-core` (0.6715787550273024), `tiga.health.clinical` (0.6912820366040198).
    - Likely reason: These packages have non-empty `description` fields or `author` names providing semantic context (e.g., healthcare-related terms).
  - Failed for 63 packages (similarity below 0.3).
  - Likely cause: Empty `description` fields, technical `package_name` tokens (e.g., "hl7", "fhir"), and noise from `author` fields dilute similarity scores.
- **Fallback to RapidFuzz**:
  - 63 packages matched via RapidFuzz with scores of 100.0 (e.g., `hl7.fhir.core`, `hl7.fhir.us.core`).
  - "core" is a direct substring of these package names, making RapidFuzz highly effective.
- **Results**:
  - Total matches: 77
  - SpaCy matches: 14 (18%)
  - RapidFuzz matches: 63 (82%)

## Overall Fallback Statistics

- **Total Matches Across All Test Cases**: 82 (4 + 1 + 77)
- **SpaCy Matches**: 14 (all from "core" query)
- **RapidFuzz Matches**: 68 (4 from "beda", 1 from "au core", 63 from "core")
- **Fallback Rate**: 68/82 = 83%

The app falls back to RapidFuzz for 83% of matches, indicating that SpaCy’s semantic similarity is not effective for most packages in these test cases.

## Why the Frequent Fallback to RapidFuzz?

The high fallback rate to RapidFuzz is due to several issues with SpaCy’s semantic similarity in the context of these searches:

### 1. **Weak Embeddings for Technical Terms**
- **Issue**: Queries like "beda", "au", and "core" have weak or no embeddings in the `en_core_web_md` model:
  - "beda" is likely an out-of-vocabulary token.
  - "au" is a short token, possibly treated as a stop word.
  - "core" is a common English word but doesn’t align strongly with tokenized package names (e.g., "hl7", "fhir", "core").
- **Impact**: SpaCy cannot compute meaningful similarity scores, leading to fallbacks.

### 2. **Empty or Sparse Package Descriptions**
- **Issue**: Many FHIR packages have empty `description` fields (e.g., `hl7.fhir.au.core` has no description).
- **Impact**: The combined text (`package_name`, `description`, `author`) lacks semantic content, reducing SpaCy’s ability to find meaningful matches. For example, "hl7.fhir.au.core Martijn Harthoorn" provides little semantic context beyond the package name.

### 3. **Noise from Author Field**
- **Issue**: The `author` field (e.g., "Martijn Harthoorn") is included in the combined text for SpaCy similarity.
- **Impact**: Author names often add noise, diluting the semantic similarity between the query and the package’s core content (e.g., "au core" vs. "hl7.fhir.au.core Martijn Harthoorn").

### 4. **Tokenization of Package Names**
- **Issue**: SpaCy tokenizes package names like "hl7.fhir.au.core" into "hl7", "fhir", "au", "core".
- **Impact**: This splits the package name into parts, reducing the overall semantic alignment with the query (e.g., "au core" doesn’t match strongly with the tokenized form).

### 5. **SpaCy Similarity Threshold (0.3)**
- **Issue**: The threshold for SpaCy semantic similarity is set to 0.3, which is relatively strict.
- **Impact**: Many packages have similarity scores just below 0.3 (e.g., possibly 0.25 for "au core" vs. "hl7.fhir.au.core"), forcing a fallback to RapidFuzz.

### 6. **Empty Vectors Warning**
- **Issue**: For the query "beda", SpaCy raises a warning: `[W008] Evaluating Doc.similarity based on empty vectors`.
- **Impact**: SpaCy fails entirely when either the query or the target text lacks meaningful embeddings, leading to an immediate fallback to RapidFuzz.

## Why RapidFuzz Succeeds

- **Mechanism**: RapidFuzz uses the `partial_ratio` method, which computes a string similarity score (0 to 100) based on substring matches.
- **Effectiveness**:
  - "beda" matches "abda" in package names with a score of 100.0.
  - "au core" matches "au.core" with a score of 85.71.
  - "core" matches package names like "hl7.fhir.core" with a score of 100.0.
- **Threshold**: The RapidFuzz threshold is 70, which is lenient and captures most substring matches.
- **No Dependency on Semantics**: RapidFuzz doesn’t rely on word embeddings or descriptive content, making it effective for technical queries and packages with sparse metadata.

## Conclusion

The IggyAPI search functionality in `semantic` mode falls back to RapidFuzz for 83% of matches due to SpaCy’s limitations with technical queries, sparse package metadata, and a strict similarity threshold. SpaCy struggles with weak embeddings for terms like "beda", "au", and "core", empty package descriptions, noise from author fields, tokenized package names, and a 0.3 similarity threshold. RapidFuzz succeeds where SpaCy fails by focusing on substring matches, ensuring that relevant results are returned despite SpaCy’s shortcomings. This analysis highlights the challenges of applying semantic similarity to technical FHIR data with limited descriptive content.