# IggyAPI - IGGY: Your IG Spirit Animal
Knows every guide inside out, and helps you fetch, explore, and use them.
![IggyAPI Logo](IggyAPI.png)

IggyAPI is a FastAPI-based application designed to search, retrieve, and manage FHIR Implementation Guides (IGs) and their associated StructureDefinitions (profiles). It offers a powerful interface for querying FHIR packages, listing profiles within an IG, and fetching specific StructureDefinitions with the option to strip narrative content. Tailored to support healthcare interoperability in an Australian context, IggyAPI focuses on AU Core profiles but is capable of handling IGs from various FHIR registries worldwide.

## Table of Contents

- [Project Overview](#project-overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running IggyAPI](#running-iggyapi)
- [Build the Docker Image](#build-the-docker-image)
- [Run the Docker Container](#run-the-docker-container)
- [API Endpoints](#api-endpoints)
  - [Search Implementation Guides](#search-implementation-guides)
  - [List Profiles in an IG](#list-profiles-in-an-ig)
  - [Get a Specific Profile](#get-a-specific-profile)
  - [Get Refresh Status](#get-refresh-status)
  - [Force Cache Refresh](#force-cache-refresh)
- [Response Samples](#response-samples)
- [Testing IggyAPI](#testing-iggyapi)
- [Implementation Details](#implementation-details)
- [Contributing](#contributing)
- [License](#license)

## Project Overview

IggyAPI is a backend service that enables developers and healthcare systems to interact with FHIR Implementation Guides programmatically. It retrieves metadata from FHIR registries, caches the data, and provides endpoints to search for IGs, list profiles within an IG, and fetch specific StructureDefinitions. A key feature of IggyAPI is its support for narrative stripping in StructureDefinitions, which helps reduce payload size when human-readable content is not required.

While IggyAPI is particularly focused on supporting AU Core profiles (e.g., `hl7.fhir.au.core`), it is designed to work with any FHIR IG published in supported registries, such as `packages.fhir.org` and `packages.simplifier.net`.

## Features

- **Search IGs**: Query Implementation Guides using a search term with semantic or string similarity matching.
- **List Profiles**: Retrieve a list of StructureDefinitions (profiles) within a specified IG, with optional version filtering.
- **Fetch Profiles**: Obtain a specific StructureDefinition by IG and profile ID, with an option to exclude narrative content.
- **Cache Management**: Automatically syncs IG metadata from registries every 8 hours or on demand, with status reporting.
- **Robust Error Handling**: Provides detailed error messages for invalid requests or unavailable resources.
- **Swagger UI**: Offers an interactive API documentation interface at `/docs`.

## Prerequisites

Before setting up IggyAPI, ensure you have the following installed:

- **Python 3.8+**: IggyAPI is built using Python.
- **pip**: Python package manager for installing dependencies.
- **SQLite**: Used for caching (included with Python).
- **Git**: For cloning the repository (optional).
- **Docker**: Required for running IggyAPI in a container.
- **SpaCy Model**: IggyAPI uses SpaCy for advanced search functionality, requiring the `en_core_web_md` model for semantic similarity searches.

An internet connection is required to fetch IG metadata from FHIR registries during the initial sync.

## Installation

1. **Clone the Repository** (if applicable):
   ```bash
   git clone <repository-url>
   cd iggyapi
   ```

2. **Create a Virtual Environment** (recommended for non-Docker setup):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies** (for non-Docker setup):
   IggyAPI requires several Python packages listed in `requirements.txt`. Install them using:
   ```bash
   pip install -r requirements.txt
   ```
   Example `requirements.txt`:
   ```
   fastapi==0.115.0
   uvicorn==0.30.6
   requests==2.32.3
   feedparser==6.0.11
   sqlalchemy==2.0.35
   tenacity==9.0.0
   rapidfuzz==3.10.0
   spacy==3.7.6
   en-core-web-md @ https://github.com/explosion/spacy-models/releases/download/en_core_web_md-3.7.1/en_core_web_md-3.7.1-py3-none-any.whl
   ```

4. **Verify Setup** (for non-Docker setup):
   Ensure all dependencies are installed by running:
   ```bash
   pip list
   ```
   Confirm that `fastapi`, `uvicorn`, `requests`, `sqlalchemy`, `spacy`, and other required packages are listed.

5. **Verify SpaCy Model** (for non-Docker setup):
   Confirm that the SpaCy model is installed by running:
   ```bash
   python -m spacy validate
   ```
   You should see `en_core_web_md` listed as installed. If not, ensure the model was downloaded correctly via the `requirements.txt` installation.

## Running IggyAPI

1. **Start the Server** (for non-Docker setup):
   Launch IggyAPI using `uvicorn`:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
   - `--host 0.0.0.0`: Allows external access to the API.
   - `--port 8000`: The port to listen on (default is 8000; adjust as needed).

2. **Access IggyAPI**:
   - Open your browser and navigate to `http://localhost:8000/docs` to access the Swagger UI.
   - The Swagger UI provides an interactive interface to test IggyAPI’s endpoints.

3. **Initial Sync and Scheduled Refreshes**:
   On startup, IggyAPI will load any existing data from the database into memory, even if it’s older than 8 hours. If the data is older than 8 hours or missing, a background refresh will be triggered to fetch the latest IG metadata from FHIR registries. This process may take a few minutes depending on your internet connection. After the initial refresh, IggyAPI schedules automatic refreshes every 8 hours from the last refresh time (whether triggered at startup, in the background, or manually via the `/refresh-cache` endpoint). You can also trigger a manual refresh at any time using the `/refresh-cache` endpoint.

## Build the Docker Image

Ensure you are in the project directory where the `Dockerfile` is located. Build the Docker image using:
```bash 
docker build -t iggyapi:latest .
```
This creates an image named `iggyapi` with the `latest` tag. Optionally, you can add a `--name iggyapi-container` flag during the run step to name the container for easier reference.

## Run the Docker Container

Start a container from the built image, mapping port 8000 on your host to port 8000 in the container:
```bash
docker run -d -p 8000:8000 -e PORT=8000 -v C:/git/IggyApi/instance:/app/instance --name iggyapi-container iggyapi:latest
```

**Verify the Container is Running**:
Check the status of the container:
```bash
docker ps
```
You should see `iggyapi-container` listed as running.

**Initial Sync and Scheduled Refreshes**:
On startup, IggyAPI will load any existing data from the database into memory, even if it’s older than 8 hours. If the data is older than 8 hours or missing, a background refresh will be triggered to fetch the latest IG metadata from FHIR registries. This process may take a few minutes depending on your internet connection. After the initial refresh, IggyAPI schedules automatic refreshes every 8 hours from the last refresh time (whether triggered at startup, in the background, or manually via the `/refresh-cache` endpoint). You can also trigger a manual refresh at any time using the `/refresh-cache` endpoint.

## API Endpoints

IggyAPI provides the following endpoints, all documented in the Swagger UI at `/docs`.

### Search Implementation Guides

- **Endpoint**: `GET /igs/search`
- **Query Parameters**:
  - `query` (string, optional): A search term to filter IGs by name or author (e.g., `au core`).
  - `search_type` (string, optional, default: `semantic`): The type of search to perform. Options are:
    - `semantic`: Uses SpaCy for semantic similarity, matching based on the meaning of the query and package metadata. If the semantic similarity is low, it falls back to rapidfuzz for string-based matching.
    - `string`: Uses SpaCy for token-based string similarity, with a fallback to rapidfuzz for exact or near-exact string matching.
- **Description**: Searches for FHIR Implementation Guides using either semantic or string similarity matching. The search first filters packages by ensuring all words in the query are present in the package name or author, then applies the specified similarity search on the filtered results. Returns a list of matching IGs with metadata such as version, FHIR version, and relevance score.
- **Response**: A JSON object containing a list of IGs, total count, and cache status.

### List Profiles in an IG

- **Endpoint**: `GET /igs/{ig_id}/profiles`
- **Path Parameter**:
  - `ig_id` (string, required): The ID of the IG (e.g., `hl7.fhir.au.core` or `hl7.fhir.au.core#1.1.0-preview`).
- **Query Parameter**:
  - `version` (string, optional): The version of the IG (e.g., `1.1.0-preview`). Overrides the version in `ig_id` if provided.
- **Description**: Lists all StructureDefinitions (profiles) within the specified IG. Downloads the IG package if not already cached and extracts profile metadata.
- **Response**: A list of profiles with their name, description, version, and URL.

### Get a Specific Profile

- **Endpoint**: `GET /igs/{ig_id}/profiles/{profile_id}`
- **Path Parameters**:
  - `ig_id` (string, required): The ID of the IG (e.g., `hl7.fhir.au.core`).
  - `profile_id` (string, required): The ID or name of the profile (e.g., `AUCorePatient`).
- **Query Parameters**:
  - `version` (string, optional): The version of the IG (e.g., `1.1.0-preview`).
  - `include_narrative` (boolean, optional, default: `true`): Whether to include the narrative (`text` element) in the StructureDefinition. Set to `false` to strip the narrative.
- **Description**: Retrieves a specific StructureDefinition from the IG. Supports narrative stripping to reduce payload size.
- **Response**: A JSON object containing the StructureDefinition resource.

### Get Refresh Status

- **Endpoint**: `GET /status`
- **Description**: Returns the status of the last cache refresh, including the timestamp, package count, and any errors encountered.
- **Response**: A JSON object with refresh status details.

### Force Cache Refresh

- **Endpoint**: `POST /refresh-cache`
- **Description**: Forces an immediate refresh of the IG metadata cache by re-syncing with FHIR registries. This also resets the scheduled refresh timer to 8 hours from the time of the manual refresh.
- **Response**: A JSON object with the updated refresh status.

## Response Samples

Below are sample responses for IggyAPI’s main endpoints, illustrating the output format.

### Search Implementation Guides Response

**Request**:
```
GET /igs/search?query=core
```

**Response** (`response_Search.json`):
```json
{
  "packages": [
    {
      "id": "hl7.fhir.core",
      "name": "hl7.fhir.core",
      "description": "",
      "url": "https://packages.simplifier.net/hl7.fhir.core/4.3.0",
      "Author": "Martijn Harthoorn",
      "fhir_version": "4",
      "Latest_Version": "4.3.0",
      "version_count": 9,
      "all_versions": [
        {
          "version": "4.3.0",
          "pubDate": "Wed, 29 Mar 2023 11:22:42 GMT"
        },
        {
          "version": "3.2.0",
          "pubDate": "Thu, 23 Apr 2020 11:48:07 GMT"
        },
        {
          "version": "4.0.1",
          "pubDate": "Thu, 23 Apr 2020 11:37:44 GMT"
        },
        {
          "version": "3.5.0",
          "pubDate": "Thu, 23 Apr 2020 11:37:25 GMT"
        },
        {
          "version": "3.0.2",
          "pubDate": "Thu, 23 Apr 2020 11:33:53 GMT"
        },
        {
          "version": "1.8.0",
          "pubDate": "Thu, 23 Apr 2020 11:33:40 GMT"
        },
        {
          "version": "1.4.0",
          "pubDate": "Thu, 23 Apr 2020 11:32:11 GMT"
        },
        {
          "version": "1.0.2",
          "pubDate": "Thu, 23 Apr 2020 11:30:34 GMT"
        },
        {
          "version": "4.1.0",
          "pubDate": "Mon, 03 Mar 2025 18:00:06 GMT"
        }
      ],
      "relevance": 1.5
    },
    {
      "id": "hl7.fhir.r2.core",
      "name": "hl7.fhir.r2.core",
      "description": "",
      "url": "https://packages.simplifier.net/hl7.fhir.r2.core/1.0.2",
      "Author": "Martijn Harthoorn",
      "fhir_version": "1",
      "Latest_Version": "1.0.2",
      "version_count": 1,
      "all_versions": [
        {
          "version": "1.0.2",
          "pubDate": "Mon, 18 Nov 2019 16:06:05 GMT"
        }
      ],
      "relevance": 1.5
    }
    // ... (additional packages truncated for brevity)
  ],
  "total": 76,
  "last_cached_timestamp": "2025-05-12T09:29:55.653596",
  "fetch_failed": false,
  "is_fetching": false
}
```

This response lists IGs matching the query `core`, including their metadata and relevance scores. The `total` field indicates the number of matching IGs, and cache status fields provide information about the last sync.

### List Profiles Response

**Request**:
```
GET /igs/hl7.fhir.au.core/profiles?version=1.1.0-preview
```

**Response** (`response_Get Profiles.json`):
```json
[
  {
    "name": "AUCoreAllergyIntolerance",
    "description": "This profile sets minimum expectations for an AllergyIntolerance resource to record, search, and fetch allergies/adverse reactions associated with a patient. It is based on the [AU Base Allergy Intolerance](http://build.fhir.org/ig/hl7au/au-fhir-base/StructureDefinition-au-allergyintolerance.html) profile and identifies the *additional* mandatory core elements, extensions, vocabularies and value sets that **SHALL** be present in the AllergyIntolerance resource when conforming to this profile. It provides the floor for standards development for specific uses cases in an Australian context.",
    "version": "1.1.0-preview",
    "url": "http://hl7.org.au/fhir/core/StructureDefinition/au-core-allergyintolerance"
  },
  {
    "name": "AUCoreBloodPressure",
    "description": "This profile sets minimum expectations for an Observation resource to record, search, and fetch blood pressure observations with standard coding and units of measure. It is based on the [FHIR Blood Pressure Profile](http://hl7.org/fhir/R4/bp.html) and identifies the *additional* mandatory core elements, extensions, vocabularies and value sets that **SHALL** be present in the Observation resource when conforming to this profile. It provides the floor for standards development for specific uses cases in an Australian context.",
    "version": "1.1.0-preview",
    "url": "http://hl7.org.au/fhir/core/StructureDefinition/au-core-bloodpressure"
  },
  {
    "name": "AUCoreBodyHeight",
    "description": "This profile sets minimum expectations for an Observation resource to record, search, and fetch body height observations with standard coding and units of measure. It is based on the [FHIR Body Height Profile](http://hl7.org/fhir/R4/bodyheight.html) and identifies the *additional* mandatory core elements, extensions, vocabularies and value sets that **SHALL** be present in the Observation resource when conforming to this profile. It provides the floor for standards development for specific uses cases in an Australian context.",
    "version": "1.1.0-preview",
    "url": "http://hl7.org.au/fhir/core/StructureDefinition/au-core-bodyheight"
  }
  // ... (additional profiles truncated for brevity)
]
```

This response lists profiles within the `hl7.fhir.au.core` IG (version `1.1.0-preview`), including their names, descriptions, versions, and URLs.

### Get Profile Response

**Request**:
```
GET /igs/hl7.fhir.au.core/profiles/AUCoreAllergyIntolerance?version=1.1.0-preview&include_narrative=true
```

**Response** (`response_get structure def.json`):
```json
{
  "resource": {
    "resourceType": "StructureDefinition",
    "id": "au-core-allergyintolerance",
    "text": {
      "status": "extensions",
      "div": "<div xmlns=\"http://www.w3.org/1999/xhtml\"><p class=\"res-header-id\"><b>Generated Narrative: StructureDefinition au-core-allergyintolerance</b></p><a name=\"au-core-allergyintolerance\"> </a><a name=\"hcau-core-allergyintolerance\"> </a><a name=\"au-core-allergyintolerance-en-AU\"> </a><table border=\"0\" cellpadding=\"0\" cellspacing=\"0\" style=\"border: 0px #F0F0F0 solid; font-size: 11px; font-family: verdana; vertical-align: top;\"><tr style=\"border: 1px #F0F0F0 solid; font-size: 11px; font-family: verdana; vertical-align: top\"><th style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; padding-top: 3px; padding-bottom: 3px\" class=\"hierarchy\"><a href=\"https://build.fhir.org/ig/FHIR/ig-guidance/readingIgs.html#table-views\" title=\"The logical name of the element\">Name</a></th><th style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; padding-top: 3px; padding-bottom: 3px\" class=\"hierarchy\"><a href=\"https://build.fhir.org/ig/FHIR/ig-guidance/readingIgs.html#table-views\" title=\"Information about the use of the element\">Flags</a></th><th style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; padding-top: 3px; padding-bottom: 3px\" class=\"hierarchy\"><a href=\"https://build.fhir.org/ig/FHIR/ig-guidance/readingIgs.html#table-views\" title=\"Minimum and Maximum # of times the element can appear in the instance\">Card.</a></th><th style=\"width: 100px\" class=\"hierarchy\"><a href=\"https://build.fhir.org/ig/FHIR/ig-guidance/readingIgs.html#table-views\" title=\"Reference to the type of the element\">Type</a></th><th style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; padding-top: 3px; padding-bottom: 3px\" class=\"hierarchy\"><a href=\"https://build.fhir.org/ig/FHIR/ig-guidance/readingIgs.html#table-views\" title=\"Additional information about the element\">Description & Constraints</a><span style=\"float: right\"><a href=\"https://build.fhir.org/ig/FHIR/ig-guidance/readingIgs.html#table-views\" title=\"Legend for this format\"><img src=\"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH3goXBCwdPqAP0wAAAldJREFUOMuNk0tIlFEYhp9z/vE2jHkhxXA0zJCMitrUQlq4lnSltEqCFhFG2MJFhIvIFpkEWaTQqjaWZRkp0g26URZkTpbaaOJkDqk10szoODP//7XIMUe0elcfnPd9zsfLOYplGrpRwZaqTtw3K7PtGem7Q6FoidbGgqHVy/HRb669R+56zx7eRV1L31JGxYbBtjKK93cxeqfyQHbehkZbUkK20goELEuIzEd+dHS+qz/Y8PTSif0FnGkbiwcAjHaU1+QWOptFiyCLp/LnKptpqIuXHx6rbR26kJcBX3yLgBfnd7CxwJmflpP2wUg0HIAoUUpZBmKzELGWcN8nAr6Gpu7tLU/CkwAaoKTWRSQyt89Q8w6J+oVQkKnBoblH7V0PPvUOvDYXfopE/SJmALsxnVm6LbkotrUtNowMeIrVrBcBpaMmdS0j9df7abpSuy7HWehwJdt1lhVwi/J58U5beXGAF6c3UXLycw1wdFklArBn87xdh0ZsZtArghBdAA3+OEDVubG4UEzP6x1FOWneHh2VDAHBAt80IbdXDcesNoCvs3E5AFyNSU5nbrDPZpcUEQQTFZiEVx+51fxMhhyJEAgvlriadIJZZksRuwBYMOPBbO3hePVVqgEJhFeUuFLhIPkRP6BQLIBrmMenujm/3g4zc398awIe90Zb5A1vREALqneMcYgP/xVQWlG+Ncu5vgwwlaUNx+3799rfe96u9K0JSDXcOzOTJg4B6IgmXfsygc7/Bvg9g9E58/cDVmGIBOP/zT8Bz1zqWqpbXIsd0O9hajXfL6u4BaOS6SeWAAAAAElFTkSuQmCC\" alt=\"doco\" style=\"background-color: inherit\"/></a></span></th></tr><tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: white\"><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck1.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_resource.png\" alt=\".\" style=\"background-color: white; background-color: inherit\" title=\"Resource\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance\">AllergyIntolerance</a><a name=\"AllergyIntolerance\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">0</span><span style=\"opacity: 0.5\">..</span><span style=\"opacity: 0.5\">*</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a href=\"http://hl7.org.au/fhir/5.1.0-preview/StructureDefinition-au-allergyintolerance.html\">AUBaseAllergyIntolerance</a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">An allergy or intolerance statement in an Australian healthcare context</span></td></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: #F7F7F7\"><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck10.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_element.gif\" alt=\".\" style=\"background-color: #F7F7F7; background-color: inherit\" title=\"Element\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance.clinicalStatus\">clinicalStatus</a><a name=\"AllergyIntolerance.clinicalStatus\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"padding-left: 3px; padding-right: 3px; color: white; background-color: red\" title=\"This element has obligations and must be supported\">SO</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">0</span><span style=\"opacity: 0.5\">..</span><span style=\"opacity: 0.5\">1</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a style=\"opacity: 0.5\" href=\"http://hl7.org/fhir/R4/datatypes.html#CodeableConcept\">CodeableConcept</a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">active | inactive | resolved</span><table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Obligations</b></td><td style=\"font-size: 11px\"><b>Actor</b></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: populate-if-known\">populate-if-known</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-responder.html\">AU Core Responder</a></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: no-error\">no-error</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-requester.html\">AU Core Requester</a></td></tr></table></td></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: white\"><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck10.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_element.gif\" alt=\".\" style=\"background-color: white; background-color: inherit\" title=\"Element\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance.verificationStatus\">verificationStatus</a><a name=\"AllergyIntolerance.verificationStatus\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"padding-left: 3px; padding-right: 3px; color: white; background-color: red\" title=\"This element has obligations and must be supported\">SO</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">0</span><span style=\"opacity: 0.5\">..</span><span style=\"opacity: 0.5\">1</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a style=\"opacity: 0.5\" href=\"http://hl7.org/fhir/R4/datatypes.html#CodeableConcept\">CodeableConcept</a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">unconfirmed | confirmed | refuted | entered-in-error</span><table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Obligations</b></td><td style=\"font-size: 11px\"><b>Actor</b></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: populate-if-known\">populate-if-known</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-responder.html\">AU Core Responder</a></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: no-error\">no-error</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-requester.html\">AU Core Requester</a></td></tr></table></td></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: #F7F7F7\"><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck10.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_element.gif\" alt=\".\" style=\"background-color: #F7F7F7; background-color: inherit\" title=\"Element\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance.code\">code</a><a name=\"AllergyIntolerance.code\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"padding-left: 3px; padding-right: 3px; color: white; background-color: red\" title=\"This element has obligations and must be supported\">SO</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\">1..<span style=\"opacity: 0.5\">1</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a style=\"opacity: 0.5\" href=\"http://hl7.org/fhir/R4/datatypes.html#CodeableConcept\">CodeableConcept</a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">Code that identifies the allergy or intolerance</span><br/><span style=\"font-weight:bold\">Binding: </span><a href=\"https://tx.ontoserver.csiro.au/fhir/ValueSet/560e1d07-b12a-4b03-bfe2-eabc77ada87a\" title=\"https://healthterminologies.gov.au/fhir/ValueSet/indicator-hypersensitivity-intolerance-to-substance-2\">Indicator of Hypersensitivity or Intolerance to Substance <img src=\"external.png\" alt=\".\"/></a> (<a href=\"http://hl7.org/fhir/R4/terminologies.html#extensible\" title=\"To be conformant, the concept in this element SHALL be from the specified value set if any of the codes within the value set can apply to the concept being communicated.  If the value set does not cover the concept (based on human review), alternate codings (or, data type allowing, text) may be included instead.\">extensible</a>)<table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Additional Bindings</b></td><td style=\"font-size: 11px\">Purpose</td></tr><tr><td style=\"font-size: 11px\"><a href=\"https://tx.ontoserver.csiro.au/fhir/ValueSet/adverse-reaction-substances-and-negated-findings-1\" title=\"https://healthterminologies.gov.au/fhir/ValueSet/adverse-reaction-substances-and-negated-findings-1\">Adverse Reaction Substances and Negated Findings <img src=\"external.png\" alt=\".\"/></a></td><td style=\"font-size: 11px\"><span title=\"Unknown code for purpose\">candidate</span></td></tr></table><table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Obligations</b></td><td style=\"font-size: 11px\"><b>Actor</b></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: populate-if-known\">populate-if-known</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-responder.html\">AU Core Responder</a></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: no-error\">no-error</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-requester.html\">AU Core Requester</a></td></tr></table></td></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: white\"><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck10.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_reference.png\" alt=\".\" style=\"background-color: white; background-color: inherit\" title=\"Reference to another Resource\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance.patient\">patient</a><a name=\"AllergyIntolerance.patient\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"padding-left: 3px; padding-right: 3px; color: white; background-color: red\" title=\"This element has obligations and must be supported\">SO</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">1</span><span style=\"opacity: 0.5\">..</span><span style=\"opacity: 0.5\">1</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a href=\"http://hl7.org/fhir/R4/references.html\">Reference</a>(<a href=\"StructureDefinition-au-core-patient.html\">AU Core Patient</a>)</td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">Who the sensitivity is for</span><table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Obligations</b></td><td style=\"font-size: 11px\"><b>Actor</b></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: populate-if-known\">populate-if-known</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-responder.html\">AU Core Responder</a></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: no-error\">no-error</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-requester.html\">AU Core Requester</a></td></tr></table></td></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: #F7F7F7\"><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck11.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_choice.gif\" alt=\".\" style=\"background-color: #F7F7F7; background-color: inherit\" title=\"Choice of Types\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance.onset[x]\">onset[x]</a><a name=\"AllergyIntolerance.onset_x_\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"padding-left: 3px; padding-right: 3px; color: white; background-color: red\" title=\"This element has obligations and must be supported\">SO</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">0</span><span style=\"opacity: 0.5\">..</span><span style=\"opacity: 0.5\">1</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">When allergy or intolerance was identified</span><table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Obligations</b></td><td style=\"font-size: 11px\"><b>Actor</b></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: populate-if-known\">populate-if-known</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-responder.html\">AU Core Responder</a></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: no-error\">no-error</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-requester.html\">AU Core Requester</a></td></tr></table></td></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: white\"><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck110.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vline.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_primitive.png\" alt=\".\" style=\"background-color: white; background-color: inherit\" title=\"Primitive Data Type\" class=\"hierarchy\"/> <span title=\"Base StructureDefinition for dateTime Type: A date, date-time or partial date (e.g. just year or year + month).  If hours and minutes are specified, a time zone SHALL be populated. The format is a union of the schema types gYear, gYearMonth, date and dateTime. Seconds must be provided due to schema type constraints but may be zero-filled and may be ignored.                 Dates SHALL be valid dates.\">onsetDateTime</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a href=\"http://hl7.org/fhir/R4/datatypes.html#dateTime\">dateTime</a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: #F7F7F7\"><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck110.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vline.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_datatype.gif\" alt=\".\" style=\"background-color: #F7F7F7; background-color: inherit\" title=\"Data Type\" class=\"hierarchy\"/> <span title=\"Base StructureDefinition for Age Type: A duration of time during which an organism (or a process) has existed.\">onsetAge</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a href=\"http://hl7.org/fhir/R4/datatypes.html#Age\">Age</a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: white\"><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck110.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vline.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_datatype.gif\" alt=\".\" style=\"background-color: white; background-color: inherit\" title=\"Data Type\" class=\"hierarchy\"/> <span title=\"Base StructureDefinition for Period Type: A time period defined by a start and end date and optionally time.\">onsetPeriod</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a href=\"http://hl7.org/fhir/R4/datatypes.html#Period\">Period</a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: #F7F7F7\"><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck100.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vline.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin_end.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_datatype.gif\" alt=\".\" style=\"background-color: #F7F7F7; background-color: inherit\" title=\"Data Type\" class=\"hierarchy\"/> <span title=\"Base StructureDefinition for Range Type: A set of ordered Quantities defined by a low and high limit.\">onsetRange</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a href=\"http://hl7.org/fhir/R4/datatypes.html#Range\">Range</a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"/></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: white\"><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck01.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin_end.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_element.gif\" alt=\".\" style=\"background-color: white; background-color: inherit\" title=\"Element\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance.reaction\">reaction</a><a name=\"AllergyIntolerance.reaction\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"padding-left: 3px; padding-right: 3px; color: white; background-color: red\" title=\"This element has obligations and must be supported\">SO</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">0</span><span style=\"opacity: 0.5\">..</span><span style=\"opacity: 0.5\">*</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a style=\"opacity: 0.5\" href=\"http://hl7.org/fhir/R4/datatypes.html#BackboneElement\">BackboneElement</a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">Adverse Reaction Events linked to exposure to substance</span><table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Obligations</b></td><td style=\"font-size: 11px\"><b>Actor</b></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: populate-if-known\">populate-if-known</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-responder.html\">AU Core Responder</a></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: no-error\">no-error</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-requester.html\">AU Core Requester</a></td></tr></table></td></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: #F7F7F7\"><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck010.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_blank.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_element.gif\" alt=\".\" style=\"background-color: #F7F7F7; background-color: inherit\" title=\"Element\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance.reaction.manifestation\">manifestation</a><a name=\"AllergyIntolerance.reaction.manifestation\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"padding-left: 3px; padding-right: 3px; color: white; background-color: red\" title=\"This element has obligations and must be supported\">SO</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">1</span><span style=\"opacity: 0.5\">..</span><span style=\"opacity: 0.5\">*</span></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a style=\"opacity: 0.5\" href=\"http://hl7.org/fhir/R4/datatypes.html#CodeableConcept\">CodeableConcept</a></td><td style=\"vertical-align: top; text-align : left; background-color: #F7F7F7; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">Clinical symptoms/signs associated with the Event</span><table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Obligations</b></td><td style=\"font-size: 11px\"><b>Actor</b></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: populate-if-known\">populate-if-known</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-responder.html\">AU Core Responder</a></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: no-error\">no-error</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-requester.html\">AU Core Requester</a></td></tr></table></td></tr>\r\n<tr style=\"border: 0px #F0F0F0 solid; padding:0px; vertical-align: top; background-color: white\"><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px; white-space: nowrap; background-image: url(tbl_bck000.png)\" class=\"hierarchy\"><img src=\"tbl_spacer.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_blank.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"tbl_vjoin_end.png\" alt=\".\" style=\"background-color: inherit\" class=\"hierarchy\"/><img src=\"icon_element.gif\" alt=\".\" style=\"background-color: white; background-color: inherit\" title=\"Element\" class=\"hierarchy\"/> <a href=\"StructureDefinition-au-core-allergyintolerance-definitions.html#AllergyIntolerance.reaction.severity\">severity</a><a name=\"AllergyIntolerance.reaction.severity\"> </a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"padding-left: 3px; padding-right: 3px; color: white; background-color: red\" title=\"This element has obligations and must be supported\">SO</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">0</span><span style=\"opacity: 0.5\">..</span><span style=\"opacity: 0.5\">1</span></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><a style=\"opacity: 0.5\" href=\"http://hl7.org/fhir/R4/datatypes.html#code\">code</a></td><td style=\"vertical-align: top; text-align : left; background-color: white; border: 0px #F0F0F0 solid; padding:0px 4px 0px 4px\" class=\"hierarchy\"><span style=\"opacity: 0.5\">mild | moderate | severe (of event as a whole)</span><table class=\"grid\"><tr><td style=\"font-size: 11px\"><b>Obligations</b></td><td style=\"font-size: 11px\"><b>Actor</b></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: populate-if-known\">populate-if-known</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-responder.html\">AU Core Responder</a></td></tr><tr><td style=\"font-size: 11px\"><b>SHALL</b>:<span title=\"obligation: no-error\">no-error</span></td><td style=\"font-size: 11px; opacity: 0.5;\"><a href=\"ActorDefinition-au-core-actor-requester.html\">AU Core Requester</a></td></tr></table></td></tr>\r\n<tr><td colspan=\"5\" class=\"hierarchy\"><br/><a href=\"https://build.fhir.org/ig/FHIR/ig-guidance/readingIgs.html#table-views\" title=\"Legend for this format\"><img src=\"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH3goXBCwdPqAP0wAAAldJREFUOMuNk0tIlFEYhp9z/vE2jHkhxXA0zJCMitrUQlq4lnSltEqCFhFG2MJFhIvIFpkEWaTQqjaWZRkp0g26URZkTpbaaOJkDqk10szoODP//7XIMUe0elcfnPd9zsfLOYplGrpRwZaqTtw3K7PtGem7Q6FoidbGgqHVy/HRb669R+56zx7eRV1L31JGxYbBtjKK93cxeqfyQHbehkZbUkK20goELEuIzEd+dHS+qz/Y8PTSif0FnGkbiwcAjHaU1+QWOptFiyCLp/LnKptpqIuXHx6rbR26kJcBX3yLgBfnd7CxwJmflpP2wUg0HIAoUUpZBmKzELGWcN8nAr6Gpu7tLU/CkwAaoKTWRSQyt89Q8w6J+oVQkKnBoblH7V0PPvUOvDYXfopE/SJmALsxnVm6LbkotrUtNowMeIrVrBcBpaMmdS0j9df7abpSuy7HWehwJdt1lhVwi/J58U5beXGAF6c3UXLycw1wdFklArBn87xdh0ZsZtArghBdAA3+OEDVubG4UEzP6x1FOWneHh2VDAHBAt80IbdXDcesNoCvs3E5AFyNSU5nbrDPZpcUEQQTFZiEVx+51fxMhhyJEAgvlriadIJZZksRuwBYMOPBbO3hePVVqgEJhFeUuFLhIPkRP6BQLIBrmMenujm/3g4zc398awIe90Zb5A1vREALqneMcYgP/xVQWlG+Ncu5vgwwlaUNx+3799rfe96u9K0JSDXcOzOTJg4B6IgmXfsygc7/Bvg9g9E58/cDVmGIBOP/zT8Bz1zqWqpbXIsd0O9hajXfL6u4BaOS6SeWAAAAAElFTkSuQmCC\" alt=\"doco\" style=\"background-color: inherit\"/> Documentation for this format</a></td></tr></table></div>"
    },
    "extension": [
      {
        "url": "http://hl7.org/fhir/StructureDefinition/structuredefinition-fmm",
        "valueInteger": 2
      },
      {
        "url": "http://hl7.org/fhir/StructureDefinition/structuredefinition-standards-status",
        "valueCode": "trial-use",
        "_valueCode": {
          "extension": [
            {
              "url": "http://hl7.org/fhir/StructureDefinition/structuredefinition-conformance-derivedFrom",
              "valueCanonical": "http://hl7.org.au/fhir/core/ImplementationGuide/hl7.fhir.au.core"
            }
          ]
        }
      }
    ],
    "url": "http://hl7.org.au/fhir/core/StructureDefinition/au-core-allergyintolerance",
    "version": "1.1.0-preview",
    "name": "AUCoreAllergyIntolerance",
    "title": "AU Core AllergyIntolerance",
    "status": "active",
    "date": "2025-03-06T07:19:11+00:00",
    "publisher": "HL7 Australia",
    "contact": [
      {
        "name": "HL7 Australia FHIR Work Group",
        "telecom": [
          {
            "system": "url",
            "value": "https://confluence.hl7.org/display/HAFWG",
            "use": "work"
          }
        ]
      }
    ],
    "description": "This profile sets minimum expectations for an AllergyIntolerance resource to record, search, and fetch allergies/adverse reactions associated with a patient. It is based on the [AU Base Allergy Intolerance](http://build.fhir.org/ig/hl7au/au-fhir-base/StructureDefinition-au-allergyintolerance.html) profile and identifies the *additional* mandatory core elements, extensions, vocabularies and value sets that **SHALL** be present in the AllergyIntolerance resource when conforming to this profile. It provides the floor for standards development for specific uses cases in an Australian context.",
    "jurisdiction": [
      {
        "coding": [
          {
            "system": "urn:iso:std:iso:3166",
            "code": "AU"
          }
        ]
      }
    ],
    "copyright": "Used by permission of HL7 International, all rights reserved Creative Commons License. HL7 Australia© 2022+; Licensed Under Creative Commons No Rights Reserved.",
    "fhirVersion": "4.0.1",
    // ... (additional fields truncated for brevity)
    "snapshot": {
      // Snapshot details omitted for brevity
    },
    "differential": {
      // Differential details omitted for brevity
    }
  }
}
```

This response provides the `AUCoreAllergyIntolerance` StructureDefinition with the narrative included. To strip the narrative, set `include_narrative=false`, and the `text` element will be `null`.

## Testing IggyAPI

You can test IggyAPI using `curl`, Postman, or the Swagger UI.

### Using `curl`

1. **Search for IGs**:
   ```bash
   curl -X GET "http://localhost:8000/igs/search?query=au%20core&search_type=semantic" -H "accept: application/json"
   ```
   Look for `hl7.fhir.au.core` in the response.

2. **List Profiles**:
   ```bash
   curl -X GET "http://localhost:8000/igs/hl7.fhir.au.core/profiles?version=1.1.0-preview" -H "accept: application/json"
   ```
   Verify that profiles like `AUCoreAllergyIntolerance` are listed.

3. **Get a Profile with Narrative**:
   ```bash
   curl -X GET "http://localhost:8000/igs/hl7.fhir.au.core/profiles/AUCoreAllergyIntolerance?version=1.1.0-preview&include_narrative=true" -H "accept: application/json"
   ```
   Check that the `text` element contains narrative content.

4. **Get a Profile without Narrative**:
   ```bash
   curl -X GET "http://localhost:8000/igs/hl7.fhir.au.core/profiles/AUCoreAllergyIntolerance?version=1.1.0-preview&include_narrative=false" -H "accept: application/json"
   ```
   Confirm that the `text` element is `null`.

5. **Refresh Cache**:
   ```bash
   curl -X POST "http://localhost:8000/refresh-cache" -H "accept: application/json"
   ```
   Verify the response includes the updated `last_refresh` timestamp.

### Using Swagger UI

- Navigate to `http://localhost:8000/docs`.
- Use the interactive interface to execute the above requests and inspect responses.

### Using Postman

- Import the OpenAPI specification (`http://localhost:8000/openapi.json`) into Postman.
- Create requests for each endpoint and test with the parameters shown above.

## Implementation Details

- **Framework**: Built with FastAPI for high performance and automatic OpenAPI documentation.
- **Database**: Uses SQLite to cache IG metadata, with tables `cached_packages` and `registry_cache_info`.
- **Caching**:
  - IG metadata is cached in memory and persisted to SQLite.
  - The cache is refreshed every 8 hours or on demand via `/refresh-cache`.
  - Profiles are cached in memory to reduce redundant downloads.
- **Search Functionality**: Uses SpaCy for semantic and string similarity matching, with rapidfuzz as a fallback for string searches.
- **Narrative Stripping**: The `include_narrative` parameter in the `get_profile` endpoint removes the `text` element from StructureDefinitions when set to `false`.
- **Dependencies**:
  - `requests` and `feedparser` for fetching IG metadata from registries.
  - `sqlalchemy` for database operations.
  - `rapidfuzz` for fuzzy search functionality.
  - `spacy` for semantic and string similarity searches.
  - `tenacity` for retrying failed registry requests.
- **Error Handling**:
  - Returns HTTP 400 for invalid input (e.g., malformed IG names).
  - Returns HTTP 404 for missing IGs or profiles.
  - Returns HTTP 500 for server errors, with detailed logs.

## Contributing

Contributions to IggyAPI are welcome! To contribute:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-feature`).
3. Commit your changes (`git commit -m "Add my feature"`).
4. Push to the branch (`git push origin feature/my-feature`).
5. Open a pull request with a detailed description of your changes.

Please ensure your code follows PEP 8 style guidelines and includes appropriate tests.

## License

IggyAPI is licensed under the MIT License. See the `LICENSE` file for details.
