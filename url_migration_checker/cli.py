from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console
from rich.table import Table

from .checker import load_urls_from_csv, check_all, write_results

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="url-check",
        description="Check if URLs from a crawl export exist on a new domain.",
        epilog="Example: url-check urls.csv new.example.com -o results.csv",
    )
    parser.add_argument("input", help="CSV file with URLs to check (e.g. Screaming Frog export)")
    parser.add_argument("domain", help="New domain to check against (e.g. new.example.com)")
    parser.add_argument("-o", "--output", default="url_check_results.csv", help="Output CSV path (default: url_check_results.csv)")
    parser.add_argument("-c", "--column", default="Address", help="CSV column containing URLs (default: Address)")
    parser.add_argument("--concurrency", type=int, default=20, help="Max concurrent requests (default: 20)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    console.print(f"\n[bold]URL Migration Checker[/bold]")
    console.print(f"  Input:  {args.input}")
    console.print(f"  Domain: {args.domain}")
    console.print(f"  Output: {args.output}\n")

    try:
        urls = load_urls_from_csv(args.input, args.column)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] File not found: {args.input}")
        sys.exit(1)
    except KeyError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(f"Found [bold]{len(urls)}[/bold] URLs to check\n")

    results = asyncio.run(check_all(urls, args.domain, args.concurrency))
    write_results(results, args.output)

    found = sum(1 for r in results if r.exists)
    missing = len(results) - found

    table = Table(title="Results Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Total URLs", str(len(results)))
    table.add_row("Exist (2xx/3xx)", f"[green]{found}[/green]")
    table.add_row("Missing (4xx/5xx/err)", f"[red]{missing}[/red]")
    console.print(table)

    console.print(f"\n[bold green]Results saved to:[/bold green] {args.output}\n")


if __name__ == "__main__":
    main()
