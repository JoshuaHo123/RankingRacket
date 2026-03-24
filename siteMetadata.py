"""
Site Metadata Extractor

This module extracts and infers metadata from college ranking URLs.
It auto-fills what can be reliably inferred and allows user overrides.
"""

from urllib.parse import urlparse
from datetime import datetime
from typing import Dict, Tuple, Optional
import re
import requests
from bs4 import BeautifulSoup


def extract_publisher_from_domain(url: str) -> str:
    """
    Extract publisher name from domain.
    
    Examples:
        usnews.com → US News
        topuniversities.com → QS Rankings
        timeshighereducation.com → Times Higher Education
        example.com → Example
    
    Args:
        url: The URL
        
    Returns:
        Publisher name
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.lower().replace('www.', '')
    
    # Known domain mappings
    domain_to_publisher = {
        'usnews.com': 'US News & World Report',
        'topuniversities.com': 'QS Rankings',
        'qs.com': 'QS Rankings',
        'timeshighereducation.com': 'Times Higher Education',
        'arwu.org': 'ARWU',
        'shanghairanking.org': 'ARWU',
        'forbes.com': 'Forbes',
        'princetonreview.com': 'The Princeton Review',
        'niche.com': 'Niche',
    }
    
    # Check if domain is in known mappings
    for known_domain, publisher in domain_to_publisher.items():
        if known_domain in domain:
            return publisher
    
    # For unknown domains, use domain name
    # e.g., example.com → Example, myranking.org → Myranking
    base_domain = domain.split('.')[0]
    return base_domain.title()


def extract_category_from_path(url: str) -> Optional[str]:
    """
    Try to extract ranking category from URL path.
    
    Examples:
        /national-universities → National Universities
        /liberal-arts-colleges → Liberal Arts Colleges
        /engineering-schools → Engineering Schools
        /global/rankings → Global
    
    Args:
        url: The URL
        
    Returns:
        Category name or None if can't infer
    """
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    
    # Known category patterns
    category_patterns = {
        'national-universit': 'National Universities',
        'liberal-arts': 'Liberal Arts Colleges',
        'regional-universit': 'Regional Universities',
        'regional-college': 'Regional Colleges',
        'engineering': 'Engineering Schools',
        'business': 'Business Schools',
        'global': 'Global',
        'international': 'Global',
        'usa': 'USA',
        'united-states': 'USA',
    }
    
    for pattern, category in category_patterns.items():
        if pattern in path:
            return category
    
    return None


def get_page_title(url: str, timeout: int = 5) -> Optional[str]:
    """
    Extract page title from HTML meta tags or <title>.
    
    Tries (in order):
    1. og:title meta tag
    2. twitter:title meta tag
    3. <title> tag
    
    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        Page title or None if unavailable
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try og:title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content']
        
        # Try twitter:title
        twitter_title = soup.find('meta', {'name': 'twitter:title'})
        if twitter_title and twitter_title.get('content'):
            return twitter_title['content']
        
        # Try <title> tag
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.string
        
    except Exception as e:
        print(f"  ⚠ Could not fetch page title: {e}")
    
    return None


def infer_list_name_from_title(title: str, publisher: str) -> str:
    """
    Extract list name from page title.
    
    Removes common publisher names and suffixes like " - Rankings", " | Rankings", etc.
    
    Args:
        title: The page title
        publisher: The publisher name (to filter out)
        
    Returns:
        Cleaned list name
    """
    if not title:
        return f'{publisher} Rankings'
    
    # Remove common suffixes
    suffixes = [' - Rankings', ' | Rankings', ' Rankings', ' - Best', ' | Best', ' - Ranking']
    for suffix in suffixes:
        title = title.replace(suffix, '')
    
    # Remove publisher name if it appears in title
    if publisher.lower() in title.lower():
        title = re.sub(re.escape(publisher), '', title, flags=re.IGNORECASE).strip()
    
    # Remove extra whitespace
    title = ' '.join(title.split())
    
    return title if title else f'{publisher} Rankings'


