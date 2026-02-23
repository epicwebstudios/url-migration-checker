from __future__ import annotations

import re
import csv
import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn

console = Console()

MAX_CONCURRENT = 20
TIMEOUT = 15

NOT_FOUND_PATTERNS = [
    "page not found",
    "404 not found",
    "not found",
    "error 404",
    "the page you requested",
    "page doesn't exist",
    "page does not exist",
    "no longer available",
]

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass
class CheckResult:
    old_url: str
    new_url: str
    status_code: int | None
    status_text: str
    exists: bool
    page_title: str


def load_urls_from_csv(path: str, column: str = "Address") -> list[str]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        available = reader.fieldnames or []
        if column not in available:
            close_matches = [c for c in available if column.lower() in c.lower()]
            if close_matches:
                column = close_matches[0]
            else:
                raise KeyError(
                    f"Column '{column}' not found. Available: {', '.join(available)}"
                )
        return [row[column] for row in reader if row[column]]


def remap_url(old_url: str, new_domain: str, force_https: bool = True) -> str:
    parsed = urlparse(old_url)
    scheme = "https" if force_https else parsed.scheme
    return urlunparse(parsed._replace(scheme=scheme, netloc=new_domain))


def _extract_title(html: str) -> str:
    match = TITLE_RE.search(html)
    return match.group(1).strip() if match else ""


def _looks_like_not_found(title: str) -> bool:
    lower = title.lower()
    return any(pattern in lower for pattern in NOT_FOUND_PATTERNS)


def _is_html(content_type: str) -> bool:
    return "text/html" in content_type


async def check_single(
    client: httpx.AsyncClient,
    old_url: str,
    new_domain: str,
    semaphore: asyncio.Semaphore,
) -> CheckResult:
    new_url = remap_url(old_url, new_domain)
    async with semaphore:
        try:
            resp = await client.get(new_url, follow_redirects=True)
            code = resp.status_code
            content_type = resp.headers.get("content-type", "")
            title = ""
            is_soft_404 = False

            if _is_html(content_type):
                title = _extract_title(resp.text)
                is_soft_404 = _looks_like_not_found(title)

            # A page "exists" if it returns < 400, OR returns a page that
            # isn't a not-found page (handles servers that 404 everything).
            if code < 400:
                exists = not is_soft_404
            elif _is_html(content_type) and title and not is_soft_404:
                exists = True
            else:
                exists = False

            status_text = httpx.codes.get_reason_phrase(code)
            if is_soft_404:
                status_text = "Soft 404 (page says not found)"

            return CheckResult(old_url, new_url, code, status_text, exists, title)

        except httpx.TimeoutException:
            return CheckResult(old_url, new_url, None, "Timeout", False, "")
        except Exception as e:
            return CheckResult(old_url, new_url, None, str(e)[:120], False, "")


async def check_all(
    urls: list[str],
    new_domain: str,
    concurrency: int = MAX_CONCURRENT,
) -> list[CheckResult]:
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        verify=False,
        headers={"User-Agent": "Mozilla/5.0 (url-migration-checker)"},
    ) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Checking URLs", total=len(urls))

            async def wrapped(url: str) -> CheckResult:
                result = await check_single(client, url, new_domain, semaphore)
                progress.advance(task)
                return result

            results = await asyncio.gather(*[wrapped(u) for u in urls])
    return list(results)


def write_results(results: list[CheckResult], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Old URL", "New URL", "Status Code", "Status", "Exists", "Page Title"])
        for r in results:
            writer.writerow([
                r.old_url,
                r.new_url,
                r.status_code or "Error",
                r.status_text,
                "Yes" if r.exists else "No",
                r.page_title,
            ])
