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
# Core dependencies
pip install requests

# Optional:
pip install icecream pyyaml

# For interactive login (urwid-based TUI form):
pip install urwid
```

Or install via pip from source:

```bash
pip install .
```

This installs two console scripts:

| Command | Description |
|---|---|
| `tcurl` | Main CLI tool for API calls, credentials, etc. |
| `tcurl-login` | Interactive TUI login (username/password/OTP form) |

## Usage

```bash
# As a standalone script
python tcurl.py [global-opts] <command> [command-opts]

# Or using the installed console scripts:
tcurl [global-opts] <command> [command-opts]
tcurl-login [options]
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

When doing AK/SK calls, you can scope the request with any of these
mutually exclusive options:

| Option | Description |
|---|---|
| `--project-id` | Scope to a specific project ID |
| `--project-name` | Scope to a project by name |
| `--domain-id` | Scope to a specific domain ID |

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

You can also use a custom metadata URL with `--url`:

```bash
# In two steps
python tcurl.py metadata --url=http://custom.metadata/securitykey --format shell

# Or inline with any REST verb
python tcurl.py get --url=http://custom.metadata/securitykey https://...
```

### REST API call options

All REST verb commands (`get`, `post`, `put`, `patch`, `delete`, `head`, `options`)
accept these authentication options (mutually exclusive):

| Option | Description |
|---|---|
| `--token` / `-t` | Bearer token (or env `OS_AUTH_TOKEN` / `OS_TOKEN`) |
| `--ak` / `-a` | Access Key (or env `OS_ACCESS_KEY`) |
| `--sk` / `-s` | Secret Key (or env `OS_SECRET_KEY`) |
| `--securitytoken` / `-T` | Security token for temp credentials (or env `OS_SECURITY_TOKEN`) |
| `--metadata` / `-m` | Fetch credentials from the standard metadata endpoint |
| `--url` / `-U` | Fetch credentials from a custom metadata URL |

And these general options:

| Option | Description |
|---|---|
| `--header` / `-H` | Additional header in `Key:Value` format (repeatable) |
| `--format` / `-f` | Output format: `raw`, `json`, `yaml`, `shell` |

### Login (issue a bearer token)

```bash
# Using username + password
python tcurl.py login --username=user@example.com --password=... --domain=OTC0000xxxx

# Interactive (prompts for missing credentials via stdin)
python tcurl.py login --interactive

# Interactive with urwid-based TUI form (requires urwid)
tcurl-login

# Interactive with Virtual MFA OTP
python tcurl.py login --interactive --totp=123456

# Exchange an unscoped token for a scoped one
python tcurl.py login --token=eyJ... --project=eu-de_project

# Scope to a region
python tcurl.py login --username=... --password=... --domain=... --region=eu-de

# Custom auth URL
python tcurl.py login --username=... --password=... --domain=... --auth-url=https://iam.eu-de.otc.t-systems.com
```

Options:

| Option | Description |
|---|---|
| `--username` / `-u` | Username for password-based authentication |
| `--password` / `-P` | Password (or env `OS_PASSWORD`) |
| `--domain` / `-D` | User domain name, e.g. `OTC0000xxxx` (or env `OS_USER_DOMAIN_NAME`) |
| `--token` / `-t` | Unscoped token to exchange for a scoped one |
| `--project` / `-p` | Scope to a project name (derives region from prefix) |
| `--region` / `-R` | Scope to a region (or env `OS_TENANT_NAME`) |
| `--auth-url` / `-A` | Custom auth URL (or env `OS_AUTH_URL`) |
| `--interactive` / `-i` | Prompt for credentials interactively |
| `--totp` | Virtual MFA one-time passcode |

The login command outputs the token and expiry in the selected format
(`--format json` is recommended for inspection).

### Logout (revoke a token)

```bash
# Revoke a specific token
python tcurl.py logout eyJ...

# Revoke the token from the environment and export shell commands
python tcurl.py logout --shell
```

The `--shell` flag (or `--format shell`) outputs `export` statements suitable
for `eval`, clearing the `OS_AUTH_TOKEN` variable after revocation.

