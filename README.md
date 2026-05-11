# tcurl — T Cloud Public API Client

A CLI tool and Python module for making REST API calls to
[T Cloud Public](https://t-cloud-public.com/) endpoints.

Supports bearer token, AK/SK (SDK-HMAC-SHA256), and metadata server
authentication.

It is more of a tool to use for creating integration scripts
rather than outright application.

## Requirements

- Python 3.10+
- `requests` library
- Optional: `icecream` (debug logging, falls back gracefully)
- Optional: `pyyaml` (YAML output format)

## Installation

```bash
pip install requests
# Optional:
pip install icecream pyyaml
```

## Usage

```
python tcurl.py [global-opts] <command> [command-opts]
```

### Global options

| Option | Description |
|---|---|
| `-v`, `--verbose` | Show additional information |
| `-V`, `--version` | Show version and exit |

### Commands

#### Authentication

| Command | Description |
|---|---|
| `login` | Issue a bearer token (password or unscoped token exchange) |
| `logout` | Revoke a previously issued token |

#### Credential retrieval

| Command | Description |
|---|---|
| `metadata` | Retrieve temporary AK/SK from the metadata server |
| `aksk` | Issue temporary AK/SK credentials from a bearer token |

#### REST API calls

| Command | Description |
|---|---|
| `get` | Make a GET request |
| `post` | Make a POST request (requires body) |
| `put` | Make a PUT request (requires body) |
| `patch` | Make a PATCH request (requires body) |
| `delete` | Make a DELETE request |
| `head` | Make a HEAD request |
| `options` | Make an OPTIONS request |

### Output formats

Every command except `logout` supports the `--format` / `-f` option:

| Format | Description |
|---|---|
| `raw` | Space-joined values (default) |
| `json` | Pretty-printed JSON |
| `yaml` | YAML output (requires `pyyaml`) |
| `shell` | Shell `export` statements for sourcing |

## Authentication

Credentials are resolved in this order:

1. Command-line arguments
2. Metadata server (`http://169.254.169.254/openstack/latest/securitykey`)
3. Environment variables

### Bearer token

```bash
# Environment
export OS_AUTH_TOKEN=...
python tcurl.py get https://...

# Command line
python tcurl.py get --token=eyJ... https://...
```

### AK/SK (SDK-HMAC-SHA256)

```bash
# Environment
export OS_ACCESS_KEY=...
export OS_SECRET_KEY=...
export OS_SECURITY_TOKEN=...   # optional, for temp credentials

# Command line
python tcurl.py get --ak=... --sk=... https://...
```

When doing AK/SK calls, you can use the `--project-id` option to
scope calls to a specific project.

### Metadata server

```bash
# Fetch credentials first
eval $(python tcurl.py metadata --format shell)

# Then use them
python tcurl.py get https://...
```

Alternatively, pass `--metadata` directly to any REST verb:

```bash
python tcurl.py get --metadata https://...
```

### Login (issue a bearer token)

```bash
# Using username + password
python tcurl.py login --username=user@example.com --password=... --domain=OTC0000xxxx

# Exchange an unscoped token for a scoped one
python tcurl.py login --token=eyJ... --project=eu-de_project

# Scope to a region
python tcurl.py login --username=... --password=... --domain=... --region=eu-de
```

The login command outputs the token and expiry in the selected format
(`--format json` is recommended for inspection).

### Logout (revoke a token)

```bash
python tcurl.py logout eyJ...
```

### Temporary AK/SK

```bash
python tcurl.py aksk --maxage=3600 eyJ...
```

## Project layout

| Path | Description |
|---|---|
| `tcurl.py` | CLI tool and importable module |
| `tests/` | Test suite |
| `_attic/` | Archived scripts (not part of the project) |
| `DEVNOTES.md` | Developer notes |

## Use as a Python module

```python
from tcurl import creds, add_headers, metadata_config, OTCAkSkAuth

# Fetch credentials from metadata server
credential = metadata_config()
# => {'access': '...', 'secret': '...', 'securitytoken': '...', 'expires_at': '...'}

# Build request kwargs
kwargs = creds(token='eyJ...')
# => {'headers': {'X-Auth-Token': 'eyJ...'}}

# Or use AK/SK
kwargs = creds(ak='...', sk='...', securitytoken='...')
# => {'auth': OTCAkSkAuth(...)}

# Add custom headers
add_headers(kwargs, ['X-Request-Id:my-id'])

# Make the request
import requests
resp = requests.get('https://...', **kwargs)
```

## Notes

- The `--project` short flag (`-p`) in the `login` command refers to a
  **project name**, not a project ID.
- When using `--project` in `login`, the region is automatically derived
  from the project name (the part before the first `_`).
- All REST verb commands accept `get`, `post`, `put`, `patch`, `delete`,
  `head`, and `options` both in lowercase (e.g. `get`) and uppercase
  (e.g. `GET`).
- The tool supports reading arguments from a file using the `@` prefix
  (e.g. `python tcurl.py get @args.txt`).
