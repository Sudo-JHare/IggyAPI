from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Optional, Dict
import spacy
from rapidfuzz import fuzz
import logging
import re
import tarfile
import json
from datetime import datetime, timedelta
import asyncio

# Import from core
from core import (
    SessionLocal, CachedPackage, RegistryCacheInfo,
    refresh_status, app_config, sync_packages,
    should_sync_packages, download_package,
    logger, FHIR_REGISTRY_BASE_URL
)

# Configure logging to capture more details
logging.getLogger().setLevel(logging.DEBUG)  # Set root logger to DEBUG
logging.getLogger("uvicorn").setLevel(logging.DEBUG)  # Ensure uvicorn logs are captured
logging.getLogger("uvicorn.access").setLevel(logging.DEBUG)  # Capture access logs

# Load SpaCy model
try:
    nlp = spacy.load("en_core_web_md")
    logger.info("SpaCy model 'en_core_web_md' loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load SpaCy model: {str(e)}")
    raise RuntimeError("SpaCy model 'en_core_web_md' is required for search functionality. Please install it.")

# FastAPI app
app = FastAPI(title="IggyAPI", description="API for searching and retrieving FHIR Implementation Guides and StructureDefinitions")
logger.debug("FastAPI app initialized.")

# Pydantic Models for Responses
class VersionEntry(BaseModel):
    version: str
    pubDate: str

class IGSearchResult(BaseModel):
    id: str
    name: str
    description: Optional[str]
    url: Optional[str]
    Author: Optional[str]
    fhir_version: Optional[str]
    Latest_Version: Optional[str]
    version_count: int
    all_versions: List[VersionEntry]
    relevance: float

class SearchResponse(BaseModel):
    packages: List[IGSearchResult]
    total: int
    last_cached_timestamp: Optional[str]
    fetch_failed: bool
    is_fetching: bool

class ProfileMetadata(BaseModel):
    name: str
    description: Optional[str]
    version: Optional[str]
    url: str

class StructureDefinition(BaseModel):
    resource: dict

class RefreshStatus(BaseModel):
    last_refresh: Optional[str]
    package_count: int
    errors: List[str]

# Global variable to track the last refresh time
last_refresh_time = datetime.utcnow()

async def background_cache_refresh(db):
    """Run a cache refresh and update in-memory cache and database upon completion."""
    global last_refresh_time
    logger.info("Starting background cache refresh")
    try:
        sync_packages()  # This updates app_config["MANUAL_PACKAGE_CACHE"] and the database
        last_refresh_time = datetime.utcnow()  # Update the last refresh time
        logger.info(f"Background cache refresh completed successfully at {last_refresh_time.isoformat()}")
    except Exception as e:
        logger.error(f"Background cache refresh failed: {str(e)}")
        refresh_status["errors"].append(f"Background cache refresh failed: {str(e)}")
    finally:
        db.close()
        logger.info("Closed database session after background cache refresh")

