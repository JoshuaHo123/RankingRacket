"""
MascotGO Data Pipeline

This pipeline orchestrates the scraping and collection of college ranking data
from various ranking websites into a unified data table.
"""

from scraper import get_rankings
from typing import List, Dict, Tuple
import pandas as pd
import re
import random
import csv
import os
import difflib

from siteMetadata import get_site_metadata_interactive, get_site_metadata_auto
from urllib.parse import parse_qs, urlparse


ALIAS_CSV_PATH = "AtlasDatabase/data/CollegeAliases.csv"
NAME_PREFERENCES_CSV_PATH = "AtlasDatabase/data/CollegeNamePreferences.csv"
SLUG_PREFERENCES_CSV_PATH = "AtlasDatabase/data/CollegeSlugPreferences.csv"
HISTORICAL_COLLEGES_CSV_PATH = "AtlasDatabase/data/HistoricalUrbanColleges.csv"
COUNTRIES_CSV_PATH = "AtlasDatabase/data/Countries.csv"
STATES_CSV_PATH = "AtlasDatabase/data/States.csv"
_alias_index_loaded = False
_location_suffixes_loaded = False
_alias_by_instname: Dict[str, str] = {}
_alias_by_alias: Dict[str, str] = {}
_alias_by_instname_norm: Dict[str, str] = {}
_alias_by_alias_norm: Dict[str, str] = {}
_alias_by_instname_lower: Dict[str, str] = {}
_alias_by_alias_lower: Dict[str, str] = {}
_instname_source_by_norm: Dict[str, str] = {}
_alias_source_by_norm: Dict[str, str] = {}
_instname_source_by_lower: Dict[str, str] = {}
_alias_source_by_lower: Dict[str, str] = {}
_alias_by_instname_variant: Dict[str, str] = {}
_alias_by_alias_variant: Dict[str, str] = {}
_instname_source_by_variant: Dict[str, str] = {}
_alias_source_by_variant: Dict[str, str] = {}
_alias_by_instname_tokens: Dict[str, str] = {}
_alias_by_alias_tokens: Dict[str, str] = {}
_instname_source_by_tokens: Dict[str, str] = {}
_alias_source_by_tokens: Dict[str, str] = {}
_alias_norm_keys: List[str] = []
_alias_variant_keys: List[str] = []
_alias_token_keys: List[str] = []
_location_suffixes: List[str] = []

FUZZY_CUTOFF = 0.90


def generate_random_list_id() -> str:
    """
    Generate a random 10-digit list ID.
    
    Returns:
        String of 10 random digits
    """
    return ''.join([str(random.randint(0, 9)) for _ in range(10)])


def build_table(url: str) -> pd.DataFrame:
    """
    Build a DataFrame from the rankings scraped from the given URL.
    
    Args:
        url: URL of the rankings page
    """
    rows = _get_rankings_for_url(url, use_browser=True)
    df = pd.DataFrame(rows)
    return df 


def _is_usnews_url(url: str) -> bool:
    domain = urlparse(url).netloc.lower().replace("www.", "")
    return "usnews.com" in domain


def _get_usnews_rankings(url: str, usnews_soft_target: int | None = None) -> List[Dict[str, str]]:
    """
    US News now uses the shared Playwright scraper path.
    This keeps its extractor logic aligned with the rest of the pipeline,
    including the script-data fallbacks in scraper.py.
    """
    kwargs = _get_scrape_kwargs_for_url(url)
    if usnews_soft_target is not None:
        kwargs["usnews_soft_target"] = usnews_soft_target
    return get_rankings(url, use_browser=True, **kwargs)


def _get_rankings_for_url(
    url: str,
    use_browser: bool = True,
    usnews_soft_target: int | None = None,
) -> List[Dict[str, str]]:
    if _is_usnews_url(url):
        return _get_usnews_rankings(url, usnews_soft_target=usnews_soft_target)
    return get_rankings(url, use_browser=use_browser, **_get_scrape_kwargs_for_url(url))


