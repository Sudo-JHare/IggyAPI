# Search Explanation for IggyAPI

This document explains the two search modes available in IggyAPI's `/igs/search` endpoint: `semantic` and `string`. It details how each mode works, their strengths, and the types of queries each is best suited for, helping users choose the appropriate mode for their search needs.

## Overview of the `/igs/search` Endpoint

The `/igs/search` endpoint allows users to search for FHIR Implementation Guides (IGs) by providing a query string. The endpoint supports two search modes, specified via the `search_type` query parameter:

- **`semantic` (default)**: Matches based on the meaning of the query and package metadata, with a fallback to string-based matching.
- **`string`**: Matches based on token similarity and exact/near-exact string matching.

Both modes operate on a pre-filtered list of packages, where the query words must be present in the package name or author field. The search then applies the specified similarity matching to rank and return results.

## Pre-filtering Step (Common to Both Modes)

Before applying either search mode, IggyAPI filters the list of available packages to reduce the search space:

- **How It Works**:
  - The query is split into individual words (e.g., "au core" becomes `["au", "core"]`).
  - Packages are included in the filtered list only if all query words are present in either the `package_name` or `author` field (case-insensitive).
  - For example, the query "au core" will include packages like "hl7.fhir.au.core" because both "au" and "core" are substrings of the package name.

- **Purpose**:
  - This step ensures that only potentially relevant packages are passed to the similarity matching phase, improving performance by reducing the number of comparisons.

## Semantic Search Mode (`search_type=semantic`)

### How It Works

- **Primary Matching (SpaCy Semantic Similarity)**:
  - Uses SpaCy's `en_core_web_md` model to compute the semantic similarity between the query and a combined text of the package's `name`, `description`, and `author`.
  - SpaCy processes both the query and the combined text into `Doc` objects, then uses word embeddings to calculate a similarity score (between 0 and 1) based on the meaning of the texts.
  - A package is included in the results if the similarity score exceeds a threshold of `0.3`.

- **Fallback (Rapidfuzz String Matching)**:
  - If the semantic similarity score is below the threshold, the search falls back to rapidfuzz's `partial_ratio` method for string-based matching.
  - `partial_ratio` computes a score (0 to 100) based on how closely the query matches substrings in the `name`, `description`, or `author` fields.
  - A package is included if the rapidfuzz score exceeds `70`.

- **Result Ranking**:
  - Results are ranked by their similarity scores (semantic or rapidfuzz), with an adjustment factor applied based on the source of the match (e.g., matches in the `name` field are weighted higher).

### Strengths

- **Meaning-Based Matching**:
  - Excels at finding packages that are conceptually similar to the query, even if the exact words differ. For example, a query like "healthcare standard" might match "hl7.fhir.core" because SpaCy understands the semantic relationship between "healthcare" and "fhir".
- **Context Awareness**:
  - Takes into account the `description` and `author` fields, providing a broader context for matching. This can help when package names alone are not descriptive enough.
- **Robust Fallback**:
  - The rapidfuzz fallback ensures that technical queries (e.g., "au core") that might fail semantic matching still return relevant results based on string similarity.

### Best Suited For

- **Conceptual Queries**:
  - Queries where the user is looking for packages related to a concept or topic, rather than an exact name (e.g., "patient data" or "clinical standards").
- **Natural Language Queries**:
  - Longer or more descriptive queries where semantic understanding is beneficial (e.g., "Australian healthcare profiles").
- **General Exploration**:
  - When the user is exploring and might not know the exact package name but has a general idea of what they’re looking for.

### Limitations

- **Technical Queries**:
  - May struggle with short, technical queries (e.g., "au core") if the semantic similarity score is too low, although the rapidfuzz fallback mitigates this.
- **Tokenization Issues**:
  - SpaCy’s tokenization of package names (e.g., splitting "hl7.fhir.au.core" into "hl7", "fhir", "au", "core") can dilute the semantic match for queries that rely on specific terms.
- **Threshold Sensitivity**:
  - The semantic similarity threshold (`0.3`) might still exclude some relevant matches if the query and package metadata are semantically distant, even with the fallback.

## String Search Mode (`search_type=string`)

### How It Works

- **Primary Matching (SpaCy Token Similarity)**:
  - Uses SpaCy to compute a token-based similarity score between the query and the combined text of the package’s `name`, `description`, and `author`.
  - Unlike `semantic` mode, this focuses more on token overlap rather than deep semantic meaning, but still uses SpaCy’s similarity method.
  - A package is included if the token similarity score exceeds a threshold of `0.7`.

