from __future__ import annotations

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


@dataclass
class CheckResult:
    old_url: str
    new_url: str
    status_code: int | None
    status_text: str
    exists: bool


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


async def check_single(
    client: httpx.AsyncClient,
    old_url: str,
    new_domain: str,
    semaphore: asyncio.Semaphore,
) -> CheckResult:
    new_url = remap_url(old_url, new_domain)
    async with semaphore:
        try:
            resp = await client.head(new_url, follow_redirects=True)
            if resp.status_code == 405:
                resp = await client.get(new_url, follow_redirects=True)
            return CheckResult(
                old_url=old_url,
                new_url=new_url,
                status_code=resp.status_code,
                status_text=httpx.codes.get_reason_phrase(resp.status_code),
                exists=resp.status_code < 400,
            )
        except httpx.TimeoutException:
            return CheckResult(old_url, new_url, None, "Timeout", False)
        except Exception as e:
            return CheckResult(old_url, new_url, None, str(e)[:120], False)


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
            results: list[CheckResult] = []

            async def wrapped(url: str) -> CheckResult:
                result = await check_single(client, url, new_domain, semaphore)
                progress.advance(task)
                return result

            results = await asyncio.gather(*[wrapped(u) for u in urls])
    return list(results)


def write_results(results: list[CheckResult], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Old URL", "New URL", "Status Code", "Status", "Exists"])
        for r in results:
            writer.writerow([
                r.old_url,
                r.new_url,
                r.status_code or "Error",
                r.status_text,
                "Yes" if r.exists else "No",
            ])