def _get_scrape_kwargs_for_url(url: str) -> Dict[str, object]:
    """
    Return site-specific scrape hints.
    We avoid forcing table parsing globally because most ranking sites are not pure tables.
    """
    domain = urlparse(url).netloc.lower().replace("www.", "")
    path = urlparse(url).path.lower()

    if "forbes.com" in domain:
        if "top-colleges" in path and "/sites/" not in path:
            return {
                "wait_for_selector": "table",
                "table_selector": "table",
            }
        if "value-colleges" in path:
            return {
                "wait_for_selector": "table, article, ol li",
                "table_selector": "table",
            }
        return {
            "wait_for_selector": "article, ol li, h2, h3",
        }
    if "usnews.com" in domain:
        q = parse_qs(urlparse(url).query)
        mode = (q.get("_mode") or [""])[0].lower()
        kwargs: Dict[str, object] = {
            "wait_for_selector": "a[href*='/best-colleges/'], article, [class*='ranking'], table",
            "headless": True,
            "timeout": 60,
        }
        # Table ranking pages have a bounded row count; lower target = less scrolling.
        if mode == "table" or "/rankings/" in path:
            kwargs["usnews_soft_target"] = 400
        else:
            kwargs["usnews_soft_target"] = 900
        return kwargs
    if "princetonreview.com" in domain:
        return {
            "wait_for_selector": "a[href*='/school/'], [class*='ranking'], article",
            "headless": False,
        }
    if "niche.com" in domain:
        return {
            "wait_for_selector": "a[href*='/colleges/'], article, [data-testid*='search-result']",
            "headless": False,
            "timeout": 30,
        }
    if "topuniversities.com" in domain:
        return {
            "wait_for_selector": "tr, [class*='ranking'], [class*='institution']",
        }
    if "timeshighereducation.com" in domain:
        return {
            "wait_for_selector": "tr, [class*='table-row'], [class*='institution']",
            "timeout": 30,
        }
    if "shanghairanking.com" in domain or "arwu.org" in domain:
        return {
            "wait_for_selector": "table, tr",
        }
    if "collegeconsensus.com" in domain:
        return {
            "wait_for_selector": "li, article, [class*='ranking']",
        }
    if "mastersportal.com" in domain:
        return {
            "wait_for_selector": "a[href*='/universities/'], a[href*='/university/'], article",
            "headless": False,
            "timeout": 30,
        }
    return {}


def _infer_year(value: str) -> str:
    """
    Try to infer a 4-digit year from a string.
    Returns empty string if not found.
    """
    if not value:
        return ""
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return match.group(0) if match else ""


def _find_first_value(row: Dict[str, str], candidates: List[str]) -> str:
    for key in row.keys():
        normalized = key.strip().lower()
        for candidate in candidates:
            if candidate in normalized:
                return str(row.get(key, "")).strip()
    return ""


def _parse_rank_value(value: str) -> Tuple[str, bool]:
    """
    Return (rank, is_tied) parsed from a rank string.
    Examples: "T1" -> ("1", True), "1 (tie)" -> ("1", True)
    """
    if not value:
        return ("", False)
    text = str(value).strip()
    is_tied = bool(re.search(r"\btie\b|^t\d+|^t\s*\d+", text, flags=re.IGNORECASE))
    match = re.search(r"\d+", text)
    rank = match.group(0) if match else text
    return (rank, is_tied)