- **Fallback (Rapidfuzz String Matching)**:
  - If the token similarity score is below the threshold, the search falls back to rapidfuzz’s `partial_ratio` method.
  - `partial_ratio` computes a score (0 to 100) based on how closely the query matches substrings in the `name`, `description`, or `author` fields.
  - A package is included if the rapidfuzz score exceeds `70`.

- **Result Ranking**:
  - Results are ranked by their similarity scores (token similarity or rapidfuzz), with an adjustment factor applied based on the source of the match (e.g., matches in the `name` field are weighted higher).

### Strengths

- **Exact and Near-Exact Matching**:
  - Excels at finding packages where the query closely matches the package name or author, even with minor variations (e.g., "au core" matches "hl7.fhir.au.core").
- **Technical Queries**:
  - Performs well with short, technical queries that are likely to appear as substrings in package names (e.g., "au core", "fhir r4").
- **Reliable Fallback**:
  - The rapidfuzz fallback ensures that even if SpaCy’s token similarity fails, string-based matching will catch relevant results.

### Best Suited For

- **Exact Name Searches**:
  - Queries where the user knows part of the package name or author and wants an exact or near-exact match (e.g., "au core", "hl7 fhir").
- **Technical Queries**:
  - Short queries that correspond to specific terms or abbreviations in package names (e.g., "r4", "us core").
- **Precise Matching**:
  - When the user prioritizes string similarity over conceptual similarity, ensuring that results closely match the query text.

### Limitations

- **Lack of Semantic Understanding**:
  - Does not consider the meaning of the query, so it might miss conceptually related packages if the exact words differ (e.g., "healthcare standard" might not match "hl7.fhir.core" as well as in `semantic` mode).
- **Token Overlap Dependency**:
  - The initial SpaCy token similarity might still fail for queries with low overlap, relying heavily on the rapidfuzz fallback.
- **Less Contextual**:
  - While it considers `description` and `author`, it’s less effective at leveraging these fields for broader context compared to `semantic` mode.

## Choosing the Right Search Mode

- **Use `semantic` Mode When**:
  - You’re searching for packages related to a concept or topic (e.g., "patient data", "clinical standards").
  - Your query is descriptive or in natural language (e.g., "Australian healthcare profiles").
  - You’re exploring and want to find packages that are conceptually similar, even if the exact words differ.
  - Example: Searching for "healthcare standard" to find "hl7.fhir.core".

- **Use `string` Mode When**:
  - You know part of the package name or author and want an exact or near-exact match (e.g., "au core", "hl7 fhir").
  - Your query is short and technical, likely matching specific terms in package names (e.g., "r4", "us core").
  - You prioritize precise string matching over conceptual similarity.
  - Example: Searching for "au core" to find "hl7.fhir.au.core".

## Example Scenarios

### Scenario 1: Searching for "au core"

- **Semantic Mode**:
  - SpaCy might compute a low semantic similarity score between "au core" and "hl7.fhir.au.core Martijn Harthoorn" due to tokenization and semantic distance.
  - However, the rapidfuzz fallback will match "au core" to "hl7.fhir.au.core" with a high score (e.g., `85`), ensuring the package is included in the results.
- **String Mode**:
  - SpaCy’s token similarity might also be low, but rapidfuzz will match "au core" to "hl7.fhir.au.core" with a high score, returning the package.
- **Best Mode**: `string`, as this is a technical query aiming for an exact match. However, `semantic` mode will now also work due to the rapidfuzz fallback.

### Scenario 2: Searching for "healthcare standard"

- **Semantic Mode**:
  - SpaCy will compute a higher semantic similarity score between "healthcare standard" and "hl7.fhir.core Martijn Harthoorn" because of the conceptual alignment between "healthcare standard" and "fhir".
  - The package is likely to exceed the `0.3` threshold and be included in the results.
- **String Mode**:
  - SpaCy’s token similarity might be low because "healthcare standard" doesn’t directly overlap with "hl7.fhir.core".
  - Rapdfuzz might also fail if the string match isn’t close enough, potentially excluding the package.
- **Best Mode**: `semantic`, as this query is conceptual and benefits from meaning-based matching.

## Conclusion

IggyAPI’s search functionality provides two complementary modes to cater to different user needs:

- **`semantic` Mode**: Best for conceptual, descriptive, or exploratory searches where understanding the meaning of the query is key. It now includes a string-based fallback to handle technical queries better.
- **`string` Mode**: Best for precise, technical searches where the user knows part of the package name or author and wants an exact or near-exact match.

By understanding the strengths of each mode, users can choose the most appropriate `search_type` for their query, ensuring optimal search results.