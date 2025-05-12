from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Optional, Dict
import feedparser
import requests
import json
import os
import logging
from sqlalchemy import create_engine, Column, String, Integer, JSON, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta, timezone
from tenacity import retry, stop_after_attempt, wait_fixed
import re
import tarfile
import io
from rapidfuzz import process, fuzz
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app with lifespan handler
app = FastAPI(title="FHIR IG API", description="API for searching and retrieving FHIR Implementation Guides and StructureDefinitions")

# SQLite Database Setup with increased timeout
Base = declarative_base()
DATABASE_URL = "sqlite:///instance/fhir_igs.db?timeout=60"  # Increase timeout to 60 seconds
os.makedirs("instance", exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

with engine.connect() as connection:
    connection.execute(text("PRAGMA journal_mode=WAL;"))
    connection.execute(text("PRAGMA busy_timeout=60000;"))
    logger.info("Enabled WAL mode and set busy timeout for SQLite")

# Database Models
class CachedPackage(Base):
    __tablename__ = "cached_packages"
    package_name = Column(String, primary_key=True)
    version = Column(String)
    latest_official_version = Column(String)
    author = Column(String)
    description = Column(String)
    fhir_version = Column(String)
    url = Column(String)
    canonical = Column(String)
    all_versions = Column(JSON)
    dependencies = Column(JSON)
    version_count = Column(Integer)
    last_updated = Column(String)
    latest_version = Column(String)

class RegistryCacheInfo(Base):
    __tablename__ = "registry_cache_info"
    id = Column(Integer, primary_key=True)
    last_fetch_timestamp = Column(DateTime(timezone=True), nullable=True)

Base.metadata.create_all(bind=engine)

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

# Global variables
refresh_status = {
    "last_refresh": None,
    "errors": []
}

app_config = {
    "MANUAL_PACKAGE_CACHE": None,
    "MANUAL_CACHE_TIMESTAMP": None,
    "FETCH_IN_PROGRESS": False,
    "PROFILE_CACHE": {}  # Cache for profiles: {ig_name#version: [ProfileMetadata]}
}

# Constants from FHIRFLARE
FHIR_REGISTRY_BASE_URL = "https://packages.fhir.org"

def safe_parse_version(v_str):
    """Parse version strings, handling FHIR-specific suffixes."""
    if not v_str or not isinstance(v_str, str):
        return "0.0.0a0"
    v_str_norm = v_str.lower()
    base_part = v_str_norm.split('-', 1)[0] if '-' in v_str_norm else v_str_norm
    suffix = v_str_norm.split('-', 1)[1] if '-' in v_str_norm else None
    if re.match(r'^\d+(\.\d+)*$', base_part):
        if suffix in ['dev', 'snapshot', 'ci-build', 'snapshot1', 'snapshot3', 'draft-final']:
            return f"{base_part}a0"
        elif suffix in ['draft', 'ballot', 'preview', 'ballot2']:
            return f"{base_part}b0"
        elif suffix and suffix.startswith('rc'):
            return f"{base_part}rc{''.join(filter(str.isdigit, suffix)) or '0'}"
        return base_part
    return "0.0.0a0"

def compare_versions(v1, v2):
    """Compare two version strings, handling FHIR-specific formats."""
    v1_parts = v1.split('.')
    v2_parts = v2.split('.')
    for i in range(max(len(v1_parts), len(v2_parts))):
        p1 = v1_parts[i] if i < len(v1_parts) else '0'
        p2 = v2_parts[i] if i < len(v2_parts) else '0'
        p1_num, p1_suffix = re.match(r'(\d+)([a-zA-Z0-9]*)$', p1).groups() if re.match(r'^\d+[a-zA-Z0-9]*$', p1) else (p1, '')
        p2_num, p2_suffix = re.match(r'(\d+)([a-zA-Z0-9]*)$', p2).groups() if re.match(r'^\d+[a-zA-Z0-9]*$', p2) else (p2, '')
        if int(p1_num) != int(p2_num):
            return int(p1_num) > int(p2_num)
        if p1_suffix != p2_suffix:
            if not p1_suffix:
                return True
            if not p2_suffix:
                return False
            return p1_suffix > p2_suffix
    return False

def get_additional_registries():
    """Fetch additional FHIR IG registries from the master feed."""
    feed_registry_url = 'https://raw.githubusercontent.com/FHIR/ig-registry/master/package-feeds.json'
    feeds = []
    try:
        response = requests.get(feed_registry_url, timeout=15)
        response.raise_for_status()
        data = json.loads(response.text)
        feeds = [{'name': feed['name'], 'url': feed['url']} for feed in data.get('feeds', []) if 'name' in feed and 'url' in feed and feed['url'].startswith(('http://', 'https://'))]
        feeds = [feed for feed in feeds if feed['url'] != 'https://fhir.kl.dk/package-feed.xml']
        logger.info(f"Fetched {len(feeds)} registries from {feed_registry_url}")
    except Exception as e:
        logger.error(f"Failed to fetch registries: {str(e)}")
        refresh_status["errors"].append(f"Failed to fetch registries from {feed_registry_url}: {str(e)}")
    return feeds

@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def fetch_feed(feed):
    """Fetch and parse a single feed, handling both JSON and RSS/Atom."""
    logger.info(f"Fetching feed: {feed['name']} from {feed['url']}")
    entries = []
    try:
        response = requests.get(feed['url'], timeout=30)
        response.raise_for_status()
        content_type = response.headers.get('content-type', '').lower()
        logger.debug(f"Response content-type: {content_type}, content: {response.text[:200]}")

        if 'application/json' in content_type or feed['url'].endswith('.json'):
            try:
                data = response.json()
                packages = data.get('packages', data.get('entries', []))
                for pkg in packages:
                    if not isinstance(pkg, dict):
                        continue
                    versions = pkg.get('versions', [])
                    if versions:
                        entries.append(pkg)
                    else:
                        pkg['versions'] = [{"version": pkg.get('version', ''), "pubDate": pkg.get('pubDate', 'NA')}]
                        entries.append(pkg)
                logger.info(f"Fetched {len(entries)} packages from JSON feed {feed['name']}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error for {feed['name']}: {str(e)}")
                refresh_status["errors"].append(f"JSON parse error for {feed['name']} at {feed['url']}: {str(e)}")
                raise
        elif 'xml' in content_type or 'rss' in content_type or 'atom' in content_type or feed['url'].endswith(('.rss', '.atom', '.xml')) or 'text/plain' in content_type:
            try:
                feed_data = feedparser.parse(response.text)
                if not feed_data.entries:
                    logger.warning(f"No entries found in feed {feed['name']}")
                for entry in feed_data.entries:
                    title = entry.get('title', '')
                    pkg_name = ''
                    version = ''
                    if '#' in title:
                        pkg_name, version = title.split('#', 1)
                    else:
                        pkg_name = title
                        version = entry.get('version', '')
                    if not pkg_name:
                        pkg_name = entry.get('id', '') or entry.get('summary', '')
                    if not pkg_name:
                        continue
                    package = {
                        'name': pkg_name,
                        'version': version,
                        'author': entry.get('author', 'NA'),
                        'fhirVersion': entry.get('fhir_version', ['NA'])[0] or 'NA',
                        'url': entry.get('link', 'unknown'),
                        'canonical': entry.get('canonical', ''),
                        'dependencies': entry.get('dependencies', []),
                        'pubDate': entry.get('published', entry.get('pubdate', 'NA')),
                        'registry': feed['url'],
                        'versions': [{"version": version, "pubDate": entry.get('published', entry.get('pubdate', 'NA'))}]
                    }
                    entries.append(package)
                logger.info(f"Fetched {len(entries)} entries from RSS/Atom feed {feed['name']}")
            except Exception as e:
                logger.error(f"RSS/Atom parse error for {feed['name']}: {str(e)}")
                refresh_status["errors"].append(f"RSS/Atom parse error for {feed['name']} at {feed['url']}: {str(e)}")
                raise
        else:
            logger.error(f"Unknown content type for {feed['name']}: {content_type}")
            refresh_status["errors"].append(f"Unknown content type for {feed['name']} at {feed['url']}: {content_type}")
            raise ValueError(f"Unknown content type: {content_type}")

        return entries
    except requests.RequestException as e:
        logger.error(f"Request error for {feed['name']}: {str(e)}")
        refresh_status["errors"].append(f"Request error for {feed['name']} at {feed['url']}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error for {feed['name']}: {str(e)}")
        refresh_status["errors"].append(f"Unexpected error for {feed['name']} at {feed['url']}: {str(e)}")
        raise

def normalize_package_data(entries, registry_url):
    """Normalize package data, grouping by name and aggregating versions."""
    logger.info("Starting normalization of package data")
    packages_grouped = defaultdict(list)
    skipped_raw_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            skipped_raw_count += 1
            logger.warning(f"Skipping raw package entry, not a dict: {entry}")
            continue
        raw_name = entry.get('name') or entry.get('title') or ''
        if not isinstance(raw_name, str):
            raw_name = str(raw_name)
        name_part = raw_name.split('#', 1)[0].strip().lower()
        if name_part:
            packages_grouped[name_part].append(entry)
        else:
            if not entry.get('id'):
                skipped_raw_count += 1
                logger.warning(f"Skipping raw package entry, no name or id: {entry}")
    logger.info(f"Initial grouping: {len(packages_grouped)} unique package names found. Skipped {skipped_raw_count} raw entries.")

    normalized_list = []
    skipped_norm_count = 0
    total_entries_considered = 0

    for name_key, entries in packages_grouped.items():
        total_entries_considered += len(entries)
        latest_absolute_data = None
        latest_official_data = None
        latest_absolute_ver = "0.0.0a0"
        latest_official_ver = "0.0.0a0"
        all_versions = []
        package_name_display = name_key

        processed_versions = set()
        for package_entry in entries:
            versions_list = package_entry.get('versions', [])
            for version_info in versions_list:
                if isinstance(version_info, dict) and 'version' in version_info:
                    version_str = version_info.get('version', '')
                    if version_str and version_str not in processed_versions:
                        all_versions.append({
                            "version": version_str,
                            "pubDate": version_info.get('pubDate', 'NA')
                        })
                        processed_versions.add(version_str)

        processed_entries = []
        for package_entry in entries:
            version_str = None
            raw_name_entry = package_entry.get('name') or package_entry.get('title') or ''
            if not isinstance(raw_name_entry, str):
                raw_name_entry = str(raw_name_entry)
            version_keys = ['version', 'latestVersion']
            for key in version_keys:
                val = package_entry.get(key)
                if isinstance(val, str) and val:
                    version_str = val.strip()
                    break
                elif isinstance(val, list) and val and isinstance(val[0], str) and val[0]:
                    version_str = val[0].strip()
                    break
            if not version_str and '#' in raw_name_entry:
                parts = raw_name_entry.split('#', 1)
                if len(parts) == 2 and parts[1]:
                    version_str = parts[1].strip()

            if not version_str:
                logger.warning(f"Skipping entry for {raw_name_entry}: no valid version found. Entry: {package_entry}")
                skipped_norm_count += 1
                continue

            version_str = version_str.strip()
            current_display_name = str(raw_name_entry).split('#')[0].strip()
            if current_display_name and current_display_name != name_key:
                package_name_display = current_display_name

            entry_with_version = package_entry.copy()
            entry_with_version['version'] = version_str
            processed_entries.append(entry_with_version)

            try:
                current_ver = safe_parse_version(version_str)
                if latest_absolute_data is None or compare_versions(current_ver, latest_absolute_ver):
                    latest_absolute_ver = current_ver
                    latest_absolute_data = entry_with_version

                if re.match(r'^\d+\.\d+\.\d+(?:-[a-zA-Z0-9\.]+)?$', version_str):
                    if latest_official_data is None or compare_versions(current_ver, latest_official_ver):
                        latest_official_ver = current_ver
                        latest_official_data = entry_with_version
            except Exception as comp_err:
                logger.error(f"Error comparing version '{version_str}' for package '{package_name_display}': {comp_err}", exc_info=True)

        if latest_absolute_data:
            final_absolute_version = latest_absolute_data.get('version', 'unknown')
            final_official_version = latest_official_data.get('version') if latest_official_data else None

            author_raw = latest_absolute_data.get('author') or latest_absolute_data.get('publisher') or 'NA'
            if isinstance(author_raw, dict):
                author = author_raw.get('name', str(author_raw))
            elif not isinstance(author_raw, str):
                author = str(author_raw)
            else:
                author = author_raw

            fhir_version_str = 'NA'
            fhir_keys = ['fhirVersion', 'fhirVersions', 'fhir_version']
            for key in fhir_keys:
                val = latest_absolute_data.get(key)
                if isinstance(val, list) and val and isinstance(val[0], str):
                    fhir_version_str = val[0]
                    break
                elif isinstance(val, str) and val:
                    fhir_version_str = val
                    break

            url_raw = latest_absolute_data.get('url') or latest_absolute_data.get('link') or 'unknown'
            url = str(url_raw) if not isinstance(url_raw, str) else url_raw
            canonical_raw = latest_absolute_data.get('canonical') or url
            canonical = str(canonical_raw) if not isinstance(canonical_raw, str) else canonical_raw

            dependencies_raw = latest_absolute_data.get('dependencies', [])
            dependencies = []
            if isinstance(dependencies_raw, dict):
                dependencies = [{"name": str(dn), "version": str(dv)} for dn, dv in dependencies_raw.items()]
            elif isinstance(dependencies_raw, list):
                for dep in dependencies_raw:
                    if isinstance(dep, str):
                        if '@' in dep:
                            dep_name, dep_version = dep.split('@', 1)
                            dependencies.append({"name": dep_name, "version": dep_version})
                        else:
                            dependencies.append({"name": dep, "version": "N/A"})
                    elif isinstance(dep, dict) and 'name' in dep and 'version' in dep:
                        dependencies.append(dep)

            all_versions.sort(key=lambda x: x.get('pubDate', ''), reverse=True)
            latest_version = final_official_version or final_absolute_version or 'N/A'

            normalized_entry = {
                "package_name": package_name_display,
                "version": final_absolute_version,
                "latest_official_version": final_official_version,
                "author": author.strip(),
                "description": "",
                "fhir_version": fhir_version_str.strip(),
                "url": url.strip(),
                "canonical": canonical.strip(),
                "all_versions": all_versions,
                "dependencies": dependencies,
                "version_count": len(all_versions),
                "last_updated": datetime.utcnow().isoformat(),
                "latest_version": latest_version
            }
            normalized_list.append(normalized_entry)
            if not final_official_version:
                logger.warning(f"No official version found for package '{package_name_display}'. Versions: {[v['version'] for v in all_versions]}")
        else:
            logger.warning(f"No valid entries found to determine details for package name key '{name_key}'. Entries: {entries}")
            skipped_norm_count += len(entries)

    logger.info(f"Normalization complete. Entries considered: {total_entries_considered}, Skipped during norm: {skipped_norm_count}, Unique Packages Found: {len(normalized_list)}")
    normalized_list.sort(key=lambda x: x.get('package_name', '').lower())
    return normalized_list

def cache_packages(normalized_packages, db_session):
    """Cache normalized FHIR Implementation Guide packages in the CachedPackage database."""
    logger.info("Starting to cache packages")
    try:
        batch_size = 10
        for i in range(0, len(normalized_packages), batch_size):
            batch = normalized_packages[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} with {len(batch)} packages")
            for package in batch:
                existing = db_session.query(CachedPackage).filter_by(package_name=package['package_name']).first()
                if existing:
                    existing.version = package['version']
                    existing.latest_official_version = package['latest_official_version']
                    existing.author = package['author']
                    existing.description = package['description']
                    existing.fhir_version = package['fhir_version']
                    existing.url = package['url']
                    existing.canonical = package['canonical']
                    existing.all_versions = package['all_versions']
                    existing.dependencies = package['dependencies']
                    existing.version_count = package['version_count']
                    existing.last_updated = package['last_updated']
                    existing.latest_version = package['latest_version']
                else:
                    new_package = CachedPackage(**package)
                    db_session.add(new_package)
            db_session.commit()
            logger.info(f"Cached {len(batch)} packages in batch {i//batch_size + 1}")
        logger.info(f"Successfully cached {len(normalized_packages)} packages in CachedPackage.")
    except Exception as error:
        db_session.rollback()
        logger.error(f"Error caching packages: {error}")
        refresh_status["errors"].append(f"Error caching packages: {str(error)}")
        raise
    logger.info("Finished caching packages")

def should_sync_packages(db_session):
    """Check if the database is empty or data is older than 4 hours."""
    logger.info("Checking if sync is needed")
    try:
        package_count = db_session.query(CachedPackage).count()
        if package_count == 0:
            logger.info("Database is empty, triggering sync")
            return True

        latest_package = db_session.query(CachedPackage).order_by(CachedPackage.last_updated.desc()).first()
        if not latest_package or not latest_package.last_updated:
            logger.info("No valid last_updated timestamp, triggering sync")
            return True

        try:
            last_updated = datetime.fromisoformat(latest_package.last_updated.replace('Z', '+00:00'))
            time_diff = datetime.utcnow() - last_updated
            if time_diff.total_seconds() > 4 * 3600:
                logger.info(f"Data is {time_diff.total_seconds()/3600:.2f} hours old, triggering sync")
                return True
            else:
                logger.info(f"Data is {time_diff.total_seconds()/3600:.2f} hours old, using current dataset")
                return False
        except ValueError:
            logger.warning("Invalid last_updated format, triggering sync")
            return True
    except Exception as e:
        logger.error(f"Error checking sync status: {str(e)}")
        return True

def sync_packages():
    """Syndicate package metadata from RSS feeds and package registries."""
    logger.info("Starting RSS feed refresh")
    global refresh_status, app_config
    refresh_status["errors"] = []
    temp_packages = []
    app_config["FETCH_IN_PROGRESS"] = True

    db = SessionLocal()
    try:
        registries = get_additional_registries()
        if not registries:
            logger.error("No registries fetched. Cannot proceed with package syndication.")
            refresh_status["errors"].append("No registries fetched. Syndication aborted.")
            app_config["FETCH_IN_PROGRESS"] = False
            return

        for feed in registries:
            if not feed['url'].startswith(('http://', 'https://')):
                logger.warning(f"Skipping invalid feed URL: {feed['url']}")
                continue
            try:
                entries = fetch_feed(feed)
                normalized_packages = normalize_package_data(entries, feed["url"])
                temp_packages.extend(normalized_packages)
            except Exception as e:
                logger.error(f"Failed to process feed {feed['name']}: {str(e)}")
                refresh_status["errors"].append(f"Failed to process feed {feed['name']}: {str(e)}")

        now_ts = datetime.utcnow().isoformat()
        app_config["MANUAL_PACKAGE_CACHE"] = temp_packages
        app_config["MANUAL_CACHE_TIMESTAMP"] = now_ts

        logger.info("Updating database with fetched packages")
        try:
            db.query(CachedPackage).delete()
            db.flush()
            logger.info("Cleared existing data in cached_packages table")
            cache_packages(temp_packages, db)
            timestamp_info = db.query(RegistryCacheInfo).first()
            if timestamp_info:
                timestamp_info.last_fetch_timestamp = datetime.fromisoformat(now_ts.replace('Z', '+00:00'))
            else:
                timestamp_info = RegistryCacheInfo(last_fetch_timestamp=datetime.fromisoformat(now_ts.replace('Z', '+00:00')))
                db.add(timestamp_info)
            db.commit()
            refresh_status["last_refresh"] = now_ts
            logger.info(f"Refreshed database with {len(temp_packages)} packages")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update database: {str(e)}")
            refresh_status["errors"].append(f"Database update failed: {str(e)}")
            raise
    finally:
        app_config["FETCH_IN_PROGRESS"] = False
        db.close()
        logger.info("Closed database session after sync")
    logger.info("Finished syncing packages")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler for FastAPI startup and shutdown."""
    os.makedirs("instance", exist_ok=True)
    db = SessionLocal()
    try:
        db_path = "instance/fhir_igs.db"
        if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
            logger.info("Database file exists and has data. Checking if sync is needed...")
            if should_sync_packages(db):
                logger.info("Data is outdated or missing, triggering sync")
                sync_packages()
            else:
                logger.info("Using existing dataset at startup")
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
            logger.info("Database file does not exist or is empty, triggering sync")
            sync_packages()
        yield
    finally:
        db.close()
        logger.info("Closed database session after lifespan shutdown")

app.lifespan = lifespan

@app.get("/igs/search", response_model=SearchResponse)
async def search_igs(query: str = ''):
    """Search for IGs with embedded logic from FHIRFLARE's search_and_import and api_search_packages."""
    logger.info(f"Searching IGs with query: {query}")
    db = SessionLocal()
    try:
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
            filtered_packages = [
                pkg for pkg in normalized_packages
                if isinstance(pkg, dict) and (
                    query.lower() in pkg.get('package_name', '').lower() or
                    query.lower() in pkg.get('author', '').lower()
                )
            ]
            logger.debug(f"Filtered {len(normalized_packages)} cached packages down to {len(filtered_packages)} for term '{query}'")
        else:
            filtered_packages = normalized_packages
            logger.debug(f"No search term provided, using all {len(filtered_packages)} cached packages.")

        logger.info("Starting fuzzy search")
        search_data = [(pkg['package_name'], pkg, 'name') for pkg in filtered_packages]
        search_data += [(pkg['description'], pkg, 'description') for pkg in filtered_packages if pkg['description']]
        results = process.extract(query.lower(), [item[0].lower() for item in search_data], limit=100, scorer=fuzz.partial_ratio, score_cutoff=70)
        logger.info(f"Fuzzy search completed with {len(results)} results")

        logger.info("Building response packages")
        packages_to_display = []
        seen_names = set()
        for matched_text, score, index in results:
            pkg = search_data[index][1]
            source = search_data[index][2]
            if pkg['package_name'] not in seen_names:
                seen_names.add(pkg['package_name'])
                adjusted_score = score * 1.5 if source == 'name' else score * 0.8
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
                    "relevance": adjusted_score / 100.0
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

def download_package(ig_name: str, version: str, package: Dict) -> tuple[str, Optional[str]]:
    """Download the .tgz file for the given IG and version, mimicking FHIRFLARE's import_package_and_dependencies."""
    # Create a temporary directory for downloads
    download_dir = "instance/fhir_packages"
    os.makedirs(download_dir, exist_ok=True)
    tgz_filename = f"{ig_name}-{version}.tgz".replace('/', '_')
    tgz_path = os.path.join(download_dir, tgz_filename)

    # Check if package already exists
    if os.path.exists(tgz_path):
        logger.info(f"Package {ig_name}#{version} already exists at {tgz_path}")
        return tgz_path, None

    # Try canonical URL first (most reliable)
    canonical_url = package.get('canonical')
    if canonical_url and canonical_url.endswith(f"{version}/package.tgz"):
        logger.info(f"Attempting to fetch package from canonical URL: {canonical_url}")
        try:
            response = requests.get(canonical_url, stream=True, timeout=30)
            response.raise_for_status()
            with open(tgz_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.info(f"Successfully downloaded {ig_name}#{version} to {tgz_path} using canonical URL")
            return tgz_path, None
        except requests.RequestException as e:
            error_msg = f"Failed to fetch package from canonical URL {canonical_url}: {str(e)}"
            logger.warning(error_msg)

    # Try primary FHIR registry base URL (e.g., https://packages.fhir.org/hl7.fhir.au.core/1.1.0-preview/)
    base_url = f"{FHIR_REGISTRY_BASE_URL}/{ig_name}/{version}/"
    logger.info(f"Attempting to fetch package from FHIR registry base URL: {base_url}")
    try:
        response = requests.get(base_url, stream=True, timeout=30)
        response.raise_for_status()
        # Check if the response is a .tgz file
        content_type = response.headers.get('Content-Type', '')
        content_disposition = response.headers.get('Content-Disposition', '')
        if 'application/x-tar' in content_type or content_disposition.endswith('.tgz') or base_url.endswith('.tgz'):
            with open(tgz_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            logger.info(f"Successfully downloaded {ig_name}#{version} to {tgz_path} using FHIR registry base URL")
            return tgz_path, None
        else:
            error_msg = f"FHIR registry base URL {base_url} did not return a .tgz file (Content-Type: {content_type})"
            logger.warning(error_msg)
    except requests.RequestException as e:
        error_msg = f"Failed to fetch package from FHIR registry base URL {base_url}: {str(e)}"
        logger.warning(error_msg)

    # Fallback: Try FHIR registry with explicit /package.tgz
    tgz_url = f"{FHIR_REGISTRY_BASE_URL}/{ig_name}/{version}/package.tgz"
    logger.info(f"Attempting to fetch package from FHIR registry explicit URL: {tgz_url}")
    try:
        response = requests.get(tgz_url, stream=True, timeout=30)
        response.raise_for_status()
        with open(tgz_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logger.info(f"Successfully downloaded {ig_name}#{version} to {tgz_path} using FHIR registry explicit URL")
        return tgz_path, None
    except requests.RequestException as e:
        error_msg = f"Failed to fetch package from FHIR registry explicit URL {tgz_url}: {str(e)}"
        logger.warning(error_msg)

    # Fallback: Use registry URL (e.g., Simplifier)
    registry_url = package.get('registry', 'https://packages.simplifier.net')
    if registry_url.endswith('/rssfeed'):
        registry_url = registry_url[:-8]
    tgz_url = f"{registry_url}/{ig_name}/{version}/package.tgz"
    logger.info(f"Attempting to fetch package from registry URL: {tgz_url}")
    try:
        response = requests.get(tgz_url, stream=True, timeout=30)
        response.raise_for_status()
        with open(tgz_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logger.info(f"Successfully downloaded {ig_name}#{version} to {tgz_path} using registry URL")
        return tgz_path, None
    except requests.RequestException as e:
        error_msg = f"Failed to fetch package from registry URL {tgz_url}: {str(e)}"
        logger.error(error_msg)
        return None, error_msg

    return None, "All download attempts failed."

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

    # Download the package using updated logic
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
                if member.name.endswith('.json') and 'StructureDefinition' in member.name:
                    f = tar.extractfile(member)
                    if f:
                        resource = json.load(f)
                        if resource.get("resourceType") == "StructureDefinition":
                            profiles.append(ProfileMetadata(
                                name=resource.get("name", ""),
                                description=resource.get("description"),
                                version=resource.get("version"),
                                url=resource.get("url", "")
                            ))
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

    # Extract the specific profile
    try:
        with tarfile.open(tgz_path, mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith('.json'):
                    f = tar.extractfile(member)
                    if f:
                        resource = json.load(f)
                        if (resource.get("resourceType") == "StructureDefinition" and
                            (resource.get("name") == profile_id or resource.get("id") == profile_id or resource.get("url", "").endswith(profile_id))):
                            # Strip narrative if include_narrative is False
                            if not include_narrative:
                                if "text" in resource:
                                    logger.info(f"Stripping narrative from profile {profile_id} for IG {ig_name} (version: {version})")
                                    resource["text"] = None
                            logger.info(f"Successfully retrieved profile {profile_id} for IG {ig_name} (version: {version})")
                            return StructureDefinition(resource=resource)
    except Exception as e:
        logger.error(f"Failed to extract profile {profile_id} from package for IG {ig_name} (version: {version}): {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to extract profile: {str(e)}")

    logger.error(f"Profile {profile_id} not found in package for IG {ig_name} (version: {version})")
    raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found in IG '{ig_name}' (version: {version}).")

@app.get("/status", response_model=RefreshStatus)
async def get_refresh_status():
    """Return the status of the last refresh."""
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
async def refresh_cache():
    """Force a refresh of the package cache."""
    logger.info("Forcing cache refresh via API")
    sync_packages()
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)