def get_site_metadata_auto(url: str, fetch_title: bool = True) -> Dict[str, any]:
    """
    Auto-infer site metadata from URL and page content.
    
    Returns a dictionary with auto-filled values:
    - publisher (from domain)
    - url (the input URL)
    - yearAccessed (today's year)
    - category (from URL path, if detectable)
    - listName (from page title, if available)
    - timestamp (full datetime)
    
    Args:
        url: The ranking website URL
        fetch_title: Whether to fetch page and extract title (slower but more accurate)
        
    Returns:
        Dictionary with auto-filled metadata
        
    Example:
        >>> metadata = get_site_metadata_auto("https://www.forbes.com/top-colleges/")
        >>> print(metadata)
        {
            'publisher': 'Forbes',
            'url': 'https://www.forbes.com/top-colleges/',
            'yearAccessed': 2026,
            'timestamp': '2026-01-26 14:30:45',
            'category': None,
            'listName': 'Forbes Top Colleges Ranking For 2024'
        }
    """
    now = datetime.now()
    
    # Always reliable
    publisher = extract_publisher_from_domain(url)
    yearAccessed = now.year
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # Sometimes reliable
    category = extract_category_from_path(url)
    listName = None
    
    if fetch_title:
        print(f"  📄 Fetching page title for list name...")
        title = get_page_title(url)
        if title:
            listName = infer_list_name_from_title(title, publisher)
    
    return {
        'publisher': publisher,
        'url': url,
        'yearAccessed': yearAccessed,
        'timestamp': timestamp,
        'category': category,
        'listName': listName
    }


def get_site_metadata_interactive(url: str, fetch_title: bool = True) -> Dict[str, any]:
    """
    Get site metadata with auto-filled values and user override options.
    
    Displays auto-inferred values and allows user to confirm or override each field.
    
    Args:
        url: The ranking website URL
        fetch_title: Whether to fetch page and extract title
        
    Returns:
        Dictionary with final metadata (auto-filled + user overrides)
        
    Example:
        >>> metadata = get_site_metadata_interactive("https://www.example.com/rankings")
        Publisher: Example (auto) [press Enter to confirm]
        > 
        List Name: [empty - enter now]
        > My Custom Ranking List
    """
    # Get auto-filled values
    auto_metadata = get_site_metadata_auto(url, fetch_title=fetch_title)
    
    print("\n" + "="*70)
    print("SITE METADATA - CONFIRM OR OVERRIDE")
    print("="*70)
    
    # Display and confirm each field
    final_metadata = auto_metadata.copy()
    
    # Publisher
    print(f"\nPublisher: {auto_metadata['publisher']} (auto-filled from domain)")
    override = input("  Override? Leave blank to confirm: ").strip()
    if override:
        final_metadata['publisher'] = override
    
    # URL
    print(f"\nURL: {auto_metadata['url']}")
    print("  (Cannot override)")
    
    # Year Accessed
    print(f"\nYear Accessed: {auto_metadata['yearAccessed']}")
    override = input("  Override? Leave blank to confirm: ").strip()
    if override:
        try:
            final_metadata['yearAccessed'] = int(override)
        except ValueError:
            print("  Invalid year, keeping original")
    
    # Category (optional)
    category_str = auto_metadata['category'] if auto_metadata['category'] else "(not detected)"
    print(f"\nCategory: {category_str}")
    override = input("  Enter category (or press Enter to skip): ").strip()
    if override:
        final_metadata['category'] = override
    
    # List Name (optional)
    listname_str = auto_metadata['listName'] if auto_metadata['listName'] else "(not detected)"
    print(f"\nList Name: {listname_str}")
    override = input("  Enter list name (or press Enter to skip): ").strip()
    if override:
        final_metadata['listName'] = override
    
    print("\n" + "="*70)
    print("✓ Metadata confirmed")
    print("="*70 + "\n")
    
    return final_metadata

