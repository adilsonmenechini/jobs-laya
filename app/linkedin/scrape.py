"""Pure HTML parsers for LinkedIn job pages.

Input is untrusted: everything extracted here is treated as plain text and is
never executed or interpolated into commands. Empty payloads signal a page we
could not understand (blocked, redesigned, or not a job page).
"""

import re

from bs4 import BeautifulSoup

JOB_ID_PATTERNS = (
    re.compile(r"/jobs/view/(\d{6,})"),
    re.compile(r"-(\d{6,})(?:[/?#]|$)"),
)
REMOTE_PATTERN = re.compile(r"\bremote\b|\bremoto\b", re.IGNORECASE)
CARD_SELECTOR = "li.base-search-card, div.base-card, li.reusable-search__result-container"
DESCRIPTION_HEADINGS = ("sobre a vaga", "about the job", "about the role", "descrição da vaga")
LOCATION_PATTERN = re.compile(
    r"<span>\s*([^<>]{2,80}?\s*\((?:Remoto|Remote|Híbrido|Hybrid|Presencial|On-site)\))\s*</span>",
    re.IGNORECASE,
)


def extract_job_id(url: str) -> str | None:
    """LinkedIn job URLs are either /jobs/view/123 or /jobs/view/slug-123."""
    for pattern in JOB_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def is_authwall(url: str, html: str) -> bool:
    lowered = url.lower()
    if "authwall" in lowered or "/login" in lowered or "/checkpoint/" in lowered:
        return True
    return 'id="login-email"' in html


def _first_text(root, *selectors: str) -> str | None:
    for selector in selectors:
        element = root.select_one(selector)
        if element:
            text = element.get_text(" ", strip=True)
            if text:
                return text
    return None


def _first_block(root, *selectors: str) -> str:
    for selector in selectors:
        element = root.select_one(selector)
        if element:
            text = element.get_text("\n", strip=True)
            if text:
                return text
    return ""


def parse_job_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select(CARD_SELECTOR):
        link = card.select_one("a[href*='/jobs/view/']")
        if link is None:
            continue
        url = link.get("href", "")
        job_id = extract_job_id(url)
        if not job_id:
            continue

        location = _first_text(
            card, ".job-search-card__location", ".artdeco-entity-subtitle__location"
        )
        time_element = card.select_one("time[datetime]")
        posted_at = (
            time_element.get("datetime") if time_element is not None else _first_text(card, "time")
        )
        title = _first_text(
            card, ".base-search-card__title", ".job-search-card__title", ".base-card__title"
        )
        items.append(
            {
                "job_id": job_id,
                "title": title,
                "company": _first_text(
                    card,
                    ".base-search-card__subtitle",
                    ".job-search-card__subtitle",
                    ".base-card__subtitle",
                ),
                "location": location,
                "remote": bool(location and REMOTE_PATTERN.search(location)),
                "url": url,
                "description": "",
                "posted_at": posted_at,
            }
        )
    return items


def _looks_like_job_page(soup, html: str = "", job_id: str = "") -> bool:
    canonical = soup.select_one("link[rel='canonical']")
    if canonical and "/jobs/view/" in (canonical.get("href") or ""):
        return True
    if soup.select_one(".job-details-jobs-unified-top-card__top-card, .topcard"):
        return True
    # Current markup: no canonical and hashed classes. The requested job id
    # appears in banner ids, and the description heading is stable across locales.
    if job_id and job_id in html:
        return True
    text = soup.get_text(" ", strip=True).lower()
    return any(heading in text for heading in DESCRIPTION_HEADINGS)


def _title_and_company_from_tag(soup) -> tuple[str | None, str | None]:
    """Current markup puts 'TITLE | COMPANY | LinkedIn' in the <title> tag."""
    if soup.title is None:
        return None, None
    text = re.sub(r"\s*\|\s*LinkedIn(\s+Jobs)?\s*$", "", soup.title.get_text(" ", strip=True))
    parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(parts) >= 2:
        return " | ".join(parts[:-1]), parts[-1]
    return (text or None), None


def _description_from_boxes(soup) -> str:
    """Description lives in a data-testid box, right after the heading."""
    heading = next(
        (
            element
            for element in soup.find_all(["h2", "h3"])
            if element.get_text(" ", strip=True).lower() in DESCRIPTION_HEADINGS
        ),
        None,
    )
    if heading is not None:
        box = heading.find_next(attrs={"data-testid": "expandable-text-box"})
        if box is not None:
            text = box.get_text("\n", strip=True)
            if len(text) > 50:
                return text
    boxes = soup.select('[data-testid="expandable-text-box"]')
    if boxes:
        longest = max(boxes, key=lambda element: len(element.get_text()))
        text = longest.get_text("\n", strip=True)
        if len(text) > 50:
            return text
    return _first_block(
        soup,
        ".jobs-description__content .jobs-box__html-content",
        ".jobs-description__content",
        ".show-more-less-html__markup",
        ".description__text",
    )


def _location_and_remote(soup, html: str) -> tuple[str | None, bool]:
    """Location chips like 'São Paulo, SP (Remoto)' appear before the heading."""
    lowered = html.lower()
    heading_pos = next(
        (lowered.find(heading) for heading in DESCRIPTION_HEADINGS if heading in lowered),
        len(html),
    )
    if heading_pos < 0:
        heading_pos = len(html)

    for match in LOCATION_PATTERN.finditer(html[:heading_pos]):
        location = match.group(1).strip()
        return location, bool(REMOTE_PATTERN.search(location))

    metadata = _first_text(
        soup,
        ".job-details-jobs-unified-top-card__tertiary-description-container",
        ".workplace-types-job-card__workplace-type",
        ".topcard__flavor",
    )
    remote = bool(metadata and REMOTE_PATTERN.search(metadata)) or bool(
        REMOTE_PATTERN.search(html[:heading_pos])
    )
    location = _first_text(
        soup,
        ".job-details-jobs-unified-top-card__tertiary-description-container span",
        ".topcard__flavor--bullet span",
    )
    return location, remote


def parse_job_detail(html: str, job_id: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    if not _looks_like_job_page(soup, html, job_id):
        return {}

    title_from_tag, company_from_tag = _title_and_company_from_tag(soup)
    title = (
        _first_text(
            soup,
            "h1.job-details-jobs-unified-top-card__job-title",
            "h1.topcard__title",
        )
        or title_from_tag
        or _first_text(soup, "h1")
    )
    if not title:
        return {}

    canonical = soup.select_one("link[rel='canonical']")
    url = (
        canonical.get("href")
        if canonical and canonical.get("href")
        else f"https://www.linkedin.com/jobs/view/{job_id}"
    )
    location, remote = _location_and_remote(soup, html)
    time_element = soup.select_one("time[datetime]")

    return {
        "job_id": job_id,
        "title": title,
        "company": _first_text(
            soup,
            ".job-details-jobs-unified-top-card__company-name a",
            ".job-details-jobs-unified-top-card__company-name",
            ".topcard__flavor a",
            ".topcard__org-company-name",
        )
        or company_from_tag,
        "location": location
        or _first_text(
            soup,
            ".job-details-jobs-unified-top-card__tertiary-description-container span",
            ".topcard__flavor--bullet span",
        ),
        "remote": remote,
        "url": url,
        "description": _description_from_boxes(soup),
        "posted_at": (
            time_element.get("datetime")
            if time_element is not None
            else _first_text(soup, ".posted-time-ago__text", ".jobs-unified-top-card__posted-date")
        ),
    }