def _normalize_name(value: str) -> str:
    if not value:
        return ""
    text = value.lower().strip()
    text = text.replace("&", "and")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_match_variant(value: str) -> str:
    text = _normalize_name(value)
    if not text:
        return ""
    text = re.sub(r"\bthe\b", " ", text)
    text = re.sub(r"\bst\b", "saint", text)
    text = re.sub(r"\bste\b", "saint", text)
    text = re.sub(r"\bmt\b", "mount", text)
    text = re.sub(r"\buniv\b", "university", text)
    text = re.sub(r"\binst\b", "institute", text)
    text = re.sub(r"\btech\b", "technology", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_sort_key(value: str) -> str:
    normalized = _normalize_match_variant(value)
    if not normalized:
        return ""
    return " ".join(sorted(token for token in normalized.split() if token))


def _generate_match_candidates(value: str) -> List[str]:
    candidates: List[str] = []

    def add(candidate: str) -> None:
        cleaned = str(candidate or "").strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    raw = str(value or "").strip()
    if not raw:
        return candidates

    add(raw)
    add(re.sub(r"\s*\([^)]*\)", "", raw).strip())
    add(re.sub(r"^[Tt]he\s+", "", raw).strip())
    add(_strip_trailing_location(raw))
    return candidates


def _register_match_name(unit_id: str, name: str, source: str) -> None:
    if not unit_id or not name:
        return
    cleaned = str(name).strip()
    if not cleaned:
        return
    normalized = _normalize_name(cleaned)
    lowered = cleaned.lower()
    _alias_by_alias.setdefault(cleaned, unit_id)
    _alias_by_alias_norm.setdefault(normalized, unit_id)
    _alias_by_alias_lower.setdefault(lowered, unit_id)
    _alias_source_by_norm.setdefault(normalized, source)
    _alias_source_by_lower.setdefault(lowered, source)
    variant = _normalize_match_variant(cleaned)
    if variant:
        _alias_by_alias_variant.setdefault(variant, unit_id)
        _alias_source_by_variant.setdefault(variant, source)
    token_key = _token_sort_key(cleaned)
    if token_key:
        _alias_by_alias_tokens.setdefault(token_key, unit_id)
        _alias_source_by_tokens.setdefault(token_key, source)


def _load_location_suffixes() -> None:
    global _location_suffixes_loaded
    if _location_suffixes_loaded:
        return

    suffixes = set()

    if os.path.exists(COUNTRIES_CSV_PATH):
        with open(COUNTRIES_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = str(row.get("Name", "")).strip()
                if name:
                    suffixes.add(name.lower())

    if os.path.exists(STATES_CSV_PATH):
        with open(STATES_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = str(row.get("Name", "")).strip()
                if name:
                    suffixes.add(name.lower())

    _location_suffixes.extend(sorted(suffixes, key=len, reverse=True))
    _location_suffixes_loaded = True


def _strip_trailing_location(value: str) -> str:
    if not value:
        return ""
    _load_location_suffixes()

    text = re.sub(r"\s+", " ", str(value)).strip(" ,")
    school_tokens = ("university", "college", "institute", "school", "academy", "polytechnic")

    changed = True
    while changed and text:
        changed = False
        lower = text.lower()
        for suffix in _location_suffixes:
            if not lower.endswith(suffix):
                continue
            candidate = text[: len(text) - len(suffix)].rstrip(" ,|-")
            candidate_lower = candidate.lower()
            if not candidate:
                continue
            if not any(token in candidate_lower for token in school_tokens):
                continue
            text = candidate
            changed = True
            break

    return text


def _looks_like_ranked_school_name(raw_name: str, url: str) -> bool:
    if not raw_name:
        return False

    text = raw_name.strip()
    lower = text.lower()
    if len(text) < 3 or len(text) > 160:
        return False

    generic_blocked_terms = [
        "scholarship",
        "will you get in",
        "ways to pay for college",
        "featured review",
        "view nearby homes",
        "acceptance rate",
        "net price",
        "overall niche grade",
        "save school",
        "learn more",
        "read more",
        "view all",
        "photos",
        "methodology",
        "best college food",
        "best campus food",
        "best dorms",
        "best colleges",
        "best schools",
        "student body",
        "admissions information",
        "tuition and aid",
        "overview",
    ]
    if any(term in lower for term in generic_blocked_terms):
        return False

    if re.search(r"\$\d[\d,]*", text):
        return False

    if re.fullmatch(r"[a-f][+-]?", lower):
        return False

    domain = urlparse(url).netloc.lower().replace("www.", "")
    if "niche.com" in domain:
        niche_blocked = {
            "will you get in?",
            "ways to pay for college",
            "best college food",
        }
        if lower in niche_blocked:
            return False
    if "usnews.com" in domain:
        if lower.startswith(("here are ", "view all ", "in ")):
            return False
    if "princetonreview.com" in domain:
        if lower.startswith("ranked "):
            return False

    school_tokens = ["university", "college", "institute", "school", "academy", "polytechnic"]
    if any(token in lower for token in school_tokens):
        return True

    if text.isupper() and 2 <= len(text) <= 8:
        return True

    words = text.split()
    if len(words) >= 2 and re.search(r"[A-Za-z]", text):
        weak_noise = ["best", "top", "news", "home", "results", "search", "food", "scholarship"]
        if any(term in lower for term in weak_noise):
            return False
        return True

    return False


def _is_truncated_school_name(raw_name: str) -> bool:
    lower = str(raw_name or "").strip().lower()
    truncated_prefixes = {
        "university of",
        "college of",
        "institute of",
        "school of",
        "academy of",
    }
    if lower in truncated_prefixes:
        return True

    truncated_directionals = (
        "university of north",
        "university of south",
        "university of east",
        "university of west",
        "college of north",
        "college of south",
        "college of east",
        "college of west",
    )
    return lower in truncated_directionals


def _requires_unit_id_match(url: str) -> bool:
    domain = urlparse(url).netloc.lower().replace("www.", "")
    strict_domains = [
        "niche.com",
        "usnews.com",
        "princetonreview.com",
        "mastersportal.com",
        "forbes.com",
        "collegeconsensus.com",
        "shanghairanking.com",
        "arwu.org",
    ]
    return any(site in domain for site in strict_domains)


def _load_alias_index(path: str = ALIAS_CSV_PATH) -> None:
    global _alias_index_loaded
    if _alias_index_loaded:
        return
    if os.path.exists(path):
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                unit_id = str(row.get("UnitId", "")).strip()
                inst_name = str(row.get("InstName", "")).strip()
                alias = str(row.get("Alias", "")).strip()
                if unit_id and inst_name:
                    _alias_by_instname.setdefault(inst_name, unit_id)
                    inst_name_norm = _normalize_name(inst_name)
                    inst_name_lower = inst_name.lower()
                    inst_name_variant = _normalize_match_variant(inst_name)
                    inst_name_tokens = _token_sort_key(inst_name)
                    _alias_by_instname_norm.setdefault(inst_name_norm, unit_id)
                    _alias_by_instname_lower.setdefault(inst_name_lower, unit_id)
                    _instname_source_by_norm.setdefault(inst_name_norm, "CollegeAliases.csv:InstName")
                    _instname_source_by_lower.setdefault(inst_name_lower, "CollegeAliases.csv:InstName")
                    if inst_name_variant:
                        _alias_by_instname_variant.setdefault(inst_name_variant, unit_id)
                        _instname_source_by_variant.setdefault(inst_name_variant, "CollegeAliases.csv:InstName")
                    if inst_name_tokens:
                        _alias_by_instname_tokens.setdefault(inst_name_tokens, unit_id)
                        _instname_source_by_tokens.setdefault(inst_name_tokens, "CollegeAliases.csv:InstName")
                _register_match_name(unit_id, alias, "CollegeAliases.csv:Alias")
    else:
        print(f"  ⚠ Alias CSV not found: {path}")

    if os.path.exists(NAME_PREFERENCES_CSV_PATH):
        with open(NAME_PREFERENCES_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                unit_id = str(row.get("UnitId", "")).strip()
                original_name = str(row.get("OriginalInstName", "")).strip()
                preferred_name = str(row.get("PreferredInstName", "")).strip()
                _register_match_name(unit_id, original_name, "CollegeNamePreferences.csv:OriginalInstName")
                _register_match_name(unit_id, preferred_name, "CollegeNamePreferences.csv:PreferredInstName")
    else:
        print(f"  ⚠ College name preferences CSV not found: {NAME_PREFERENCES_CSV_PATH}")

    if os.path.exists(SLUG_PREFERENCES_CSV_PATH):
        with open(SLUG_PREFERENCES_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                unit_id = str(row.get("UnitId", "")).strip()
                inst_name = str(row.get("InstName", "")).strip()
                slug = str(row.get("Slug", "")).strip()
                _register_match_name(unit_id, inst_name, "CollegeSlugPreferences.csv:InstName")
                _register_match_name(unit_id, slug, "CollegeSlugPreferences.csv:Slug")
    else:
        print(f"  ⚠ College slug preferences CSV not found: {SLUG_PREFERENCES_CSV_PATH}")

    if os.path.exists(HISTORICAL_COLLEGES_CSV_PATH):
        with open(HISTORICAL_COLLEGES_CSV_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                unit_id = str(row.get("UnitId", "")).strip()
                inst_name = str(row.get("InstName", "")).strip()
                _register_match_name(unit_id, inst_name, "HistoricalUrbanColleges.csv:InstName")
    else:
        print(f"  ⚠ Historical colleges CSV not found: {HISTORICAL_COLLEGES_CSV_PATH}")

    norm_keys = set(_alias_by_instname_norm.keys())
    norm_keys.update(_alias_by_alias_norm.keys())
    _alias_norm_keys.extend(sorted(norm_keys))
    variant_keys = set(_alias_by_instname_variant.keys())
    variant_keys.update(_alias_by_alias_variant.keys())
    _alias_variant_keys.extend(sorted(variant_keys))
    token_keys = set(_alias_by_instname_tokens.keys())
    token_keys.update(_alias_by_alias_tokens.keys())
    _alias_token_keys.extend(sorted(token_keys))
    _alias_index_loaded = True


def resolve_unit_id(raw_name: str) -> Tuple[str, str, str, float]:
    """
    Placeholder for UnitID matching implementation.
    Replace this with your real matching logic when ready.
    
    Returns:
        (unit_id, match_method, match_source_csv, match_confidence)
    """
    if not raw_name:
        return ("", "UNMATCHED", "", 0.0)
    _load_alias_index()
    for candidate in _generate_match_candidates(raw_name):
        name = candidate.strip()
        name_lower = name.lower()
        if name_lower in _alias_by_instname_lower:
            source = _instname_source_by_lower.get(name_lower, "UNKNOWN_INSTNAME_SOURCE")
            return (_alias_by_instname_lower[name_lower], "EXACT", source, 1.0)
        if name_lower in _alias_by_alias_lower:
            source = _alias_source_by_lower.get(name_lower, "UNKNOWN_ALIAS_SOURCE")
            return (_alias_by_alias_lower[name_lower], "EXACT", source, 1.0)

        name_norm = _normalize_name(name)
        if name_norm in _alias_by_instname_norm:
            source = _instname_source_by_norm.get(name_norm, "UNKNOWN_INSTNAME_SOURCE")
            return (_alias_by_instname_norm[name_norm], "NORMALIZED", source, 0.99)
        if name_norm in _alias_by_alias_norm:
            source = _alias_source_by_norm.get(name_norm, "UNKNOWN_ALIAS_SOURCE")
            return (_alias_by_alias_norm[name_norm], "NORMALIZED", source, 0.99)

        name_variant = _normalize_match_variant(name)
        if name_variant in _alias_by_instname_variant:
            source = _instname_source_by_variant.get(name_variant, "UNKNOWN_INSTNAME_SOURCE")
            return (_alias_by_instname_variant[name_variant], "VARIANT", source, 0.97)
        if name_variant in _alias_by_alias_variant:
            source = _alias_source_by_variant.get(name_variant, "UNKNOWN_ALIAS_SOURCE")
            return (_alias_by_alias_variant[name_variant], "VARIANT", source, 0.97)

        token_key = _token_sort_key(name)
        if token_key in _alias_by_instname_tokens:
            source = _instname_source_by_tokens.get(token_key, "UNKNOWN_INSTNAME_SOURCE")
            return (_alias_by_instname_tokens[token_key], "TOKEN_SORT", source, 0.95)
        if token_key in _alias_by_alias_tokens:
            source = _alias_source_by_tokens.get(token_key, "UNKNOWN_ALIAS_SOURCE")
            return (_alias_by_alias_tokens[token_key], "TOKEN_SORT", source, 0.95)

        fuzzy_checks = [
            (name_norm, _alias_norm_keys, _alias_by_instname_norm, _instname_source_by_norm, "FUZZY"),
            (name_norm, _alias_norm_keys, _alias_by_alias_norm, _alias_source_by_norm, "FUZZY"),
            (name_variant, _alias_variant_keys, _alias_by_instname_variant, _instname_source_by_variant, "FUZZY_VARIANT"),
            (name_variant, _alias_variant_keys, _alias_by_alias_variant, _alias_source_by_variant, "FUZZY_VARIANT"),
            (token_key, _alias_token_keys, _alias_by_instname_tokens, _instname_source_by_tokens, "FUZZY_TOKEN_SORT"),
            (token_key, _alias_token_keys, _alias_by_alias_tokens, _alias_source_by_tokens, "FUZZY_TOKEN_SORT"),
        ]
        for query, keys, mapping, sources, method in fuzzy_checks:
            if not query:
                continue
            matches = difflib.get_close_matches(query, keys, n=1, cutoff=FUZZY_CUTOFF)
            if not matches:
                continue
            best = matches[0]
            score = difflib.SequenceMatcher(a=query, b=best).ratio()
            unit_id = mapping.get(best, "")
            if unit_id:
                source = sources.get(best, "UNKNOWN_MATCH_SOURCE")
                return (unit_id, method, source, score)
    return ("", "UNMATCHED", "", 0.0)


def _slugify_filename(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip())
    text = text.strip("_").lower()
    return text or "rankings"


def _review_unmatched_rows(
    entries_df: pd.DataFrame,
    per_url_file: str,
    unmatched_file: str,
) -> pd.DataFrame:
    unmatched_count = int((entries_df["Match Method"] == "UNMATCHED").sum())
    if unmatched_count == 0:
        return entries_df

    print(f"  ⚠ Found {unmatched_count} unmatched rows")
    print(f"  Review full file: {per_url_file}")
    print(f"  Review unmatched-only file: {unmatched_file}")
    print("  Options: keep / drop / edited")
    choice = input("  After review, choose [keep]: ").strip().lower() or "keep"

    try:
        reviewed_df = pd.read_csv(per_url_file, dtype=str).fillna("")
    except Exception:
        reviewed_df = entries_df.copy()

    if choice == "drop":
        reviewed_df = reviewed_df[reviewed_df["Match Method"] != "UNMATCHED"].copy()
        reviewed_df.to_csv(per_url_file, index=False)
        print(f"  ✓ Removed unmatched rows from {per_url_file}")
    elif choice == "edited":
        print(f"  ✓ Loaded your edited file from {per_url_file}")
    else:
        print("  ✓ Keeping unmatched rows for this file")

    return reviewed_df


def build_rankings_metadata_table(
    urls: List[str],
    output_file: str = "ranking_lists.csv",
    biases: List[int] | None = None,
    interactive: bool = True
) -> pd.DataFrame:
    """
    Build a metadata table for ranking lists (one row per URL).
    
    Columns:
    ListID, Publisher, ListName, Category, Year, Year Collected/Accessed, URL, List Bias/ Weight
    """
    rows: List[Dict[str, str]] = []
    
    for i, url in enumerate(urls, 1):
        print("\n" + "="*70)
        print(f"[{i}/{len(urls)}] Processing: {url}")
        print("="*70)
        
        if interactive:
            meta = get_site_metadata_interactive(url)
        else:
            meta = get_site_metadata_auto(url)
        
        # Infer ranking year from list name or URL, then allow override
        inferred_year = _infer_year(meta.get("listName", "")) or _infer_year(url)
        year = inferred_year
        override = input(f"Ranking Year [{year or 'unknown'}]: ").strip()
        if override:
            year = override
        
        # Bias/weight (from list or prompt)
        if biases and i - 1 < len(biases):
            bias_value = biases[i - 1]
        else:
            bias_input = input("List Bias/Weight (integer): ").strip()
            bias_value = int(bias_input) if bias_input else 0
        
        list_id = generate_random_list_id()
        
        rows.append({
            "ListID": list_id,
            "Publisher": meta.get("publisher", ""),
            "ListName": meta.get("listName", ""),
            "Category": meta.get("category", ""),
            "Year": year,
            "Year Collected/Accessed": str(meta.get("yearAccessed", "")),
            "URL": meta.get("url", url),
            "List Bias/ Weight": str(bias_value),
        })
    
    df = pd.DataFrame(rows, columns=[
        "ListID",
        "Publisher",
        "ListName",
        "Category",
        "Year",
        "Year Collected/Accessed",
        "URL",
        "List Bias/ Weight",
    ])
    
    df.to_csv(output_file, index=False)
    print(f"\n✓ Saved ranking list metadata to {output_file}")
    return df


def build_rankings_entries_table(
    metadata_df: pd.DataFrame,
    output_file: str = "ranking_entries.csv",
    use_browser: bool = True
) -> pd.DataFrame:
    """
    Build a rankings table with columns:
    ListId, UnitId, Rank, Score, IsTied, RawName, Match Method, Match Source CSV, Match Confidence
    """
    combined_frames: List[pd.DataFrame] = []
    usnews_url_count = 0
    output_base, output_ext = os.path.splitext(output_file)
    if not output_ext:
        output_ext = ".csv"
    parts_dir = f"{output_base}_parts"
    os.makedirs(parts_dir, exist_ok=True)
    
    for index, row in enumerate(metadata_df.iterrows(), 1):
        _, row = row
        list_id = str(row.get("ListID", "")).strip()
        url = str(row.get("URL", "")).strip()
        if not url:
            continue
        
        print("\n" + "="*70)
        print(f"Scraping rankings for ListID {list_id}")
        print(f"URL: {url}")
        print("="*70)

        usnews_soft_target = None
        if _is_usnews_url(url):
            usnews_url_count += 1
            if usnews_url_count == 1:
                usnews_soft_target = 400
            elif usnews_url_count == 2:
                usnews_soft_target = 1400

        rankings = _get_rankings_for_url(
            url,
            use_browser=use_browser,
            usnews_soft_target=usnews_soft_target,
        )
        if not rankings:
            print("  ✗ No rankings found")
            continue
        
        added_count = 0
        skipped_count = 0
        entries: List[Dict[str, str]] = []
        for r in rankings:
            raw_name = _find_first_value(r, ["college", "school", "institution", "university", "name"])
            raw_name = _strip_trailing_location(raw_name)
            rank_raw = _find_first_value(r, ["rank", "ranking", "position", "#"])
            score_raw = _find_first_value(r, ["score", "points"])
            rank, is_tied = _parse_rank_value(rank_raw)

            if _is_truncated_school_name(raw_name):
                skipped_count += 1
                continue

            if not rank or not _looks_like_ranked_school_name(raw_name, url):
                skipped_count += 1
                continue

            unit_id, match_method, match_source_csv, match_conf = resolve_unit_id(raw_name)

            entries.append({
                "ListId": list_id,
                "UnitId": unit_id,
                "Rank": rank,
                "Score": score_raw,
                "IsTied": str(is_tied),
                "RawName": raw_name,
                "Match Method": match_method,
                "Match Source CSV": match_source_csv,
                "Match Confidence": str(match_conf),
            })
            added_count += 1

        print(f"  ✓ Added {added_count} rankings")
        if skipped_count:
            print(f"  ⚠ Skipped {skipped_count} unmatched or suspicious rows")

        per_url_df = pd.DataFrame(entries, columns=[
            "ListId",
            "UnitId",
            "Rank",
            "Score",
            "IsTied",
            "RawName",
            "Match Method",
            "Match Source CSV",
            "Match Confidence",
        ])

        file_stub = f"{index:02d}_{_slugify_filename(list_id)}_{_slugify_filename(urlparse(url).netloc)}"
        per_url_file = os.path.join(parts_dir, f"{file_stub}{output_ext}")
        unmatched_file = os.path.join(parts_dir, f"{file_stub}_unmatched{output_ext}")
        per_url_df.to_csv(per_url_file, index=False)
        unmatched_df = per_url_df[per_url_df["Match Method"] == "UNMATCHED"].copy()
        unmatched_df.to_csv(unmatched_file, index=False)
        print(f"  ✓ Saved per-URL rankings to {per_url_file}")

        if unmatched_df.empty:
            print("  ✓ No unmatched rows to review for this file")
            reviewed_df = per_url_df
        else:
            reviewed_df = _review_unmatched_rows(per_url_df, per_url_file, unmatched_file)

        combined_frames.append(reviewed_df)

    df = pd.concat(combined_frames, ignore_index=True) if combined_frames else pd.DataFrame(columns=[
        "ListId",
        "UnitId",
        "Rank",
        "Score",
        "IsTied",
        "RawName",
        "Match Method",
        "Match Source CSV",
        "Match Confidence",
    ])
    
    df.to_csv(output_file, index=False)
    print(f"\n✓ Saved ranking entries to {output_file}")
    print(f"✓ Saved per-URL entry files to {parts_dir}")
    return df


if __name__ == "__main__":
    print("\n" + "="*70)
    print("MASCOTGO COLLEGE RANKINGS PIPELINE")
    print("="*70)

    # Step 1: Build the ranking list metadata table (one row per URL)
    # Hardcode your list of ranking URLs here:
    urls = [
        # US News: tune scraper per URL; start with one ranking list (table mode).
        "https://www.usnews.com/best-colleges/rankings/national-universities?myCollege=national-universities&_sort=myCollege&_sortDirection=asc&_mode=table",
        # "https://www.forbes.com/top-colleges/",
        # "https://www.forbes.com/value-colleges/list/#tab:rank",
        # "https://www.usnews.com/best-colleges/search?_sort=rank&_sortDirection=asc&_mode=table",
        #"https://www.princetonreview.com/college-rankings/?rankings=best-career-services",
        #"https://www.niche.com/colleges/search/best-colleges/",
        #"https://www.mastersportal.com/search/universities/master/rankings/united-states",
        #"https://www.timeshighereducation.com/world-university-rankings/latest/world-ranking",
        #"https://www.shanghairanking.com/rankings/arwu/2025"

    ]
    metadata_df = build_rankings_metadata_table(urls, output_file="ranking_lists.csv", interactive=True)
    print("\nRanking list metadata preview:")
    print(metadata_df.head(10))

    # Step 2: Build rankings entries table (one row per ranked school)
    entries_df = build_rankings_entries_table(metadata_df, output_file="ranking_entries.csv", use_browser=True)
    print("\nRanking entries preview:")
    print(entries_df.head(10))