async def scheduled_cache_refresh():
    """Scheduler to run cache refresh every 8 hours after the last refresh."""
    global last_refresh_time
    while True:
        # Calculate time since last refresh
        time_since_last_refresh = datetime.utcnow() - last_refresh_time
        # Calculate how long to wait until the next 8-hour mark
        wait_seconds = max(0, (8 * 3600 - time_since_last_refresh.total_seconds()))
        logger.info(f"Next scheduled cache refresh in {wait_seconds / 3600:.2f} hours")
        await asyncio.sleep(wait_seconds)
        # Create a new database session for the refresh task
        db = SessionLocal()
        await background_cache_refresh(db)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for FastAPI startup and shutdown."""
    logger.debug("Lifespan handler starting.")
    os.makedirs("instance", exist_ok=True)
    db = SessionLocal()
    try:
        db_path = "instance/fhir_igs.db"
        # Always load existing data into memory on startup, regardless of age
        if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
            logger.info("Database file exists and has data. Loading into memory...")
            cached_packages = db.query(CachedPackage).all()
            normalized_packages = []
            for pkg in cached_packages:
                pkg_data = {
                    "package_name": pkg.package_name,
                    "version": pkg.version,
                    "latest_official_version": pkg.latest_official_version,
                    "author": pkg.author,
                    "description": pkg.description,
                    "fhir_version": pkg.fhir_version,
                    "url": pkg.url,
                    "canonical": pkg.canonical,
                    "all_versions": pkg.all_versions,
                    "dependencies": pkg.dependencies,
                    "version_count": pkg.version_count,
                    "last_updated": pkg.last_updated,
                    "latest_version": pkg.latest_version
                }
                normalized_packages.append(pkg_data)
            app_config["MANUAL_PACKAGE_CACHE"] = normalized_packages
            db_timestamp_info = db.query(RegistryCacheInfo).first()
            db_timestamp = db_timestamp_info.last_fetch_timestamp if db_timestamp_info else None
            app_config["MANUAL_CACHE_TIMESTAMP"] = db_timestamp.isoformat() if db_timestamp else datetime.utcnow().isoformat()
            logger.info(f"Loaded {len(normalized_packages)} packages into in-memory cache from database.")
        else:
            logger.info("Database file does not exist or is empty, initializing empty cache")
            app_config["MANUAL_PACKAGE_CACHE"] = []
            app_config["MANUAL_CACHE_TIMESTAMP"] = datetime.utcnow().isoformat()

        # Check if data is older than 8 hours or missing, and trigger a background refresh if needed
        should_refresh = False
        if app_config["MANUAL_PACKAGE_CACHE"]:
            latest_package = db.query(CachedPackage).order_by(CachedPackage.last_updated.desc()).first()
            if not latest_package or not latest_package.last_updated:
                logger.info("No valid last_updated timestamp, triggering background refresh")
                should_refresh = True
            else:
                try:
                    last_updated = datetime.fromisoformat(latest_package.last_updated.replace('Z', '+00:00'))
                    time_diff = datetime.utcnow() - last_updated
                    if time_diff.total_seconds() > 8 * 3600:  # 8 hours
                        logger.info(f"Data is {time_diff.total_seconds()/3600:.2f} hours old, triggering background refresh")
                        should_refresh = True
                    else:
                        logger.info(f"Data is {time_diff.total_seconds()/3600:.2f} hours old, no background refresh needed")
                except ValueError:
                    logger.warning("Invalid last_updated format, triggering background refresh")
                    should_refresh = True
        else:
            logger.info("No packages in cache, triggering background refresh")
            should_refresh = True

        # Start background refresh if needed
        if should_refresh:
            # Create a new database session for the background task
            background_db = SessionLocal()
            asyncio.create_task(background_cache_refresh(background_db))

        # Start the scheduler to run every 8 hours after the last refresh
        asyncio.create_task(scheduled_cache_refresh())

        logger.info("Lifespan startup completed, yielding control to FastAPI.")
        yield
    finally:
        db.close()
        logger.info("Closed database session after lifespan shutdown")

app.lifespan = lifespan

@app.get("/igs/search", response_model=SearchResponse)
async def search_igs(query: str = '', search_type: str = 'semantic'):
    """
    Search for Implementation Guides (IGs) using the specified search type.

    Args:
        query (str, optional): The search term to filter IGs by name or author (e.g., 'au core').
        search_type (str, optional): The type of search to perform. Options are:
            - 'semantic': Uses SpaCy for semantic similarity (default).
            - 'string': Uses SpaCy for token-based string similarity, with a fallback to rapidfuzz for exact/near-exact matches.

    Returns:
        SearchResponse: A response containing a list of matching IGs, their metadata, and cache status.

    Raises:
        HTTPException: If the search_type is invalid or an error occurs during search.
    """
    logger.info(f"Searching IGs with query: {query}, search_type: {search_type}")
    db = SessionLocal()
    try:
        # Validate search_type
        valid_search_types = ['semantic', 'string']
        if search_type not in valid_search_types:
            logger.error(f"Invalid search_type: {search_type}. Must be one of {valid_search_types}.")
            raise HTTPException(status_code=400, detail=f"Invalid search_type: {search_type}. Must be one of {valid_search_types}.")

        in_memory_packages = app_config["MANUAL_PACKAGE_CACHE"]
        in_memory_timestamp = app_config["MANUAL_CACHE_TIMESTAMP"]
        db_timestamp_info = db.query(RegistryCacheInfo).first()
        db_timestamp = db_timestamp_info.last_fetch_timestamp if db_timestamp_info else None
        logger.debug(f"DB Timestamp: {db_timestamp}, In-Memory Timestamp: {in_memory_timestamp}")

        normalized_packages = None
        fetch_failed_flag = False
        display_timestamp = None
        is_fetching = False

        fetch_in_progress = app_config["FETCH_IN_PROGRESS"]
        if fetch_in_progress and in_memory_packages is not None:
            normalized_packages = in_memory_packages
            display_timestamp = in_memory_timestamp
            fetch_failed_flag = len(refresh_status["errors"]) > 0
            app_config["FETCH_IN_PROGRESS"] = False
        elif in_memory_packages is not None:
            logger.info(f"Using in-memory cached package list from {in_memory_timestamp}.")
            normalized_packages = in_memory_packages
            display_timestamp = in_memory_timestamp
            fetch_failed_flag = len(refresh_status["errors"]) > 0
        else:
            cached_packages = db.query(CachedPackage).all()
            if cached_packages:
                logger.info(f"Loading {len(cached_packages)} packages from CachedPackage table.")
                normalized_packages = []
                for pkg in cached_packages:
                    pkg_data = {
                        "package_name": pkg.package_name,
                        "version": pkg.version,
                        "latest_official_version": pkg.latest_official_version,
                        "author": pkg.author,
                        "description": pkg.description,
                        "fhir_version": pkg.fhir_version,
                        "url": pkg.url,
                        "canonical": pkg.canonical,
                        "all_versions": pkg.all_versions,
                        "dependencies": pkg.dependencies,
                        "version_count": pkg.version_count,
                        "last_updated": pkg.last_updated,
                        "latest_version": pkg.latest_version
                    }
                    normalized_packages.append(pkg_data)
                app_config["MANUAL_PACKAGE_CACHE"] = normalized_packages
                app_config["MANUAL_CACHE_TIMESTAMP"] = db_timestamp.isoformat() if db_timestamp else datetime.utcnow().isoformat()
                display_timestamp = app_config["MANUAL_CACHE_TIMESTAMP"]
                fetch_failed_flag = len(refresh_status["errors"]) > 0
                logger.info(f"Loaded {len(normalized_packages)} packages into in-memory cache from database.")
            else:
                logger.info("No packages found in CachedPackage table. Fetching from registries...")
                is_fetching = True
                app_config["FETCH_IN_PROGRESS"] = True
                sync_packages()
                normalized_packages = app_config["MANUAL_PACKAGE_CACHE"]
                display_timestamp = app_config["MANUAL_CACHE_TIMESTAMP"]
                fetch_failed_flag = len(refresh_status["errors"]) > 0

        if not isinstance(normalized_packages, list):
            logger.error(f"normalized_packages is not a list (type: {type(normalized_packages)}). Using empty list.")
            normalized_packages = []
            fetch_failed_flag = True

        logger.info("Filtering packages based on query")
        if query:
            # Split the query into individual words
            query_words = query.lower().split()
            filtered_packages = [
                pkg for pkg in normalized_packages
                if isinstance(pkg, dict) and (
                    all(word in pkg.get('package_name', '').lower() for word in query_words) or
                    all(word in pkg.get('author', '').lower() for word in query_words)
                )
            ]
            logger.debug(f"Filtered {len(normalized_packages)} cached packages down to {len(filtered_packages)} for terms '{query_words}'")
        else:
            filtered_packages = normalized_packages
            logger.debug(f"No search term provided, using all {len(filtered_packages)} cached packages.")

        logger.info(f"Starting search with search_type: {search_type}")
        results = []
        query_doc = nlp(query.lower())  # Process the query with SpaCy

        if search_type == 'semantic':
            # Semantic similarity search using SpaCy's word embeddings
            for pkg in filtered_packages:
                name = pkg['package_name']
                description = pkg['description'] if pkg['description'] else ''
                author = pkg['author'] if pkg['author'] else ''
                # Combine fields for a comprehensive semantic search
                combined_text = f"{name} {description} {author}".lower()
                doc = nlp(combined_text)
                similarity = query_doc.similarity(doc)  # Compute semantic similarity
                if similarity > 0.3:  # Lowered threshold for semantic similarity
                    logger.info(f"Semantic match: {name}, similarity: {similarity}")
                    results.append((name, pkg, 'combined', similarity))
                else:
                    # Fallback to rapidfuzz for exact/near-exact string matching
                    name_score = fuzz.partial_ratio(query.lower(), name.lower())
                    desc_score = fuzz.partial_ratio(query.lower(), description.lower()) if description else 0
                    author_score = fuzz.partial_ratio(query.lower(), author.lower()) if author else 0
                    max_score = max(name_score, desc_score, author_score)
                    if max_score > 70:  # Threshold for rapidfuzz
                        source = 'name' if max_score == name_score else ('description' if max_score == desc_score else 'author')
                        logger.info(f"Rapidfuzz fallback in semantic mode: {name}, source: {source}, score: {max_score}")
                        results.append((name, pkg, source, max_score / 100.0))
        else:
            # String similarity search
            # First try SpaCy's token-based similarity
            for pkg in filtered_packages:
                name = pkg['package_name']
                description = pkg['description'] if pkg['description'] else ''
                author = pkg['author'] if pkg['author'] else ''
                combined_text = f"{name} {description} {author}".lower()
                doc = nlp(combined_text)
                # Use token-based similarity for string matching
                token_similarity = query_doc.similarity(doc)  # Still using similarity but focusing on token overlap
                if token_similarity > 0.7:  # Higher threshold for token similarity
                    logger.info(f"SpaCy token match: {name}, similarity: {token_similarity}")
                    results.append((name, pkg, 'combined', token_similarity))
                else:
                    # Fallback to rapidfuzz for exact/near-exact string matching
                    name_score = fuzz.partial_ratio(query.lower(), name.lower())
                    desc_score = fuzz.partial_ratio(query.lower(), description.lower()) if description else 0
                    author_score = fuzz.partial_ratio(query.lower(), author.lower()) if author else 0
                    max_score = max(name_score, desc_score, author_score)
                    if max_score > 70:  # Threshold for rapidfuzz
                        source = 'name' if max_score == name_score else ('description' if max_score == desc_score else 'author')
                        logger.info(f"Rapidfuzz match: {name}, source: {source}, score: {max_score}")
                        results.append((name, pkg, source, max_score / 100.0))

        logger.info(f"Search completed with {len(results)} results")

        logger.info("Building response packages")
        packages_to_display = []
        seen_names = set()
        for matched_text, pkg, source, score in sorted(results, key=lambda x: x[3], reverse=True):
            if pkg['package_name'] not in seen_names:
                seen_names.add(pkg['package_name'])
                adjusted_score = score * 1.5 if source in ['name', 'combined'] else score * 0.8
                logger.info(f"Matched IG: {pkg['package_name']} (source: {source}, score: {score}, adjusted: {adjusted_score})")
                packages_to_display.append({
                    "id": pkg['package_name'],
                    "name": pkg['package_name'],
                    "description": pkg['description'],
                    "url": pkg['url'],
                    "Author": pkg['author'],
                    "fhir_version": pkg['fhir_version'],
                    "Latest_Version": pkg['latest_version'],
                    "version_count": pkg['version_count'],
                    "all_versions": pkg['all_versions'] or [],
                    "relevance": adjusted_score
                })

        packages_to_display.sort(key=lambda x: x['relevance'], reverse=True)
        total = len(packages_to_display)
        logger.info(f"Total packages to display: {total}")

        logger.info("Returning search response")
        return SearchResponse(
            packages=packages_to_display,
            total=total,
            last_cached_timestamp=display_timestamp,
            fetch_failed=fetch_failed_flag,
            is_fetching=is_fetching
        )
    finally:
        db.close()
        logger.info("Closed database session after search")
#-----------------------------------------------------------------------------OLD
# @app.get("/igs/{ig_id}/profiles", response_model=List[ProfileMetadata])
# async def list_profiles(ig_id: str, version: Optional[str] = None):
#     """List StructureDefinition profiles in the specified IG, optionally for a specific version."""
#     logger.info(f"Listing profiles for IG: {ig_id}, version: {version}")

#     # Parse ig_id for version if it includes a '#'
#     ig_name = ig_id
#     if '#' in ig_id:
#         parts = ig_id.split('#', 1)
#         ig_name = parts[0]
#         if version and parts[1] != version:
#             logger.warning(f"Version specified in ig_id ({parts[1]}) conflicts with version parameter ({version}). Using version parameter.")
#         else:
#             version = parts[1]
#         logger.info(f"Parsed ig_id: name={ig_name}, version={version}")

#     # Validate ig_name
#     if not ig_name or not re.match(r'^[a-zA-Z0-9\.\-_]+$', ig_name):
#         logger.error(f"Invalid IG name: {ig_name}")
#         raise HTTPException(status_code=400, detail="Invalid IG name. Use format like 'hl7.fhir.au.core'.")

#     # Validate version if provided
#     if version and not re.match(r'^[a-zA-Z0-9\.\-_]+$', version):
#         logger.error(f"Invalid version: {version}")
#         raise HTTPException(status_code=400, detail="Invalid version format. Use format like '1.1.0-preview'.")

#     # Check if profiles are cached
#     cache_key = f"{ig_name}#{version if version else 'latest'}"
#     if cache_key in app_config["PROFILE_CACHE"]:
#         logger.info(f"Returning cached profiles for IG {ig_name} (version: {version if version else 'latest'})")
#         return app_config["PROFILE_CACHE"][cache_key]

#     # Fetch package metadata from cache
#     packages = app_config["MANUAL_PACKAGE_CACHE"]
#     if not packages:
#         logger.error("Package cache is empty. Please refresh the cache using /refresh-cache.")
#         raise HTTPException(status_code=500, detail="Package cache is empty. Please refresh the cache.")

#     # Find the package
#     package = None
#     for pkg in packages:
#         if pkg['package_name'].lower() == ig_name.lower():
#             package = pkg
#             break

#     if not package:
#         logger.error(f"IG {ig_name} not found in cached packages.")
#         raise HTTPException(status_code=404, detail=f"IG '{ig_name}' not found.")

#     # Determine the version to fetch
#     if version:
#         target_version = None
#         for ver_entry in package['all_versions']:
#             if ver_entry['version'] == version:
#                 target_version = ver_entry['version']
#                 break
#         if not target_version:
#             logger.error(f"Version {version} not found for IG {ig_name}.")
#             raise HTTPException(status_code=404, detail=f"Version '{version}' not found for IG '{ig_name}'.")
#     else:
#         target_version = package['latest_version']
#         version = target_version
#         logger.info(f"No version specified, using latest version: {target_version}")

#     # Download the package
#     tgz_path, error = download_package(ig_name, version, package)
#     if not tgz_path:
#         logger.error(f"Failed to download package for IG {ig_name} (version: {version}): {error}")
#         if "404" in error:
#             raise HTTPException(status_code=404, detail=f"Package for IG '{ig_name}' (version: {version}) not found.")
#         raise HTTPException(status_code=500, detail=f"Failed to fetch package: {error}")

#     # Extract profiles from the .tgz file
#     profiles = []
#     try:
#         with tarfile.open(tgz_path, mode="r:gz") as tar:
#             for member in tar.getmembers():
#                 if member.name.endswith('.json') and 'StructureDefinition' in member.name:
#                     f = tar.extractfile(member)
#                     if f:
#                         resource = json.load(f)
#                         if resource.get("resourceType") == "StructureDefinition":
#                             profiles.append(ProfileMetadata(
#                                 name=resource.get("name", ""),
#                                 description=resource.get("description"),
#                                 version=resource.get("version"),
#                                 url=resource.get("url", "")
#                             ))
#     except Exception as e:
#         logger.error(f"Failed to extract profiles from package for IG {ig_name} (version: {version}): {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Failed to extract profiles: {str(e)}")

#     # Cache the profiles
#     app_config["PROFILE_CACHE"][cache_key] = profiles
#     logger.info(f"Cached {len(profiles)} profiles for IG {ig_name} (version: {version})")

#     logger.info(f"Found {len(profiles)} profiles in IG {ig_name} (version: {version})")
#     return profiles
#----------------------------------------------------------------------------end
@app.get("/igs/{ig_id}/profiles", response_model=List[ProfileMetadata])
async def list_profiles(ig_id: str, version: Optional[str] = None):
    """List StructureDefinition profiles in the specified IG, optionally for a specific version."""
    logger.info(f"Listing profiles for IG: {ig_id}, version: {version}")

    # Parse ig_id for version if it includes a '#'
    ig_name = ig_id
    if '#' in ig_id:
        parts = ig_id.split('#', 1)
        ig_name = parts[0]
        if version and parts[1] != version:
            logger.warning(f"Version specified in ig_id ({parts[1]}) conflicts with version parameter ({version}). Using version parameter.")
        else:
            version = parts[1]
        logger.info(f"Parsed ig_id: name={ig_name}, version={version}")

    # Validate ig_name
    if not ig_name or not re.match(r'^[a-zA-Z0-9\.\-_]+$', ig_name):
        logger.error(f"Invalid IG name: {ig_name}")
        raise HTTPException(status_code=400, detail="Invalid IG name. Use format like 'hl7.fhir.au.core'.")

    # Validate version if provided
    if version and not re.match(r'^[a-zA-Z0-9\.\-_]+$', version):
        logger.error(f"Invalid version: {version}")
        raise HTTPException(status_code=400, detail="Invalid version format. Use format like '1.1.0-preview'.")

    # Check if profiles are cached
    cache_key = f"{ig_name}#{version if version else 'latest'}"
    if cache_key in app_config["PROFILE_CACHE"]:
        logger.info(f"Returning cached profiles for IG {ig_name} (version: {version if version else 'latest'})")
        return app_config["PROFILE_CACHE"][cache_key]

    # Fetch package metadata from cache
    packages = app_config["MANUAL_PACKAGE_CACHE"]
    if not packages:
        logger.error("Package cache is empty. Please refresh the cache using /refresh-cache.")
        raise HTTPException(status_code=500, detail="Package cache is empty. Please refresh the cache.")

    # Find the package
    package = None
    for pkg in packages:
        if pkg['package_name'].lower() == ig_name.lower():
            package = pkg
            break

    if not package:
        logger.error(f"IG {ig_name} not found in cached packages.")
        raise HTTPException(status_code=404, detail=f"IG '{ig_name}' not found.")

    # Determine the version to fetch
    if version:
        target_version = None
        for ver_entry in package['all_versions']:
            if ver_entry['version'] == version:
                target_version = ver_entry['version']
                break
        if not target_version:
            logger.error(f"Version {version} not found for IG {ig_name}.")
            raise HTTPException(status_code=404, detail=f"Version '{version}' not found for IG '{ig_name}'.")
    else:
        target_version = package['latest_version']
        version = target_version
        logger.info(f"No version specified, using latest version: {target_version}")

    # Download the package
    tgz_path, error = download_package(ig_name, version, package)
    if not tgz_path:
        logger.error(f"Failed to download package for IG {ig_name} (version: {version}): {error}")
        if "404" in error:
            raise HTTPException(status_code=404, detail=f"Package for IG '{ig_name}' (version: {version}) not found.")
        raise HTTPException(status_code=500, detail=f"Failed to fetch package: {error}")

    # Extract profiles from the .tgz file
    profiles = []
    try:
        with tarfile.open(tgz_path, mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith('.json'):  # Check all JSON files
                    logger.debug(f"Processing file: {member.name}")
                    f = tar.extractfile(member)
                    if f:
                        try:
                            resource = json.load(f)
                            # Check if the resource is a StructureDefinition
                            if resource.get("resourceType") == "StructureDefinition":
                                logger.debug(f"Found StructureDefinition in file: {member.name}")
                                profiles.append(ProfileMetadata(
                                    name=resource.get("name", ""),
                                    description=resource.get("description"),
                                    version=resource.get("version"),
                                    url=resource.get("url", "")
                                ))
                            else:
                                logger.debug(f"File {member.name} is not a StructureDefinition, resourceType: {resource.get('resourceType', 'unknown')}")
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON in file {member.name}: {str(e)}")
                        except Exception as e:
                            logger.warning(f"Error processing file {member.name}: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to extract profiles from package for IG {ig_name} (version: {version}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to extract profiles: {str(e)}")

    # Cache the profiles
    app_config["PROFILE_CACHE"][cache_key] = profiles
    logger.info(f"Cached {len(profiles)} profiles for IG {ig_name} (version: {version})")

    logger.info(f"Found {len(profiles)} profiles in IG {ig_name} (version: {version})")
    return profiles

@app.get("/igs/{ig_id}/profiles/{profile_id}", response_model=StructureDefinition)
async def get_profile(ig_id: str, profile_id: str, version: Optional[str] = None, include_narrative: bool = True):
    """
    Retrieve a specific StructureDefinition from an Implementation Guide (IG).

    This endpoint fetches a specific FHIR StructureDefinition (profile) from the given IG.
    It supports optional version specification and an option to strip the narrative content.

    Args:
        ig_id (str): The ID of the Implementation Guide (e.g., 'hl7.fhir.au.core' or 'hl7.fhir.au.core#1.1.0-preview').
                     If the version is included in the ig_id (after '#'), it takes precedence unless overridden by the version parameter.
        profile_id (str): The ID or name of the profile to retrieve (e.g., 'AUCorePatient').
        version (str, optional): The version of the IG (e.g., '1.1.0-preview'). If not provided and ig_id contains a version,
                                 the version from ig_id is used; otherwise, the latest version is used.
        include_narrative (bool, optional): Whether to include the narrative (`text` element) in the StructureDefinition.
                                            Defaults to True. Set to False to strip the narrative, removing human-readable content.

    Returns:
        StructureDefinition: A dictionary containing the requested StructureDefinition resource.
                             The response includes the `resource` field with the StructureDefinition JSON.
                             If `include_narrative=False`, the `text` element will be set to null.

    Raises:
        HTTPException: 
            - 400: If the IG name, version, or profile ID is invalid.
            - 404: If the IG, version, or profile is not found.
            - 500: If an error occurs during package retrieval or profile extraction.

    Example:
        - GET /igs/hl7.fhir.au.core/profiles/AUCorePatient?version=1.1.0-preview
          Returns the AUCorePatient profile with narrative included.
        - GET /igs/hl7.fhir.au.core/profiles/AUCorePatient?version=1.1.0-preview&include_narrative=false
          Returns the AUCorePatient profile with the narrative (`text` element) stripped.
    """
    logger.info(f"Retrieving profile {profile_id} for IG: {ig_id}, version: {version}, include_narrative: {include_narrative}")

    # Parse ig_id for version if it includes a '#'
    ig_name = ig_id
    if '#' in ig_id:
        parts = ig_id.split('#', 1)
        ig_name = parts[0]
        if version and parts[1] != version:
            logger.warning(f"Version specified in ig_id ({parts[1]}) conflicts with version parameter ({version}). Using version parameter.")
        else:
            version = parts[1]
        logger.info(f"Parsed ig_id: name={ig_name}, version={version}")

    # Validate ig_name
    if not ig_name or not re.match(r'^[a-zA-Z0-9\.\-_]+$', ig_name):
        logger.error(f"Invalid IG name: {ig_name}")
        raise HTTPException(status_code=400, detail="Invalid IG name. Use format like 'hl7.fhir.au.core'.")

    # Validate version if provided
    if version and not re.match(r'^[a-zA-Z0-9\.\-_]+$', version):
        logger.error(f"Invalid version: {version}")
        raise HTTPException(status_code=400, detail="Invalid version format. Use format like '1.1.0-preview'.")

    # Validate profile_id
    if not profile_id or not re.match(r'^[a-zA-Z0-9\.\-_]+$', profile_id):
        logger.error(f"Invalid profile ID: {profile_id}")
        raise HTTPException(status_code=400, detail="Invalid profile ID format.")

    # Check if profiles are cached
    cache_key = f"{ig_name}#{version if version else 'latest'}"
    if cache_key in app_config["PROFILE_CACHE"]:
        logger.info(f"Using cached profiles for IG {ig_name} (version: {version if version else 'latest'})")
        profiles = app_config["PROFILE_CACHE"][cache_key]
        for profile in profiles:
            if profile.name == profile_id or profile.url.endswith(profile_id):
                break
        else:
            logger.error(f"Profile {profile_id} not found in cached profiles for IG {ig_name} (version: {version if version else 'latest'})")
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found in IG '{ig_name}' (version: {version if version else 'latest'}).")
    else:
        profiles = await list_profiles(ig_id, version)

    # Fetch package metadata
    packages = app_config["MANUAL_PACKAGE_CACHE"]
    if not packages:
        logger.error("Package cache is empty. Please refresh the cache using /refresh-cache.")
        raise HTTPException(status_code=500, detail="Package cache is empty. Please refresh the cache.")

    package = None
    for pkg in packages:
        if pkg['package_name'].lower() == ig_name.lower():
            package = pkg
            break

    if not package:
        logger.error(f"IG {ig_name} not found in cached packages.")
        raise HTTPException(status_code=404, detail=f"IG '{ig_name}' not found.")

    # Determine the version to fetch
    if version:
        target_version = None
        for ver_entry in package['all_versions']:
            if ver_entry['version'] == version:
                target_version = ver_entry['version']
                break
        if not target_version:
            logger.error(f"Version {version} not found for IG {ig_name}.")
            raise HTTPException(status_code=404, detail=f"Version '{version}' not found for IG '{ig_name}'.")
    else:
        target_version = package['latest_version']
        version = target_version
        logger.info(f"No version specified, using latest version: {target_version}")

    # Download the package
    tgz_path, error = download_package(ig_name, version, package)
    if not tgz_path:
        logger.error(f"Failed to download package for IG {ig_name} (version: {version}): {error}")
        if "404" in error:
            raise HTTPException(status_code=404, detail=f"Package for IG '{ig_name}' (version: {version}) not found.")
        raise HTTPException(status_code=500, detail=f"Failed to fetch package: {error}")

    # Extract the specific profile from the .tgz file
    profile_resource = None
    try:
        with tarfile.open(tgz_path, mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith('.json') and 'StructureDefinition' in member.name:
                    f = tar.extractfile(member)
                    if f:
                        resource = json.load(f)
                        if resource.get("resourceType") == "StructureDefinition":
                            resource_name = resource.get("name", "")
                            resource_url = resource.get("url", "")
                            if resource_name == profile_id or resource_url.endswith(profile_id):
                                profile_resource = resource
                                break
        if not profile_resource:
            logger.error(f"Profile {profile_id} not found in package for IG {ig_name} (version: {version})")
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found in IG '{ig_name}' (version: {version}).")
    except Exception as e:
        logger.error(f"Failed to extract profile {profile_id} from package for IG {ig_name} (version: {version}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to extract profile: {str(e)}")

    # Strip narrative if requested
    if not include_narrative:
        logger.info(f"Stripping narrative from profile {profile_id}")
        if "text" in profile_resource:
            profile_resource["text"] = None

    logger.info(f"Successfully retrieved profile {profile_id} for IG {ig_name} (version: {version})")
    return StructureDefinition(resource=profile_resource)

@app.get("/status", response_model=RefreshStatus)
async def get_refresh_status():
    """Get the status of the last cache refresh."""
    logger.info("Fetching refresh status")
    db = SessionLocal()
    try:
        package_count = db.query(CachedPackage).count()
        return RefreshStatus(
            last_refresh=refresh_status["last_refresh"],
            package_count=package_count,
            errors=refresh_status["errors"]
        )
    finally:
        db.close()
        logger.info("Closed database session after status check")

@app.post("/refresh-cache", response_model=RefreshStatus)
async def force_refresh_cache():
    """Force a refresh of the IG metadata cache."""
    global last_refresh_time
    logger.info("Forcing cache refresh")
    sync_packages()
    last_refresh_time = datetime.utcnow()  # Update the last refresh time
    logger.info(f"Manual cache refresh completed at {last_refresh_time.isoformat()}")
    db = SessionLocal()
    try:
        package_count = db.query(CachedPackage).count()
        return RefreshStatus(
            last_refresh=refresh_status["last_refresh"],
            package_count=package_count,
            errors=refresh_status["errors"]
        )
    finally:
        db.close()
        logger.info("Closed database session after cache refresh")

# Log that the application is starting
logger.info("IggyAPI application starting up.")