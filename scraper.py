"""
College Ranking Website Scraper

This module provides functionality to scrape college ranking data from websites.
Supports multiple ranking websites and data collection into structured formats.
Handles both static HTML and JavaScript-rendered pages.
"""

import json
import logging
import re
from collections import OrderedDict
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)


class CollegeRankingScraper:
    """Scrapes college ranking data from websites."""

    def __init__(self, timeout: int = 12, use_browser: bool = False, headless: bool = True):
        self.timeout = timeout
        self.use_browser = use_browser
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None
        self.last_page_html = None
        self.last_good_page_html = None
        self._lightweight_routes_enabled = False
        # Stop scrolling once this many profile links are visible. US News ranking
        # pages are usually a few hundred rows; 2000 forced long scroll loops.
        self.usnews_soft_target = 650
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": BROWSER_USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def _init_browser(self):
        if self.browser is not None and self.page is not None:
            return

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = self.browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            user_agent=BROWSER_USER_AGENT,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
            """
        )
        self.page = context.new_page()
        logger.info("Playwright browser initialized")

    def _enable_lightweight_browser_mode(self):
        if not self.page or self._lightweight_routes_enabled:
            return
        try:
            self.page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in {"image", "media", "font", "websocket"}
                else route.continue_(),
            )
            self._lightweight_routes_enabled = True
            logger.info("Enabled lightweight browser mode")
        except Exception as e:
            logger.warning(f"Could not enable lightweight browser mode: {e}")

    def _scroll_page(self):
        if not self.page:
            return
        for _ in range(4):
            self.page.mouse.wheel(0, 2500)
            self.page.wait_for_timeout(750)
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(500)

    def _count_usnews_profile_links(self) -> int:
        if not self.page:
            return 0
        return int(
            self.page.locator("a[href*='/best-colleges/']").evaluate_all(
                """
                elements => elements.filter(el => /\\/best-colleges\\/[^/?#]+-\\d+/.test(el.getAttribute('href') || '')).length
                """
            )
        )

    def _count_niche_profile_links(self) -> int:
        if not self.page:
            return 0
        return int(
            self.page.locator("a[href*='/colleges/']").evaluate_all(
                """
                elements => {
                    const seen = new Set();
                    for (const el of elements) {
                        const href = el.getAttribute('href') || '';
                        if (/\\/colleges\\/[^/?#]+\\/?$/.test(href)) {
                            seen.add(href);
                        }
                    }
                    return seen.size;
                }
                """
            )
        )

    def _count_the_rows(self) -> int:
        if not self.page:
            return 0
        return int(
            self.page.locator(
                "tr, [class*='table-row'], [class*='ranking-institution-row'], [class*='ranking-data-row']"
            ).evaluate_all(
                """
                elements => {
                    let count = 0;
                    for (const el of elements) {
                        const text = (el.innerText || '').trim();
                        if (!text) continue;
                        if (/(?:^|\\s)(?:#|rank\\s*)?\\d{1,4}(?:\\s|$)/i.test(text)) {
                            count += 1;
                        }
                    }
                    return count;
                }
                """
            )
        )

    def _count_mastersportal_profile_links(self) -> int:
        if not self.page:
            return 0
        return int(
            self.page.locator("a[href]").evaluate_all(
                """
                elements => {
                    const seen = new Set();
                    for (const el of elements) {
                        const href = (el.getAttribute('href') || '').toLowerCase();
                        if (href.includes('/universities/') || href.includes('/university/') || href.includes('/institutions/')) {
                            seen.add(href);
                        }
                    }
                    return seen.size;
                }
                """
            )
        )

    def _find_the_scroll_container_selector(self) -> Optional[str]:
        if not self.page:
            return None
        selectors = [
            "[class*='table'] [class*='scroll']",
            "[class*='table'] [style*='overflow']",
            "[class*='ranking'] [class*='scroll']",
            "[class*='viewport']",
            "[role='rowgroup']",
        ]
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                if locator.count() == 0:
                    continue
                visible = locator.is_visible(timeout=500)
                if not visible:
                    continue
                can_scroll = locator.evaluate(
                    """
                    el => {
                        const style = window.getComputedStyle(el);
                        return (el.scrollHeight - el.clientHeight) > 50 &&
                            (style.overflowY === 'auto' || style.overflowY === 'scroll' || style.overflow === 'auto' || style.overflow === 'scroll');
                    }
                    """
                )
                if can_scroll:
                    return selector
            except Exception:
                continue
        return None

    def _capture_current_page_html(self) -> str:
        if not self.page:
            return ""
        try:
            return self.page.content()
        except Exception:
            return ""

    def _remember_last_good_page_html(self) -> None:
        html = self._capture_current_page_html()
        if not html:
            return
        lowered = html.lower()
        if "aw, snap" in lowered or "something went wrong while displaying this webpage" in lowered:
            return
        self.last_good_page_html = html

    def _recover_browser_soup(self, domain: str) -> Optional[BeautifulSoup]:
        html = None
        if domain == "timeshighereducation.com" and self.last_page_html:
            html = self.last_page_html
        elif self.last_good_page_html:
            html = self.last_good_page_html
        elif self.last_page_html:
            html = self.last_page_html
        if not html:
            return None
        logger.warning("Using last captured browser HTML after page failure")
        self.last_page_html = None
        return BeautifulSoup(html, "html.parser")

    def _merge_html_snapshots(self, snapshots: List[str]) -> str:
        if not snapshots:
            return ""
        merged = OrderedDict()
        row_pattern = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)
        div_pattern = re.compile(
            r"<div\b[^>]*class=\"[^\"]*(?:table-row|ranking-institution-row|ranking-data-row)[^\"]*\"[^>]*>.*?</div>",
            re.IGNORECASE | re.DOTALL,
        )
        for html in snapshots:
            for pattern in (row_pattern, div_pattern):
                for match in pattern.finditer(html):
                    block = match.group(0)
                    text_key = re.sub(r"<[^>]+>", " ", block)
                    text_key = re.sub(r"\s+", " ", text_key).strip().lower()
                    if not text_key:
                        continue
                    merged.setdefault(text_key, block)
        if not merged:
            return snapshots[-1]
        body = "\n".join(merged.values())
        return f"<html><body><table><tbody>{body}</tbody></table></body></html>"

    def _click_expand_controls(self):
        if not self.page:
            return False
        clicked = False
        labels = ["Show more", "Load more", "See more", "More results"]
        for label in labels:
            try:
                button = self.page.get_by_role("button", name=re.compile(label, re.IGNORECASE)).first
                if button.count() and button.is_visible(timeout=500):
                    button.click(timeout=1000)
                    self.page.wait_for_timeout(1500)
                    clicked = True
            except Exception:
                continue
        return clicked

    def _dismiss_usnews_sign_in_modal(self) -> bool:
        if not self.page:
            return False

        dismissed = False
        close_name_patterns = [
            re.compile(r"close", re.IGNORECASE),
            re.compile(r"dismiss", re.IGNORECASE),
            re.compile(r"not now", re.IGNORECASE),
            re.compile(r"no thanks", re.IGNORECASE),
            re.compile(r"skip", re.IGNORECASE),
        ]

        for pattern in close_name_patterns:
            try:
                button = self.page.get_by_role("button", name=pattern).first
                if button.count() and button.is_visible(timeout=300):
                    button.click(timeout=1000)
                    self.page.wait_for_timeout(600)
                    dismissed = True
            except Exception:
                continue

        try:
            dialog = self.page.locator("[role='dialog'], [aria-modal='true'], .modal, [class*='modal'], [class*='overlay']").first
            if dialog.count():
                dialog_text = dialog.inner_text(timeout=500).lower()
                if "sign in" in dialog_text or "log in" in dialog_text or "create a free account" in dialog_text:
                    escape_close = self.page.evaluate(
                        """
                        () => {
                            const isVisible = (el) => {
                                if (!el) return false;
                                const style = window.getComputedStyle(el);
                                const rect = el.getBoundingClientRect();
                                return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                            };

                            const candidates = Array.from(document.querySelectorAll(
                                '[role="dialog"] button, [aria-modal="true"] button, .modal button, [class*="modal"] button, [class*="overlay"] button'
                            ));

                            for (const el of candidates) {
                                const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                                const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
                                if (!isVisible(el)) continue;
                                if (
                                    text === 'x' ||
                                    aria.includes('close') ||
                                    text.includes('close') ||
                                    text.includes('dismiss') ||
                                    text.includes('not now') ||
                                    text.includes('no thanks') ||
                                    text.includes('skip')
                                ) {
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                        """
                    )
                    if escape_close:
                        self.page.wait_for_timeout(600)
                        dismissed = True
            if not dismissed:
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(300)
        except Exception:
            pass

        return dismissed

    def _usnews_is_table_mode(self, url: Optional[str]) -> bool:
        if not url:
            return False
        mode = (parse_qs(urlparse(url).query).get("_mode") or [""])[0].lower()
        return mode == "table"

    def _usnews_goto_with_retries(self, url: str, max_tries: int = 4) -> None:
        """US News sometimes returns transient net::ERR_HTTP2_PROTOCOL_ERROR; retry with backoff."""
        if not self.page:
            return
        last_err: Optional[Exception] = None
        for i in range(max_tries):
            try:
                self.page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout * 1000,
                )
                return
            except PlaywrightError as e:
                last_err = e
                msg = str(e)
                transient = any(
                    s in msg
                    for s in (
                        "ERR_HTTP2",
                        "ERR_CONNECTION",
                        "ERR_NETWORK",
                        "ERR_ABORTED",
                        "net::",
                        "Navigation failed",
                        "Protocol error",
                    )
                ) or isinstance(e, PlaywrightTimeoutError)
                if i < max_tries - 1 and transient:
                    delay_ms = 1200 * (i + 1)
                    logger.warning(
                        "US News goto attempt %s/%s failed (%s); retrying in %sms",
                        i + 1,
                        max_tries,
                        e,
                        delay_ms,
                    )
                    self.page.wait_for_timeout(delay_ms)
                    continue
                raise last_err

    def _stabilize_usnews_page(self, url: Optional[str] = None):
        if not self.page:
            return
        table_mode = self._usnews_is_table_mode(url)
        stable_rounds = 0
        soft_target = self.usnews_soft_target
        if table_mode:
            # Table rankings load a bounded set of rows; no need to chase thousands of links.
            soft_target = min(soft_target, 400)
        max_rounds = 8 if table_mode else 14
        wheel_passes = 1 if table_mode else 2
        wheel_delay_ms = 500 if table_mode else 700
        settle_ms = 650 if table_mode else 1100
        stable_need = 1 if table_mode else 2

        previous_count = -1
        previous_height = -1
        previous_scroll_y = -1
        self._remember_last_good_page_html()
        for _ in range(max_rounds):
            try:
                self._dismiss_usnews_sign_in_modal()
                clicked = self._click_expand_controls()

                # US News is sensitive to fast, large jumps; scroll in smaller steps and
                # give the client time to render additional rows before continuing.
                for _ in range(wheel_passes):
                    self.page.mouse.wheel(0, 1200)
                    self.page.wait_for_timeout(wheel_delay_ms)

                self._dismiss_usnews_sign_in_modal()
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=1500)
                except PlaywrightTimeoutError:
                    pass
                self.page.wait_for_timeout(settle_ms)
                self._remember_last_good_page_html()
                current_count = self._count_usnews_profile_links()
                current_height = int(self.page.evaluate("document.body.scrollHeight"))
                current_scroll_y = int(self.page.evaluate("window.scrollY"))
                viewport_height = int(self.page.evaluate("window.innerHeight"))
                logger.info(f"US News visible profile links: {current_count}")
                no_growth = current_count == previous_count and current_height == previous_height
                no_scroll_progress = current_scroll_y == previous_scroll_y and current_height == previous_height
                at_bottom = current_scroll_y + viewport_height >= current_height - 50
                if no_growth and no_scroll_progress and not clicked:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                previous_count = current_count
                previous_height = current_height
                previous_scroll_y = current_scroll_y
                if stable_rounds >= stable_need and at_bottom:
                    logger.info("US News page stopped growing; ending scroll loop")
                    break
                if current_count >= soft_target:
                    logger.info("US News reached soft target; ending scroll loop")
                    break
                if table_mode and current_count >= 180 and stable_rounds >= 1 and at_bottom:
                    logger.info("US News table ranking: enough links loaded; ending scroll loop")
                    break
            except PlaywrightError as e:
                logger.warning(
                    "US News stabilize interrupted (using last good snapshot); cause: %s",
                    e,
                )
                self._remember_last_good_page_html()
                break
        try:
            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(500)
            self._remember_last_good_page_html()
        except PlaywrightError:
            self._remember_last_good_page_html()

    def _stabilize_niche_page(self):
        if not self.page:
            return
        stable_rounds = 0
        previous_count = -1
        previous_height = -1
        for _ in range(14):
            clicked = self._click_expand_controls()
            self.page.mouse.wheel(0, 4000)
            self.page.wait_for_timeout(1800)
            try:
                self.page.wait_for_load_state("networkidle", timeout=2500)
            except PlaywrightTimeoutError:
                pass
            current_count = self._count_niche_profile_links()
            current_height = int(self.page.evaluate("document.body.scrollHeight"))
            logger.info(f"Niche visible profile links: {current_count}")
            if current_count == previous_count and current_height == previous_height and not clicked:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_count = current_count
            previous_height = current_height
            if stable_rounds >= 2:
                break
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(500)

    def _stabilize_the_page(self):
        if not self.page:
            return
        stable_rounds = 0
        previous_count = -1
        previous_height = -1
        snapshots: List[str] = []
        container_selector = self._find_the_scroll_container_selector()
        for _ in range(4):
            clicked = self._click_expand_controls()
            if container_selector:
                try:
                    self.page.locator(container_selector).first.evaluate(
                        "(el) => { el.scrollTop = Math.min(el.scrollTop + 1400, el.scrollHeight); }"
                    )
                except Exception:
                    self.page.mouse.wheel(0, 4500)
            else:
                self.page.mouse.wheel(0, 4500)
            self.page.wait_for_timeout(1800)
            try:
                self.page.wait_for_load_state("networkidle", timeout=2500)
            except PlaywrightTimeoutError:
                pass
            snapshots.append(self._capture_current_page_html())
            current_count = self._count_the_rows()
            if container_selector:
                try:
                    current_height = int(
                        self.page.locator(container_selector).first.evaluate("(el) => el.scrollHeight")
                    )
                except Exception:
                    current_height = int(self.page.evaluate("document.body.scrollHeight"))
            else:
                current_height = int(self.page.evaluate("document.body.scrollHeight"))
            logger.info(f"THE visible ranking rows: {current_count}")
            if current_count == previous_count and current_height == previous_height and not clicked:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_count = current_count
            previous_height = current_height
            if stable_rounds >= 2:
                break
        self.last_page_html = self._merge_html_snapshots(snapshots)
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(500)

    def _stabilize_mastersportal_page(self):
        if not self.page:
            return
        stable_rounds = 0
        previous_count = -1
        previous_height = -1
        for _ in range(10):
            clicked = self._click_expand_controls()
            self.page.mouse.wheel(0, 3500)
            self.page.wait_for_timeout(1800)
            try:
                self.page.wait_for_load_state("networkidle", timeout=2500)
            except PlaywrightTimeoutError:
                pass
            current_count = self._count_mastersportal_profile_links()
            current_height = int(self.page.evaluate("document.body.scrollHeight"))
            logger.info(f"Mastersportal visible profile links: {current_count}")
            if current_count == previous_count and current_height == previous_height and not clicked:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_count = current_count
            previous_height = current_height
            if stable_rounds >= 2:
                break
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(700)

    def _page_looks_blocked(self) -> bool:
        if not self.page:
            return False
        try:
            text = self.page.locator("body").inner_text(timeout=2000).lower()
        except Exception:
            return False
        blocked_markers = [
            "verify you are human",
            "unusual traffic",
            "access denied",
            "captcha",
            "bot detected",
            "automated access",
            "press and hold",
            "security check",
        ]
        return any(marker in text for marker in blocked_markers)

    def _page_has_niche_transient_error(self) -> bool:
        if not self.page:
            return False
        try:
            text = self.page.locator("body").inner_text(timeout=2000).lower()
        except Exception:
            return False
        error_markers = [
            "oops! something went wrong",
            "niche engineers are working to fix the issue",
            "please try again later",
        ]
        return all(marker in text for marker in error_markers[:2]) or any(
            marker in text for marker in error_markers
        )

    def _ensure_niche_results_page(self, wait_for_selector: Optional[str] = None) -> bool:
        if not self.page:
            return False
        for attempt in range(4):
            try:
                if wait_for_selector:
                    self.page.wait_for_selector(
                        wait_for_selector,
                        state="attached",
                        timeout=self.timeout * 1000,
                    )
                else:
                    self.page.wait_for_load_state("networkidle", timeout=self.timeout * 1000)
            except PlaywrightTimeoutError:
                pass

            if not self._page_has_niche_transient_error():
                return True

            backoff_ms = 1500 * (attempt + 1)
            logger.warning(f"Niche transient error page detected; retrying after {backoff_ms}ms")
            self.page.wait_for_timeout(backoff_ms)
            if attempt < 3:
                try:
                    self.page.reload(wait_until="domcontentloaded", timeout=self.timeout * 1000)
                except Exception:
                    return False
        return False

    def fetch_page(self, url: str, wait_for_selector: Optional[str] = None) -> Optional[BeautifulSoup]:
        try:
            domain = urlparse(url).netloc.lower().replace("www.", "")
            if "usnews.com" in domain:
                return self._fetch_page_browser(url, wait_for_selector)
            if self.use_browser:
                soup = self._fetch_page_browser(url, wait_for_selector)
                if soup is not None:
                    return soup
                logger.warning("Browser fetch failed; falling back to requests.")
                return self._fetch_page_requests(url)
            return self._fetch_page_requests(url)
        except Exception as e:
            logger.error(f"Error fetching {url}: {repr(e)}")
            return None

    def _fetch_page_requests(self, url: str) -> Optional[BeautifulSoup]:
        try:
            logger.info(f"Fetching (requests): {url}")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def _fetch_page_browser(self, url: str, wait_for_selector: Optional[str] = None) -> Optional[BeautifulSoup]:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        try:
            self._init_browser()
            if "usnews.com" in domain:
                self._enable_lightweight_browser_mode()
            logger.info(f"Fetching (Playwright): {url}")
            for attempt in range(2):
                if attempt == 0:
                    if "usnews.com" in domain:
                        self._usnews_goto_with_retries(url)
                    else:
                        self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                else:
                    logger.warning("Retrying browser fetch after transient page error")
                    self.page.reload(wait_until="domcontentloaded", timeout=self.timeout * 1000)

                if "niche.com" in domain:
                    if not self._ensure_niche_results_page(wait_for_selector):
                        if attempt == 0:
                            continue
                        logger.warning("Niche transient error page persisted after retry")
                        return None
                elif wait_for_selector:
                    self.page.wait_for_selector(
                        wait_for_selector,
                        state="attached",
                        timeout=self.timeout * 1000,
                    )
                    logger.info(f"Wait condition met for selector: {wait_for_selector}")
                else:
                    self.page.wait_for_load_state("networkidle", timeout=self.timeout * 1000)
                break

            if self._page_looks_blocked():
                logger.warning("Blocked or challenge page detected in browser fetch")
                return None

            if "usnews.com" in domain:
                self._stabilize_usnews_page(url)
            elif "niche.com" in domain:
                self._stabilize_niche_page()
            elif "timeshighereducation.com" in domain:
                self._stabilize_the_page()
            elif "mastersportal.com" in domain:
                self._stabilize_mastersportal_page()
            else:
                self._scroll_page()

            if self._page_looks_blocked():
                logger.warning("Blocked or challenge page detected after page interactions")
                return None

            self._remember_last_good_page_html()
            html = self.last_page_html if "timeshighereducation.com" in domain and self.last_page_html else self.page.content()
            self.last_page_html = None
            return BeautifulSoup(html, "html.parser")
        except PlaywrightTimeoutError as e:
            logger.error(f"Timeout fetching page with Playwright: {e}")
            return self._recover_browser_soup(domain)
        except PlaywrightError as e:
            logger.error(f"Error fetching page with Playwright: {e}")
            return self._recover_browser_soup(domain)

    def _normalize_rank(self, value: str) -> str:
        if not value:
            return ""
        text = str(value).strip()
        tie_match = re.match(r"^[Tt]\s*(\d+)$", text)
        if tie_match:
            return tie_match.group(1)
        match = re.search(r"\d+", text)
        return match.group(0) if match else ""

    def _clean_name(self, value: str) -> str:
        if not value:
            return ""
        text = re.sub(r"\s+", " ", str(value)).strip()
        text = re.sub(r"\s*\(tie\)\s*$", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"^(#?\d+\s+)", "", text).strip()
        text = self._collapse_repeated_name_phrases(text)
        return text

    def _collapse_repeated_name_phrases(self, value: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return ""
        words = text.split()
        max_phrase_len = min(len(words) // 2, 12)
        for phrase_len in range(max_phrase_len, 0, -1):
            left = words[:phrase_len]
            right = words[phrase_len:phrase_len * 2]
            if left and left == right:
                return " ".join(left + words[phrase_len * 2:]).strip()
        return text

    def _looks_like_school_name(self, value: str) -> bool:
        if not value:
            return False
        text = value.strip()
        if len(text) < 3 or len(text) > 160:
            return False
        lower = text.lower()
        noise_terms = [
            "read the methodology",
            "methodology",
            "rankings",
            "ranking",
            "advice",
            "guidebook",
            "digital edition",
            "save school",
            "ap home",
            "course",
            "preschool",
            "k-8",
            "k-12",
            "high schools",
            "newsletter",
            "photo",
            "photos",
            "sign up",
            "sign in",
            "compare schools",
            "sponsored",
            "featured",
            "view all",
            "here are",
            "national universities",
            "national liberal arts colleges",
            "regional universities",
            "regional colleges",
            "best value schools",
            "top performers on social mobility",
        ]
        if any(term in lower for term in noise_terms):
            return False
        if re.fullmatch(r"(#?\d+|[a-z]{1,2}\s*\d+)", lower):
            return False
        if re.fullmatch(r"view all \d+ photos?", lower):
            return False
        if re.fullmatch(r"in [a-z][a-z\s&-]+", lower):
            return False
        tokens = ["university", "college", "institute", "school", "academy", "polytechnic"]
        if any(t in lower for t in tokens):
            return True
        # Fallback for short branded names (MIT/Caltech) but avoid generic menu labels.
        if text.isupper() and 2 <= len(text) <= 8:
            return True
        if len(text.split()) >= 2 and re.search(r"[A-Za-z]", text):
            # prevent common non-school labels that still pass length checks
            soft_noise = ["best", "top", "news", "home", "results", "search", "major", "photo", "view all"]
            if any(n in lower for n in soft_noise):
                return False
            return True
        return False

    def _looks_like_usnews_school_name(self, value: str) -> bool:
        if not self._looks_like_school_name(value):
            return False
        lower = value.lower().strip()
        blocked_prefixes = [
            "here are ",
            "view all ",
            "in ",
        ]
        if any(lower.startswith(prefix) for prefix in blocked_prefixes):
            return False
        blocked_exact = {
            "elementary schools",
            "middle schools",
            "high schools",
            "business programs",
            "engineering programs",
        }
        if lower in blocked_exact:
            return False
        return True

    def _looks_like_princeton_school_name(self, value: str) -> bool:
        if not self._looks_like_school_name(value):
            return False
        lower = value.lower().strip()
        blocked_terms = [
            "save school",
            "best colleges",
            "the princeton review",
            "student body",
            "admissions information",
            "tuition and aid",
            "overview",
            "learn more",
            "read more",
            "best career services",
            "best campus food",
            "best dorms",
            "best colleges",
            "best value",
            "top party schools",
            "great financial aid",
        ]
        if any(term in lower for term in blocked_terms):
            return False
        if re.fullmatch(r"ranked\s*#?\d+", lower):
            return False
        return True

    def _looks_like_niche_school_name(self, value: str) -> bool:
        if not self._looks_like_school_name(value):
            return False
        lower = value.lower().strip()
        blocked_terms = [
            "find your best fit",
            "college quiz",
            "custom list of schools",
            "tailored to fit your needs",
            "what matters most to you",
            "visible profile links",
            "featured review",
            "read ",
            "explore ",
            "see all",
            "best colleges",
            "best schools",
            "college search",
            "view nearby homes",
            "acceptance rate",
            "net price",
            "freshman",
            "students",
            "grade:",
            "overall niche grade",
            "scholarship",
            "no essay",
            "graduate survey",
            "will you get in",
            "ways to pay for college",
            "best college food",
            "best food",
            "college scholarships",
        ]
        if any(term in lower for term in blocked_terms):
            return False
        blocked_exact = {
            "will you get in?",
            "ways to pay for college",
            "best college food",
        }
        if lower in blocked_exact:
            return False
        if re.fullmatch(r"[a-f][+-]?", lower):
            return False
        if re.search(r"\$\d[\d,]*", value):
            return False
        return True

    def _niche_name_from_href(self, href: str) -> str:
        href_text = str(href or "").strip()
        if not href_text:
            return ""
        match = re.search(r"/colleges/([^/?#]+)/?$", href_text, flags=re.IGNORECASE)
        if not match:
            return ""
        slug = match.group(1).replace("-", " ").replace("_", " ").strip()
        return self._clean_name(slug.title())

    def _looks_like_mastersportal_school_name(self, value: str) -> bool:
        if not self._looks_like_school_name(value):
            return False
        lower = value.lower().strip()
        blocked_terms = [
            "tuition fee",
            "full time",
            "part time",
            "online",
            "distance learning",
            "scholarship",
            "master of",
            "msc",
            "ma ",
            "llm",
            "study option",
            "programme",
            "program",
        ]
        if any(term in lower for term in blocked_terms):
            return False
        return True

    def _extract_mastersportal_rankings(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        seen = set()
        next_rank = 1
        container_selectors = [
            "article",
            "li",
            "[data-testid*='search-result']",
            "[class*='SearchResult']",
            "[class*='search-result']",
            "[class*='results'] article",
            "[class*='results'] li",
        ]

        containers = []
        for selector in container_selectors:
            found = soup.select(selector)
            if found:
                containers = found
                break

        if not containers:
            containers = soup.find_all(["article", "li", "div"])

        for container in containers:
            if getattr(container, "name", "") in {"header", "footer", "nav"}:
                continue
            container_text = container.get_text(" ", strip=True)
            if not container_text:
                continue

            candidates: List[str] = []
            for tag in container.find_all(["h1", "h2", "h3", "h4", "strong", "b", "span", "div", "a"], limit=20):
                candidate = self._clean_name(tag.get_text(" ", strip=True))
                if self._looks_like_mastersportal_school_name(candidate):
                    candidates.append(candidate)
            for a in container.find_all("a", href=True):
                href = (a.get("href") or "").strip().lower()
                if not any(token in href for token in ["/universities/", "/university/", "/institutions/"]):
                    continue
                name = self._clean_name(a.get_text(" ", strip=True))
                if self._looks_like_mastersportal_school_name(name):
                    candidates.append(name)

            if not candidates:
                continue

            # Prefer names with explicit school tokens, then the shortest plausible label.
            candidates = list(dict.fromkeys(candidates))
            token_candidates = [
                c for c in candidates
                if any(token in c.lower() for token in ["university", "college", "institute", "school", "academy", "polytechnic"])
            ]
            ranked_candidates = token_candidates or candidates
            name = sorted(ranked_candidates, key=lambda c: (len(c.split()), len(c)))[0]
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"Rank": str(next_rank), "RawName": name})
            next_rank += 1

        if rows:
            return self._dedupe(rows)

        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = (a.get("href") or "").strip().lower()
            if not any(token in href for token in ["/universities/", "/university/", "/institutions/"]):
                continue
            parent_names = {getattr(parent, "name", "") for parent in a.parents}
            if {"header", "footer", "nav"} & parent_names:
                continue
            name = self._clean_name(a.get_text(" ", strip=True))
            if not self._looks_like_mastersportal_school_name(name):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"Rank": str(next_rank), "RawName": name})
            next_rank += 1
        return self._dedupe(rows)

    def _extract_mastersportal_rankings_from_page(self) -> List[Dict[str, str]]:
        if not self.page:
            return []
        try:
            raw_names = self.page.evaluate(
                """
                () => {
                    const containerSelectors = [
                        'article',
                        'li',
                        '[data-testid*="search-result"]',
                        '[class*="SearchResult"]',
                        '[class*="search-result"]',
                        '[class*="results"] article',
                        '[class*="results"] li'
                    ];

                    for (const selector of containerSelectors) {
                        const containers = Array.from(document.querySelectorAll(selector));
                        const names = [];
                        for (const container of containers) {
                            if (!container || !container.innerText) continue;
                            const nodes = Array.from(container.querySelectorAll('h1, h2, h3, h4, strong, b, span, div, a'))
                                .slice(0, 20);
                            const candidates = nodes
                                .map(node => (node.innerText || '').replace(/\\s+/g, ' ').trim())
                                .filter(Boolean);
                            if (!candidates.length) continue;
                            names.push(...candidates);
                        }
                        if (names.length >= 5) {
                            return names;
                        }
                    }
                    return [];
                }
                """
            )
        except Exception:
            return []

        rows: List[Dict[str, str]] = []
        seen = set()
        next_rank = 1
        for raw_name in raw_names or []:
            name = self._clean_name(str(raw_name))
            if not self._looks_like_mastersportal_school_name(name):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({"Rank": str(next_rank), "RawName": name})
            next_rank += 1
        return self._dedupe(rows)

    def _extract_niche_rankings_from_page(self) -> List[Dict[str, str]]:
        if not self.page:
            return []
        try:
            raw_rows = self.page.evaluate(
                """
                () => {
                    const profilePattern = /\\/colleges\\/[^/?#]+\\/?$/i;
                    const containerSelectors = [
                        'article',
                        'li',
                        '[data-testid*="search-result"]',
                        '[class*="search-result"]',
                        '[class*="SearchResult"]'
                    ];

                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                    };

                    const containers = [];
                    for (const selector of containerSelectors) {
                        for (const el of document.querySelectorAll(selector)) {
                            if (isVisible(el)) containers.push(el);
                        }
                    }

                    const rows = [];
                    for (const container of containers) {
                        const links = Array.from(container.querySelectorAll('a[href]')).filter((a) => {
                            const href = a.getAttribute('href') || '';
                            return profilePattern.test(href) && isVisible(a);
                        });
                        if (!links.length) continue;

                        const text = (container.innerText || '').replace(/\\s+/g, ' ').trim();
                        const rankMatch = text.match(/(?:^|\\s)#?\\s*(\\d{1,4})(?:\\s|$)/);
                        const grouped = new Map();

                        for (const link of links) {
                            const href = link.getAttribute('href') || '';
                            if (!grouped.has(href)) grouped.set(href, []);
                            const linkText = (link.innerText || link.textContent || '').replace(/\\s+/g, ' ').trim();
                            if (linkText) grouped.get(href).push(linkText);
                        }

                        for (const [href, texts] of grouped.entries()) {
                            let name = texts
                                .filter((text) => text.length >= 3)
                                .sort((a, b) => b.length - a.length)[0] || '';

                            if (!name) {
                                const slug = href
                                    .split('/colleges/')[1]
                                    ?.replace(/\\/.*$/, '')
                                    ?.replace(/[-_]+/g, ' ')
                                    ?.trim() || '';
                                name = slug.replace(/\\b\\w/g, (c) => c.toUpperCase());
                            }

                            rows.push({
                                rank: rankMatch ? rankMatch[1] : '',
                                name,
                                href,
                            });
                        }
                    }

                    return rows;
                }
                """
            )
        except Exception:
            return []

        rows: List[Dict[str, str]] = []
        seen = set()
        next_rank = 1
        for raw_row in raw_rows or []:
            href = str((raw_row or {}).get("href", "")).strip().lower()
            name = self._clean_name(str((raw_row or {}).get("name", "")))
            if not self._looks_like_niche_school_name(name):
                fallback_name = self._niche_name_from_href(href)
                if self._looks_like_niche_school_name(fallback_name):
                    name = fallback_name
                else:
                    continue
            key = href or name.lower()
            if key in seen:
                continue
            seen.add(key)
            rank = self._normalize_rank(str((raw_row or {}).get("rank", "")))
            rows.append({"Rank": rank if rank else str(next_rank), "RawName": name, "URL": href})
            next_rank += 1
        return self._dedupe(rows)

    def _extract_mastersportal_from_scripts(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []

        def walk(node):
            if isinstance(node, dict):
                normalized = {str(k).lower(): v for k, v in node.items()}
                candidate_name = ""
                candidate_url = ""

                for key, value in normalized.items():
                    if isinstance(value, str):
                        if key in {"url", "uri", "link", "href", "path"}:
                            candidate_url = value
                        if any(term in key for term in ["universityname", "institutionname", "institution", "university", "name"]):
                            name = self._clean_name(value)
                            if self._looks_like_mastersportal_school_name(name):
                                candidate_name = name

                if candidate_name:
                    url_text = str(candidate_url).lower()
                    if not url_text or any(token in url_text for token in ["/universities/", "/university/", "/institutions/"]):
                        rows.append({"Rank": "", "RawName": candidate_name})

                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for script in soup.find_all("script"):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            raw_lower = raw.lower()
            if "mastersportal" not in raw_lower and "universit" not in raw_lower and "institution" not in raw_lower:
                continue

            payload = None
            if script.get("type") == "application/ld+json":
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = None
            if payload is None:
                match = re.search(r"=\s*({.*})\s*;?\s*$", raw, flags=re.DOTALL)
                if match:
                    try:
                        payload = json.loads(match.group(1))
                    except Exception:
                        payload = None
                else:
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        payload = None

            if payload is not None:
                walk(payload)

        seen = set()
        ordered: List[Dict[str, str]] = []
        next_rank = 1
        for row in rows:
            name = row.get("RawName", "")
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            ordered.append({"Rank": str(next_rank), "RawName": name})
            next_rank += 1
        return self._dedupe(ordered)

    def _extract_forbes_rankings(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        return self._extract_by_rows(
            soup,
            row_selectors=["table tr", "tbody tr"],
            rank_selectors=["td:nth-child(1)", "th:nth-child(1)", "[class*='rank']"],
            name_selectors=["td:nth-child(2)", "[class*='name']", "a"],
            max_rows=1000,
        )

    def _extract_forbes_article_rankings(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        seen = set()
        next_rank = 1

        article_containers = soup.select("article, main, [role='main']")
        if not article_containers:
            article_containers = [soup]

        list_selectors = [
            "ol li",
            "ul li",
            "h2",
            "h3",
            "p",
        ]

        for container in article_containers:
            for selector in list_selectors:
                nodes = container.select(selector)
                for node in nodes:
                    text = self._clean_name(node.get_text(" ", strip=True))
                    if not text:
                        continue

                    rank_match = re.match(r"^\s*(?:#\s*)?(\d{1,3})[\).:\- ]+", text)
                    inline_rank = self._normalize_rank(rank_match.group(1)) if rank_match else ""

                    candidate_name = ""
                    for a in node.find_all("a", href=True):
                        link_text = self._clean_name(a.get_text(" ", strip=True))
                        href = (a.get("href") or "").lower()
                        if self._looks_like_school_name(link_text):
                            candidate_name = link_text
                            if ".edu" in href or "university" in href or "college" in href:
                                break

                    if not candidate_name:
                        candidate_name = re.sub(r"^\s*(?:#\s*)?\d{1,3}[\).:\- ]+", "", text).strip()
                        candidate_name = re.split(r"\s+[–—-]\s+|\s+\|\s+", candidate_name, maxsplit=1)[0].strip()

                    if not self._looks_like_school_name(candidate_name):
                        continue

                    key = candidate_name.lower()
                    if key in seen:
                        continue
                    seen.add(key)

                    rows.append(
                        {
                            "Rank": inline_rank if inline_rank else str(next_rank),
                            "RawName": candidate_name,
                        }
                    )
                    next_rank += 1

                if len(rows) >= 20:
                    return self._dedupe(rows)

        return self._dedupe(rows)

    def _forbes_table_signature(self) -> str:
        if not self.page:
            return ""
        try:
            return str(
                self.page.evaluate(
                    """
                    () => {
                        const rows = Array.from(document.querySelectorAll('table tr, tbody tr')).slice(0, 8);
                        return rows.map(row => (row.innerText || '').replace(/\\s+/g, ' ').trim()).join(' || ');
                    }
                    """
                )
            )
        except Exception:
            return ""

    def _advance_forbes_pagination(self) -> bool:
        if not self.page:
            return False
        try:
            advanced = self.page.evaluate(
                """
                () => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                    };

                    const elements = Array.from(document.querySelectorAll('button, a'));
                    let currentPage = null;
                    for (const el of elements) {
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        const ariaCurrent = (el.getAttribute('aria-current') || '').toLowerCase();
                        const classes = (el.className || '').toString().toLowerCase();
                        const ariaLabel = (el.getAttribute('aria-label') || '').toLowerCase();
                        if (/^\\d+$/.test(text) && (ariaCurrent === 'page' || classes.includes('active') || classes.includes('selected') || ariaLabel.includes('current'))) {
                            currentPage = parseInt(text, 10);
                            break;
                        }
                    }

                    if (currentPage !== null) {
                        let candidate = null;
                        for (const el of elements) {
                            const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                            if (!/^\\d+$/.test(text)) continue;
                            const page = parseInt(text, 10);
                            if (page !== currentPage + 1) continue;
                            if (!isVisible(el)) continue;
                            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                            candidate = el;
                            break;
                        }
                        if (candidate) {
                            candidate.click();
                            return true;
                        }
                    }

                    const nextPatterns = [/^next$/i, /^next page$/i, /^>$/];
                    for (const el of elements) {
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        const ariaLabel = (el.getAttribute('aria-label') || '').trim();
                        const rel = (el.getAttribute('rel') || '').toLowerCase();
                        const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                        if (disabled || !isVisible(el)) continue;
                        if (rel === 'next' || nextPatterns.some((pattern) => pattern.test(text)) || nextPatterns.some((pattern) => pattern.test(ariaLabel))) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
        except Exception:
            return False
        return bool(advanced)

    def _advance_niche_pagination(self) -> bool:
        if not self.page:
            return False
        try:
            advanced = self.page.evaluate(
                """
                () => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                    };

                    const elements = Array.from(document.querySelectorAll('a, button'));
                    let currentPage = null;
                    for (const el of elements) {
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        const ariaCurrent = (el.getAttribute('aria-current') || '').toLowerCase();
                        if (/^\\d+$/.test(text) && ariaCurrent === 'page') {
                            currentPage = parseInt(text, 10);
                            break;
                        }
                    }

                    if (currentPage !== null) {
                        for (const el of elements) {
                            const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                            if (!/^\\d+$/.test(text)) continue;
                            const page = parseInt(text, 10);
                            if (page !== currentPage + 1) continue;
                            if (!isVisible(el)) continue;
                            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                            el.click();
                            return true;
                        }
                    }

                    const nextPatterns = [/^next$/i, /^next page$/i, /^>$/i];
                    for (const el of elements) {
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        const ariaLabel = (el.getAttribute('aria-label') || '').trim();
                        const rel = (el.getAttribute('rel') || '').toLowerCase();
                        if (!isVisible(el)) continue;
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                        if (rel === 'next' || nextPatterns.some((pattern) => pattern.test(text)) || nextPatterns.some((pattern) => pattern.test(ariaLabel))) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
        except Exception:
            return False
        return bool(advanced)

    def _scrape_forbes_paginated(self, url: str, wait_for_selector: Optional[str] = None) -> List[Dict[str, str]]:
        self._init_browser()
        collected: List[Dict[str, str]] = []
        seen = set()

        self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
        if wait_for_selector:
            self.page.wait_for_selector(wait_for_selector, state="attached", timeout=self.timeout * 1000)
        else:
            self.page.wait_for_load_state("networkidle", timeout=self.timeout * 1000)

        previous_signature = ""
        for _ in range(40):
            try:
                self.page.wait_for_load_state("networkidle", timeout=2500)
            except PlaywrightTimeoutError:
                pass
            self.page.wait_for_timeout(1200)

            soup = BeautifulSoup(self.page.content(), "html.parser")
            page_rows = self._extract_forbes_rankings(soup)
            for row in page_rows:
                name = row.get("RawName", "")
                rank = row.get("Rank", "")
                key = (rank, name.lower())
                if key in seen:
                    continue
                seen.add(key)
                collected.append({"Rank": rank, "RawName": name})

            logger.info(f"Forbes accumulated {len(collected)} rows")
            if len(collected) >= 500:
                break

            signature = self._forbes_table_signature()
            if signature and signature == previous_signature:
                logger.info("Forbes table signature stopped changing")
                break
            previous_signature = signature

            advanced = self._advance_forbes_pagination()
            if not advanced:
                break
            self.page.wait_for_timeout(1800)

        return self._dedupe(collected)

    def _is_forbes_paginated_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        return "forbes.com" in parsed.netloc.lower() and "top-colleges" in path and "/sites/" not in path

    def _mastersportal_page_url(self, base_url: str, page_number: int) -> str:
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        if page_number <= 1:
            query.pop("page", None)
        else:
            query["page"] = [str(page_number)]
        query_items = []
        for key, values in query.items():
            for value in values:
                query_items.append((key, value))
        return parsed._replace(query=urlencode(query_items)).geturl()

    def _niche_page_url(self, base_url: str, page_number: int) -> str:
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        if page_number <= 1:
            query.pop("page", None)
        else:
            query["page"] = [str(page_number)]
        query_items = []
        for key, values in query.items():
            for value in values:
                query_items.append((key, value))
        return parsed._replace(query=urlencode(query_items)).geturl()

    def _scrape_mastersportal_paginated(self, url: str, wait_for_selector: Optional[str] = None) -> List[Dict[str, str]]:
        aggregated: List[Dict[str, str]] = []
        seen_names = set()
        base_url = url

        for page_number in range(1, 5):
            page_url = self._mastersportal_page_url(base_url, page_number)
            logger.info(f"Fetching Mastersportal page: {page_url}")
            soup = self.fetch_page(page_url, wait_for_selector=wait_for_selector)
            if not soup:
                logger.warning("Mastersportal page fetch returned no soup")
                if page_number > 1:
                    break
                continue

            page_rows = self._extract_mastersportal_rankings(soup)
            added_this_page = 0
            for row in page_rows:
                name = row.get("RawName", "")
                key = name.lower()
                if key in seen_names:
                    continue
                seen_names.add(key)
                aggregated.append({"Rank": str(len(aggregated) + 1), "RawName": name})
                added_this_page += 1

            logger.info(f"Mastersportal added {added_this_page} rows from current page")
            if added_this_page == 0 and page_number > 1:
                logger.info("Mastersportal pagination stopped after an empty page")
                break

        return aggregated

    def _scrape_niche_paginated(self, url: str, wait_for_selector: Optional[str] = None) -> List[Dict[str, str]]:
        if self.use_browser:
            self._init_browser()
            collected: List[Dict[str, str]] = []
            seen = set()

            self.page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            if not self._ensure_niche_results_page(wait_for_selector):
                logger.warning("Niche initial page did not recover from transient errors")
                return []

            for _ in range(12):
                if not self._ensure_niche_results_page(wait_for_selector):
                    logger.warning("Niche page did not recover from transient errors during pagination")
                    break
                self._stabilize_niche_page()
                page_rows = self._extract_niche_rankings_from_page()
                if not page_rows:
                    soup = BeautifulSoup(self.page.content(), "html.parser")
                    page_rows = self._extract_niche_rankings(soup)
                added_this_page = 0
                for row in page_rows:
                    name = row.get("RawName", "")
                    if not name:
                        continue
                    key = str(row.get("URL", "")).strip().lower() or name.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append({"Rank": str(len(collected) + 1), "RawName": name})
                    added_this_page += 1

                logger.info(f"Niche added {added_this_page} rows from current browser page")
                advanced = self._advance_niche_pagination()
                if not advanced:
                    break
                self.page.wait_for_timeout(1500)

            return collected

        aggregated: List[Dict[str, str]] = []
        seen_names = set()
        base_url = url

        for page_number in range(1, 8):
            page_url = self._niche_page_url(base_url, page_number)
            logger.info(f"Fetching Niche page: {page_url}")
            soup = self.fetch_page(page_url, wait_for_selector=wait_for_selector)
            if not soup:
                logger.warning("Niche page fetch returned no soup")
                if page_number > 1:
                    break
                continue

            page_rows = self._extract_niche_rankings(soup)
            added_this_page = 0
            for row in page_rows:
                name = row.get("RawName", "")
                if not name:
                    continue
                key = name.lower()
                if key in seen_names:
                    continue
                seen_names.add(key)
                aggregated.append({"Rank": str(len(aggregated) + 1), "RawName": name})
                added_this_page += 1

            logger.info(f"Niche added {added_this_page} rows from current page")
            if added_this_page == 0 and page_number > 1:
                logger.info("Niche pagination stopped after an empty page")
                break

        return aggregated

    def _extract_niche_rankings(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = (a.get("href") or "").strip()
            href_lower = href.lower()
            if not re.search(r"^/colleges/[^/?#]+/?$", href_lower):
                continue
            name = self._clean_name(a.get_text(" ", strip=True))
            if not self._looks_like_niche_school_name(name):
                fallback_name = self._niche_name_from_href(href_lower)
                if self._looks_like_niche_school_name(fallback_name):
                    name = fallback_name
                else:
                    continue

            container = a
            container_text = ""
            rank = ""
            for _ in range(8):
                container = container.parent
                if container is None:
                    break
                if getattr(container, "name", "") not in {"li", "article", "section", "div", "tr"}:
                    continue
                text = container.get_text(" ", strip=True)
                if not text:
                    continue
                low = text.lower()
                rank_match = re.search(r"(?:^|\s)#\s*(\d{1,4})(?:\b|$)", text)
                if not rank_match:
                    rank_match = re.search(r"(?:^|\s)(\d{1,4})(?:\s|$)", text)
                if rank_match:
                    container_text = text
                    rank = self._normalize_rank(rank_match.group(1))
                    break
                if any(term in low for term in ["overall niche grade", "acceptance rate", "students"]):
                    container_text = text
                    break

            if container_text and not rank:
                rows.append({"Rank": "", "RawName": name})
            elif rank:
                rows.append({"Rank": rank, "RawName": name})
            else:
                # Some Niche result pages expose clean school profile links but omit a
                # nearby rank in the card text. Keep those links so we can assign
                # rank by page order instead of dropping the school entirely.
                rows.append({"Rank": "", "RawName": name})

        cleaned = self._dedupe(rows)
        if cleaned:
            return cleaned

        ordered: List[Dict[str, str]] = []
        seen = set()
        next_rank = 1
        for row in rows:
            name = row.get("RawName", "")
            if not self._looks_like_niche_school_name(name):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append({"Rank": str(next_rank), "RawName": name})
            next_rank += 1
        return self._dedupe(ordered)

    def _extract_princeton_rankings(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = (a.get("href") or "").strip()
            href_lower = href.lower()
            if not re.search(r"^/(school|college)/[^/?#]+", href_lower):
                continue
            name = self._clean_name(a.get_text(" ", strip=True))
            if not self._looks_like_princeton_school_name(name):
                continue

            container = a
            container_text = ""
            rank = ""
            for _ in range(8):
                container = container.parent
                if container is None:
                    break
                if getattr(container, "name", "") not in {"li", "article", "section", "div", "tr"}:
                    continue
                text = container.get_text(" ", strip=True)
                if not text:
                    continue
                low = text.lower()
                rank_match = re.search(r"(?:ranked\s*)#?\s*(\d{1,4})(?:\b|$)", text, re.IGNORECASE)
                if not rank_match:
                    rank_match = re.search(r"(?:^|\s)#\s*(\d{1,4})(?:\b|$)", text)
                if rank_match:
                    container_text = text
                    rank = self._normalize_rank(rank_match.group(1))
                    break
                if "save school" in low and any(term in low for term in ["tuition", "admissions", "student body"]):
                    container_text = text
                    break

            if container_text and not rank:
                rows.append({"Rank": "", "RawName": name})
            elif rank:
                rows.append({"Rank": rank, "RawName": name})

        cleaned = self._dedupe(rows)
        if cleaned:
            return cleaned

        ordered: List[Dict[str, str]] = []
        seen = set()
        next_rank = 1
        for row in rows:
            name = row.get("RawName", "")
            if not self._looks_like_princeton_school_name(name):
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append({"Rank": str(next_rank), "RawName": name})
            next_rank += 1
        return self._dedupe(ordered)

    def _filter_site_rows(self, url: str, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        if "usnews.com" in domain:
            return [r for r in rows if self._looks_like_usnews_school_name(r.get("RawName", ""))]
        if "princetonreview.com" in domain:
            return [r for r in rows if self._looks_like_princeton_school_name(r.get("RawName", ""))]
        if "niche.com" in domain:
            return [r for r in rows if self._looks_like_niche_school_name(r.get("RawName", ""))]
        if "mastersportal.com" in domain:
            return [r for r in rows if self._looks_like_mastersportal_school_name(r.get("RawName", ""))]
        return rows

    def _needs_headed_retry(self, url: str, rows: List[Dict[str, str]]) -> bool:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        if "usnews.com" in domain or "princetonreview.com" in domain:
            return len(rows) < 20
        return False

    def _dedupe(self, rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        seen = set()
        out: List[Dict[str, str]] = []
        for r in rows:
            rank = self._normalize_rank(r.get("Rank", ""))
            name = self._clean_name(r.get("RawName", ""))
            if not name or not self._looks_like_school_name(name):
                continue
            if not rank:
                continue
            key = (rank, name.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({"Rank": rank, "RawName": name})
        out.sort(key=lambda x: int(self._normalize_rank(x.get("Rank", "")) or 10**9))
        return out

    def _extract_by_rows(
        self,
        soup: BeautifulSoup,
        row_selectors: List[str],
        rank_selectors: List[str],
        name_selectors: List[str],
        max_rows: int = 1000,
    ) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for row_selector in row_selectors:
            rows = soup.select(row_selector)
            if not rows:
                continue
            for row in rows[:max_rows]:
                rank = ""
                name = ""

                for s in rank_selectors:
                    node = row.select_one(s)
                    if node:
                        rank = self._normalize_rank(node.get_text(" ", strip=True))
                        if rank:
                            break
                if not rank:
                    rank = self._normalize_rank(row.get_text(" ", strip=True))

                for s in name_selectors:
                    node = row.select_one(s)
                    if node:
                        candidate = self._clean_name(node.get_text(" ", strip=True))
                        if self._looks_like_school_name(candidate):
                            name = candidate
                            break
                if not name:
                    for a in row.find_all("a"):
                        candidate = self._clean_name(a.get_text(" ", strip=True))
                        if self._looks_like_school_name(candidate):
                            name = candidate
                            break

                if rank and name:
                    results.append({"Rank": rank, "RawName": name})
            if len(results) >= 20:
                break
        return self._dedupe(results)

    def _extract_by_links_with_context(
        self,
        soup: BeautifulSoup,
        href_patterns: List[str],
        assign_rank_by_order: bool = True,
        min_rank: int = 1,
        href_regex: Optional[str] = None,
        blocked_href_patterns: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        matches: List[Dict[str, str]] = []
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = (a.get("href") or "").lower()
            if not any(p in href for p in href_patterns):
                continue
            if blocked_href_patterns and any(p in href for p in blocked_href_patterns):
                continue
            if href_regex and not re.search(href_regex, href):
                continue
            name = self._clean_name(a.get_text(" ", strip=True))
            if not self._looks_like_school_name(name):
                continue

            container = a
            for _ in range(4):
                container = container.parent
                if container is None:
                    break
            container_text = container.get_text(" ", strip=True) if container else ""
            rank_match = re.search(r"(?:^|\s)(?:#|rank\s*)?(\d{1,4})(?:\s|$)", container_text, re.IGNORECASE)
            rank = self._normalize_rank(rank_match.group(1)) if rank_match else ""
            matches.append({"Rank": rank, "RawName": name})

        if assign_rank_by_order:
            ordered = []
            seen_names = set()
            next_rank = min_rank
            for m in matches:
                name_key = m["RawName"].lower()
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)
                # Document order is the rank order; container-derived rank often
                # picks a spurious "1" (e.g. Forbes tab labels) for every row.
                ordered.append({"Rank": str(next_rank), "RawName": m["RawName"]})
                next_rank += 1
            return self._dedupe(ordered)

        return self._dedupe(matches)

    def _extract_profile_cards(
        self,
        soup: BeautifulSoup,
        href_regex: str,
        required_container_terms: Optional[List[str]] = None,
        assign_rank_by_order_when_missing: bool = True,
        min_rows: int = 10,
    ) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = (a.get("href") or "").lower()
            if not re.search(href_regex, href):
                continue
            name = self._clean_name(a.get_text(" ", strip=True))
            if not self._looks_like_school_name(name):
                continue

            container = a
            for _ in range(7):
                container = container.parent
                if container is None:
                    break
                if getattr(container, "name", "") in {"li", "tr", "article", "section", "div"}:
                    text = container.get_text(" ", strip=True)
                    if required_container_terms:
                        low = text.lower()
                        if not all(term in low for term in required_container_terms):
                            continue
                    rank_match = re.search(r"(?:^|\s)#?\s*(\d{1,4})(?:\s|$)", text)
                    rank = self._normalize_rank(rank_match.group(1)) if rank_match else ""
                    rows.append({"Rank": rank, "RawName": name})
                    break

        cleaned = self._dedupe(rows)
        if not cleaned:
            return []

        if assign_rank_by_order_when_missing and any(not r.get("Rank") for r in rows):
            ordered = []
            seen = set()
            next_rank = 1
            for r in cleaned:
                key = r["RawName"].lower()
                if key in seen:
                    continue
                seen.add(key)
                rank = r["Rank"] if r["Rank"] else str(next_rank)
                ordered.append({"Rank": rank, "RawName": r["RawName"]})
                next_rank += 1
            cleaned = self._dedupe(ordered)

        return cleaned if len(cleaned) >= min_rows else []

    def _extract_from_scripts(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []

        def walk(node):
            if isinstance(node, dict):
                keys = {str(k).lower().replace("_", "").replace("-", ""): v for k, v in node.items()}
                rank = ""
                name = ""
                for k, v in keys.items():
                    if any(t in k for t in ["rank", "position", "overallrank"]):
                        rank = self._normalize_rank(str(v))
                    if any(t in k for t in ["schoolname", "institutionname", "displayname", "name", "title"]):
                        candidate = self._clean_name(str(v))
                        if self._looks_like_school_name(candidate):
                            name = candidate
                if rank and name:
                    results.append({"Rank": rank, "RawName": name})
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for script in soup.find_all("script"):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            payload = None
            if script.get("type") == "application/ld+json":
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = None
            else:
                if "__NEXT_DATA__" in raw or "__PRELOADED_STATE__" in raw or "rank" in raw.lower():
                    match = re.search(r"=\s*({.*})\s*;?\s*$", raw, flags=re.DOTALL)
                    if match:
                        try:
                            payload = json.loads(match.group(1))
                        except Exception:
                            payload = None
                    else:
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            payload = None
            if payload is not None:
                walk(payload)

        return self._dedupe(results)

    def _extract_usnews_from_scripts(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []

        def walk(node):
            if isinstance(node, dict):
                keys = {str(k).lower(): v for k, v in node.items()}
                name = ""
                rank = ""
                for k, v in keys.items():
                    if isinstance(v, (str, int, float)):
                        if any(t in k for t in ["schoolname", "institutionname", "displayname"]):
                            candidate = self._clean_name(str(v))
                            if self._looks_like_usnews_school_name(candidate):
                                name = candidate
                        if any(t in k for t in ["rank", "position", "sortrank", "displayrank", "ranking"]):
                            candidate_rank = self._normalize_rank(str(v))
                            if candidate_rank:
                                rank = candidate_rank
                if name and rank:
                    rows.append({"Rank": rank, "RawName": name})
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for script in soup.find_all("script"):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            if "usnews" not in raw.lower() and "best-colleges" not in raw.lower() and "school" not in raw.lower():
                continue

            payload = None
            if script.get("type") == "application/ld+json":
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = None
            if payload is None:
                match = re.search(r"=\s*({.*})\s*;?\s*$", raw, flags=re.DOTALL)
                if match:
                    try:
                        payload = json.loads(match.group(1))
                    except Exception:
                        payload = None
                else:
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        payload = None

            if payload is not None:
                walk(payload)

        cleaned = self._dedupe(rows)
        if cleaned:
            return cleaned

        # Last resort: assign rank by order from school links.
        return self._extract_by_links_with_context(soup, ["/best-colleges/"], assign_rank_by_order=True)

    def scrape_generic_table(self, soup: BeautifulSoup, table_selector: str) -> List[Dict[str, str]]:
        data = []
        try:
            table = soup.select_one(table_selector)
            if not table:
                logger.warning(f"Table not found with selector: {table_selector}")
                return data

            headers = []
            header_row = table.find("thead")
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all("th")]
            else:
                first_row = table.find("tr")
                if first_row:
                    headers = [td.get_text(strip=True) for td in first_row.find_all(["th", "td"])]

            rows = table.find_all("tr")[1:]
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) == len(headers) and headers:
                    row_data = {headers[i]: cells[i].get_text(strip=True) for i in range(len(headers))}
                    data.append(row_data)

            logger.info(f"Scraped {len(data)} rows from table")
            return data
        except Exception as e:
            logger.error(f"Error parsing table: {e}")
            return data

    def scrape_generic_lists(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        data: List[Dict[str, str]] = []

        data.extend(self._scrape_json_ld_itemlist(soup))
        if data:
            return self._dedupe(data)

        for ol in soup.find_all("ol"):
            items = ol.find_all("li", recursive=False) or ol.find_all("li")
            for idx, li in enumerate(items, 1):
                name = self._extract_name_from_node(li)
                if self._looks_like_school_name(name):
                    data.append({"Rank": str(idx), "RawName": self._clean_name(name)})
            if data:
                return self._dedupe(data)

        ranked = soup.select("[data-rank]")
        for node in ranked:
            rank = self._normalize_rank(str(node.get("data-rank", "")).strip())
            name = self._clean_name(self._extract_name_from_node(node))
            if rank and self._looks_like_school_name(name):
                data.append({"Rank": rank, "RawName": name})
        if data:
            return self._dedupe(data)

        return self._dedupe(self._scrape_rank_name_pairs(soup))

    def _scrape_json_ld_itemlist(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                payload = json.loads(script.string or "")
            except Exception:
                continue
            items = []
            if isinstance(payload, dict):
                if payload.get("@type") == "ItemList":
                    items = payload.get("itemListElement", []) or []
                elif "itemListElement" in payload:
                    items = payload.get("itemListElement", []) or []
            elif isinstance(payload, list):
                for obj in payload:
                    if isinstance(obj, dict) and obj.get("@type") == "ItemList":
                        items.extend(obj.get("itemListElement", []) or [])
            for entry in items:
                if isinstance(entry, dict):
                    rank = self._normalize_rank(str(entry.get("position") or entry.get("rank") or ""))
                    item = entry.get("item", {})
                    name = ""
                    if isinstance(item, dict):
                        name = self._clean_name(item.get("name") or "")
                    elif isinstance(item, str):
                        name = self._clean_name(item)
                    if rank and self._looks_like_school_name(name):
                        results.append({"Rank": rank, "RawName": name})
        return self._dedupe(results)

    def _extract_name_from_node(self, node) -> str:
        for tag in node.find_all(["h1", "h2", "h3", "h4", "strong", "b", "a"], limit=5):
            text = tag.get_text(strip=True)
            if text:
                return text
        return node.get_text(" ", strip=True)

    def _scrape_rank_name_pairs(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        text_nodes = soup.find_all(string=True)
        for node in text_nodes:
            text = node.strip()
            if not text:
                continue
            if re.match(r"^#?\d{1,4}$", text) or re.match(r"^T?\d{1,4}$", text, re.IGNORECASE):
                parent = node.parent
                if parent:
                    name = self._clean_name(self._extract_name_from_node(parent))
                    rank = self._normalize_rank(text.lstrip("#"))
                    if rank and self._looks_like_school_name(name) and name != text:
                        results.append({"Rank": rank, "RawName": name})
            if len(results) >= 2000:
                break
        return results

    def _scrape_site_specific(self, url: str, soup: BeautifulSoup) -> List[Dict[str, str]]:
        domain = urlparse(url).netloc.lower().replace("www.", "")

        if "forbes.com" in domain:
            if self._is_forbes_paginated_url(url):
                return self._extract_forbes_rankings(soup)
            path_l = urlparse(url).path.lower()
            if "value-colleges" in path_l:
                table_out = self._extract_forbes_rankings(soup)
                if len(table_out) >= 50:
                    return table_out
            out = self._extract_forbes_article_rankings(soup)
            if out:
                return out

        if "usnews.com" in domain:
            out = self._extract_profile_cards(
                soup,
                href_regex=r"/best-colleges/[^/?#]+-\d+",
                required_container_terms=None,
                assign_rank_by_order_when_missing=True,
                min_rows=10,
            )
            if out:
                out = self._filter_site_rows(url, out)
                if len(out) >= 10:
                    return out
            out = self._extract_by_rows(
                soup,
                row_selectors=["article", "tr", "li", "[data-test*='ranking']", "[class*='ranking']"],
                rank_selectors=["[data-test*='rank']", "[class*='rank']", "td:nth-child(1)", "strong"],
                name_selectors=["a[href*='/best-colleges/']"],
            )
            out = self._filter_site_rows(url, out)
            if len(out) >= 10:
                return out
            out = self._extract_usnews_from_scripts(soup)
            if out:
                return out
            out = self._extract_by_links_with_context(
                soup,
                ["/best-colleges/"],
                assign_rank_by_order=True,
                href_regex=r"/best-colleges/[^/?#]+-\d+",
                blocked_href_patterns=["/rankings", "/articles", "/advice", "/methodology", "/news"],
            )
            if len(out) >= 10:
                return out

        if "princetonreview.com" in domain:
            out = self._extract_princeton_rankings(soup)
            if out:
                out = self._filter_site_rows(url, out)
                if len(out) >= 10:
                    return out
            out = self._extract_by_rows(
                soup,
                row_selectors=["li", "article", "tr", "[class*='ranking']"],
                rank_selectors=["[class*='rank']", "strong", "td:nth-child(1)"],
                name_selectors=["a[href*='/school/']", "a[href*='/college/']"],
            )
            out = self._filter_site_rows(url, out)
            if len(out) >= 10:
                return out
            out = self._extract_by_links_with_context(
                soup,
                ["/school/", "/college/"],
                assign_rank_by_order=True,
                blocked_href_patterns=["/rankings/", "/blog/", "/advice/", "/news/"],
            )
            out = self._filter_site_rows(url, out)
            if len(out) >= 10:
                return out

        if "niche.com" in domain:
            out = self._extract_niche_rankings(soup)
            if out:
                out = self._filter_site_rows(url, out)
                if len(out) >= 10:
                    return out
            out = self._extract_by_rows(
                soup,
                row_selectors=["article", "li", "[data-testid*='search-result']", "[class*='search-result']"],
                rank_selectors=["[class*='rank']", "[data-testid*='rank']", "strong"],
                name_selectors=["a[href*='/colleges/']"],
            )
            out = self._filter_site_rows(url, out)
            if len(out) >= 10:
                return out
            out = self._extract_by_links_with_context(
                soup,
                ["/colleges/"],
                assign_rank_by_order=True,
                href_regex=r"/colleges/[^/?#]+/?$",
                blocked_href_patterns=["/rankings/", "/search/", "/admissions/", "/majors/"],
            )
            out = self._filter_site_rows(url, out)
            if len(out) >= 10:
                return out
            return []

        if "mastersportal.com" in domain:
            out = self._extract_mastersportal_rankings(soup)
            if out:
                out = self._filter_site_rows(url, out)
                if len(out) >= 10:
                    return out
            return []

        if "topuniversities.com" in domain:
            out = self._extract_by_rows(
                soup,
                row_selectors=["tr", "[class*='ranking-data-row']", "[class*='rankings-table'] tr"],
                rank_selectors=["[class*='rank']", "td:nth-child(1)"],
                name_selectors=["[class*='institution']", "[class*='uni']", "td:nth-child(2)", "a"],
            )
            if out:
                return out

        if "timeshighereducation.com" in domain:
            out = self._extract_by_rows(
                soup,
                row_selectors=["tr", "[class*='table-row']", "[class*='ranking-institution-row']", "[class*='ranking-data-row']"],
                rank_selectors=["[class*='rank']", "td:nth-child(1)", "th:nth-child(1)"],
                name_selectors=["a", "[class*='institution'] a", "[class*='institution'] span", "td:nth-child(2) a", "td:nth-child(2)"],
            )
            if out:
                return out

        if "shanghairanking.com" in domain or "arwu.org" in domain:
            out = self._extract_by_rows(
                soup,
                row_selectors=["table tr", "tr"],
                rank_selectors=["td:nth-child(1)", "[class*='rank']"],
                name_selectors=["td:nth-child(2)", "[class*='name']", "a"],
            )
            if out:
                return out

        if "collegeconsensus.com" in domain:
            out = self._extract_by_rows(
                soup,
                row_selectors=["li", "article", "[class*='ranking']"],
                rank_selectors=["[class*='rank']", "strong"],
                name_selectors=["[class*='school']", "[class*='name']", "h2, h3", "a"],
            )
            if out:
                return out

        return []

    def scrape_college_data(
        self,
        url: str,
        table_selector: Optional[str] = None,
        college_name_selector: Optional[str] = None,
        rank_selector: Optional[str] = None,
        wait_for_selector: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        if self.use_browser and "forbes.com" in domain and self._is_forbes_paginated_url(url):
            rows = self._scrape_forbes_paginated(url, wait_for_selector=wait_for_selector)
            if rows:
                logger.info(f"Forbes paginator returned {len(rows)} rows")
            else:
                logger.warning("Forbes paginator returned no rows")
            return rows
        if self.use_browser and "mastersportal.com" in domain:
            rows = self._scrape_mastersportal_paginated(url, wait_for_selector=wait_for_selector)
            rows = self._filter_site_rows(url, rows)
            if rows:
                logger.info(f"Mastersportal paginator returned {len(rows)} rows")
            else:
                logger.warning("Mastersportal paginator returned no rows")
            return rows
        if self.use_browser and "niche.com" in domain:
            rows = self._scrape_niche_paginated(url, wait_for_selector=wait_for_selector)
            rows = self._filter_site_rows(url, rows)
            if rows:
                logger.info(f"Niche paginator returned {len(rows)} rows")
                return rows
            logger.warning("Niche paginator returned no rows; falling back to single-page extraction")

        soup = self.fetch_page(url, wait_for_selector=wait_for_selector)
        if not soup:
            return []

        # 1) Site-specific path
        site_rows = self._scrape_site_specific(url, soup)
        if site_rows:
            site_rows = self._filter_site_rows(url, site_rows)
            logger.info(f"Site-specific extractor returned {len(site_rows)} rows")
            return site_rows

        domain = urlparse(url).netloc.lower().replace("www.", "")
        if "niche.com" in domain:
            logger.warning("Niche extractor found no trustworthy ranking rows; skipping generic fallback")
            return []

        # 2) Requested table path
        if table_selector:
            table_rows = self.scrape_generic_table(soup, table_selector)
            normalized = []
            for row in table_rows:
                rank = ""
                name = ""
                for key, value in row.items():
                    k = str(key).lower()
                    if not rank and ("rank" in k or k.strip() == "#"):
                        rank = self._normalize_rank(str(value))
                    if not name and any(t in k for t in ["college", "school", "institution", "university", "name"]):
                        name = self._clean_name(str(value))
                if rank and self._looks_like_school_name(name):
                    normalized.append({"Rank": rank, "RawName": name})
            if normalized:
                return self._dedupe(normalized)
            return table_rows

        # 3) Custom selector path
        colleges = []
        if college_name_selector and rank_selector:
            names = soup.select(college_name_selector)
            ranks = soup.select(rank_selector)
            for name, rank in zip(names, ranks):
                colleges.append({"Rank": self._normalize_rank(rank.get_text(strip=True)), "RawName": self._clean_name(name.get_text(strip=True))})
            cleaned = self._dedupe(colleges)
            if cleaned:
                return cleaned

        # 4) Fallbacks
        fallback_rows: List[Dict[str, str]] = []
        fallback_rows.extend(self.scrape_generic_lists(soup))
        fallback_rows.extend(self._extract_from_scripts(soup))
        fallback_rows.extend(self._extract_by_links_with_context(soup, ["/college", "/universit"], assign_rank_by_order=True))

        cleaned_fallback = self._dedupe(fallback_rows)
        if cleaned_fallback:
            logger.info(f"Fallback extractors returned {len(cleaned_fallback)} rows")
        else:
            logger.warning("No rankings data found after all extractors")
        return cleaned_fallback

    def close(self):
        if hasattr(self, "session"):
            self.session.close()
        if self.page:
            self.page.close()
            self.page = None
        if self.browser:
            self.browser.close()
            self.browser = None
            logger.info("Playwright browser closed")
        if self.playwright:
            self.playwright.stop()
            self.playwright = None


def scrape_college_website(
    url: str,
    use_browser: bool = False,
    use_selenium: Optional[bool] = None,
    **kwargs,
) -> List[Dict[str, str]]:
    headless = kwargs.pop("headless", True)
    timeout = kwargs.pop("timeout", 12)
    usnews_soft_target = kwargs.pop("usnews_soft_target", None)
    if use_selenium is not None:
        use_browser = use_selenium
    scraper = CollegeRankingScraper(timeout=timeout, use_browser=use_browser, headless=headless)
    if usnews_soft_target is not None:
        scraper.usnews_soft_target = usnews_soft_target
    try:
        rows = scraper.scrape_college_data(url, **kwargs)
    finally:
        scraper.close()
    if use_browser and headless:
        retry_scraper = CollegeRankingScraper(timeout=timeout, use_browser=use_browser, headless=False)
        if usnews_soft_target is not None:
            retry_scraper.usnews_soft_target = usnews_soft_target
        try:
            filtered_rows = retry_scraper._filter_site_rows(url, rows)
            if retry_scraper._needs_headed_retry(url, filtered_rows):
                logger.info("Retrying in headed mode for site compatibility")
                retry_rows = retry_scraper.scrape_college_data(url, **kwargs)
                retry_rows = retry_scraper._filter_site_rows(url, retry_rows)
                if retry_rows:
                    return retry_rows
        finally:
            retry_scraper.close()
    return rows


def get_rankings(
    url: str,
    use_browser: bool = True,
    use_selenium: Optional[bool] = None,
    **kwargs,
) -> List[Dict[str, str]]:
    logger.info(f"Getting rankings from: {url}")
    try:
        if use_selenium is not None:
            use_browser = use_selenium
        data = scrape_college_website(url, use_browser=use_browser, **kwargs)
        if data:
            logger.info(f"Successfully retrieved {len(data)} college rankings")
        else:
            logger.warning("No rankings data found")
        return data
    except Exception as e:
        logger.error(f"Error getting rankings from {url}: {e}")
        return []


if __name__ == "__main__":
    url = "https://www.forbes.com/top-colleges/"
    data = scrape_college_website(
        url,
        use_browser=True,
        wait_for_selector="table",
        table_selector="table",
    )

    print(f"Scraped {len(data)} colleges:")
    for college in data[:5]:
        print(college)