### Temporary AK/SK

```bash
# Issue temporary credentials valid for 15 minutes (default)
python tcurl.py aksk --token=eyJ...

# Custom duration (up to 24 hours = 86400 seconds)
python tcurl.py aksk --maxage=3600 --token=eyJ...

# Using environment variable for the token
export OS_AUTH_TOKEN=eyJ...
python tcurl.py aksk

# With a custom region or auth URL
python tcurl.py aksk --region=eu-de --maxage=7200
```

Options:

| Option | Description |
|---|---|
| `--token` / `-t` | Bearer token (or env `OS_AUTH_TOKEN` / `OS_TOKEN`) |
| `--maxage` / `-M` | Max lifetime in seconds (default: 900 / 15 min) |
| `--region` / `-R` | Region for auth URL (or env `OS_TENANT_NAME`) |
| `--auth-url` / `-A` | Custom auth URL (or env `OS_AUTH_URL`) |
| `--format` / `-f` | Output format: `raw`, `json`, `yaml`, `shell` |

The issued AK/SK will have the same permissions as the original bearer token.

## Project layout

| Path | Description |
|---|---|
| `tcurl.py` | CLI tool and importable module |
| `tcurl_login.py` | Interactive TUI login form (urwid-based) |
| `setup.py` | Package installer / distribution |
| `tests/` | Test scripts and examples |
| `docs/` | Sphinx documentation source |
| `_attic/` | Archived scripts (not part of the project) |
| `DEVNOTES.md` | Developer notes |

## Use as a Python module

`tcurl.py` and `tcurl_login.py` can be imported and used programmatically:

```python
from tcurl import (
    creds, add_headers, add_project_id, add_domain_id,
    metadata_config, resolve_auth_url,
    login, logout, temp_aksk,
    OTCAkSkAuth, OBSAuth,
)

# Resolve the IAM endpoint for a region
auth_url = resolve_auth_url(region='eu-de')
# => 'https://iam.eu-de.otc.t-systems.com'

# Fetch credentials from metadata server
credential = metadata_config()
# => {'access': '...', 'secret': '...', 'securitytoken': '...', 'expires_at': '...'}

# Build request kwargs
kwargs = creds(token='eyJ...')
# => {'headers': {'X-Auth-Token': 'eyJ...'}}

# Or use AK/SK
kwargs = creds(ak='...', sk='...', securitytoken='...')
# => {'auth': OTCAkSkAuth(...)}

# Scope an AK/SK request to a project
add_project_id(kwargs, 'eu-de_12345')
add_domain_id(kwargs, 'OTC0000xxxx')

# Add custom headers
add_headers(kwargs, ['X-Request-Id:my-id'])

# Make the request
import requests
resp = requests.get('https://...', **kwargs)

# Issue a bearer token programmatically
token, details = login(
    username='user@example.com',
    password='...',
    domain='OTC0000xxxx',
    project='eu-de_project',
)
# token => 'eyJ...'
# details => full JSON response from IAM

# Issue temporary AK/SK from a token
creds = temp_aksk(token='eyJ...', max_secs=3600)
# => {'access': '...', 'secret': '...', 'securitytoken': '...', 'expires_at': '...'}

# Revoke a token
logout(token='eyJ...')
```

The `tcurl_login` module provides an interactive urwid-based form:

```python
from tcurl_login import CredentialForm

form = CredentialForm()
result = form.run()
# => {'username': '...', 'password': '...', 'domain': '...', 'totp': '...'}
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
- Credential resolution order for REST verbs: command-line arguments →
  metadata server → environment variables.
- The `--region` and `--project` options on `login` are mutually exclusive.
  When `--project` is used, the region is derived from the project name prefix.
- The `--interactive` mode reads from stdin when running in a TTY, or silently
  from stdin when piped (useful for automation scripts).
- The `tcurl-login` console script (urwid-based TUI) requires `urwid`. It
  provides a dialog-style form with password masking and Tab navigation.
