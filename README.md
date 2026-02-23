# URL Migration Checker

Pre-launch tool for site migrations. Takes a crawl export (e.g. Screaming Frog `internal_all.csv`) and checks if each URL exists on the new domain — so you can verify coverage before DNS cutover.

## Quick Start

```bash
# Run directly with uv (no install needed)
uv run url-check crawl.csv new.example.com

# Or install it
uv sync
uv run url-check crawl.csv new.example.com
```

## Usage

```
url-check <input.csv> <new-domain> [options]
```

| Argument       | Description                                           |
| -------------- | ----------------------------------------------------- |
| `input.csv`    | CSV with URLs to check (Screaming Frog, Sitebulb, etc.) |
| `new-domain`   | Domain to check against (e.g. `staging.example.com`)  |
| `-o, --output` | Output CSV path (default: `url_check_results.csv`)    |
| `-c, --column` | Column name containing URLs (default: `Address`)      |
| `--concurrency`| Max parallel requests (default: `20`)                 |

## Examples

```bash
# Screaming Frog export → staging site
uv run url-check internal_all.csv staging.clientsite.com

# Custom column name and output path
uv run url-check export.csv new.example.com -c "URL" -o results.csv

# Throttle to 5 concurrent requests
uv run url-check urls.csv new.example.com --concurrency 5
```

## Output

Generates a CSV with columns:

| Column      | Description                              |
| ----------- | ---------------------------------------- |
| Old URL     | Original URL from the crawl              |
| New URL     | Remapped URL on the new domain           |
| Status Code | HTTP response code (200, 404, etc.)      |
| Status      | Human-readable status text               |
| Exists      | `Yes` / `No` for quick filtering         |

## Notes

- Uses `HEAD` requests for speed, falls back to `GET` if the server returns `405`
- Follows redirects automatically
- Skips SSL verification (useful for staging sites with self-signed certs)
- Works with any CSV that has a URL column — not limited to Screaming Frog
