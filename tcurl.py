#!/usr/bin/python3
'''
API call tool for T Cloud Public

This module provides functionality to perform REST API calls to
T Cloud Public endpoints.

It is presented as importable module or as a scriptable command line
utility.

It supports:

* Making REST API calls with:
  * bearer tokens
  * SDK-HMAC-SHA256
  * AK/SK AWS Signature V4

Expects authentication credentials to come from:

* command-line arguments
* metadata server
* environment variables

If used as Python library, caller must provide credentials as function
arguments.

Requirements:

- `requests` library (for HTTP client functionality)
- Optional: `icecream` (for debug logging, falls back gracefully)
- Optional: `pyyaml` (for YAML output format)

:seealso: T Cloud API documentation at https://docs.otc.t-systems.com/
'''

import argparse
import datetime
import hashlib
import hmac
import json
import os
import requests
import shlex
import sys

from requests.auth import AuthBase
from typing import Any
from urllib.parse import urlparse, quote, urlencode, parse_qsl

try:
  from icecream import ic
except ImportError:  # Graceful fallback if IceCream isn't installed.
  ic = lambda *a: None if not a else (a[0] if len(a) == 1 else a)  # noqa - returns None if no args, single arg if one, tuple otherwise

try:
  import yaml
  HAS_YAML = True
except ImportError:
  HAS_YAML = False

VERSION = '2026.05-DEV'
'''Module version'''
METADATA_URL = 'http://169.254.169.254/openstack/latest/securitykey'
'''T Cloud Public URL for Metadata service'''
VERBOSE = False
'''Show additional information'''
DEFAULT_REGION = 'eu-de'
'''If no region is specified, use this one'''

AUTH_URL = 'https://iam.{region}.otc.t-systems.com'
'''Format to generate IAM URL'''

def resolve_auth_url(region: str | None = None,
                     auth_url: str | None = None) -> str:
    '''Resolve the authentication URL from explicit value, environment, or region default.

    Looks up in this order:
      1. ``auth_url`` parameter (if provided)
      2. ``OS_AUTH_URL`` environment variable (if set and non-empty)
      3. Constructed from :data:`AUTH_URL` template using *region* (or :data:`DEFAULT_REGION`)

    :param region:   Region name used to construct the default URL
    :param auth_url: Explicit auth URL (takes highest priority)
    :returns: Resolved authentication base URL
    '''
    if auth_url is not None:
        return auth_url
    env_url = os.environ.get('OS_AUTH_URL')
    if env_url:
        return env_url
    return AUTH_URL.format(region=region if region is not None else DEFAULT_REGION)

class OTCAkSkAuth(AuthBase):
  '''
  OTC/Huawei Cloud SDK-HMAC-SHA256 request signer.

  Works with both permanent and temporary AK/SK credentials.
  Pass security_token when using temporary credentials from the metadata endpoint.

  :param ak: Access Key for authentication
  :param sk: Secret Key for signing requests
  :param security_token: Optional security token for temporary credentials
  '''

  def __init__(self, ak: str, sk: str, security_token: str|None = None) -> None:
    '''Initialize the OTC authentication handler.

    :param ak: Access Key
    :param sk: Secret Key
    :param security_token: Optional temporary security token
    '''
    self.ak = ak
    self.sk = sk
    self.security_token = security_token

  def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
    '''Sign a prepared request with SDK-HMAC-SHA256 signature.

    This method adds the required authentication headers including
    `X-Sdk-Date`, `X-Security-Token` (if applicable), and `Authorization`
    header with the computed signature.

    :param r: The prepared request to sign
    :return: The signed request with authentication headers
    '''
    # 1. Timestamp
    dt = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    r.headers['X-Sdk-Date'] = dt
    if self.security_token:
      r.headers['X-Security-Token'] = self.security_token

    # 2. Parse URL
    parsed = urlparse(r.url)
    # URI must end with / per spec, but trailing slash is not sent
    uri = quote(parsed.path or '/', safe='/-_.~')
    if not uri.endswith('/'):
      uri = uri + '/'

    # Canonical query string: sort params alphabetically
    query_params = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    canonical_query = urlencode(query_params)

    # 3. Build headers to sign
    # Must include host and x-sdk-date; include x-security-token if present
    host = parsed.netloc
    headers_to_sign = {
      'host': host,
      'x-sdk-date': dt,
    }
    # Only include content-type if actually set on the request
    ct = r.headers.get('Content-Type', '')
    if ct:
      headers_to_sign['content-type'] = ct
    if self.security_token:
      headers_to_sign['x-security-token'] = self.security_token

    # Sorted alphabetically
    sorted_headers = sorted(headers_to_sign.items())
    canonical_headers = ''.join(f'{k}:{v}\n' for k, v in sorted_headers)
    signed_headers = ';'.join(k for k, _ in sorted_headers)

    # 4. Hash the request body
    body = r.body or b''
    if isinstance(body, str):
      body = body.encode('utf-8')
    payload_hash = hashlib.sha256(body).hexdigest()

    # 5. Canonical request
    canonical_request = '\n'.join([
      r.method.upper(),
      uri,
      canonical_query,
      canonical_headers,
      signed_headers,
      payload_hash,
    ])

    # 6. String to sign — NOTE: no credential scope, just 3 fields
    hashed_cr = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
    string_to_sign = f'SDK-HMAC-SHA256\n{dt}\n{hashed_cr}'

    # 7. Signature — SK used DIRECTLY, no key derivation chain
    signature = hmac.new(
      self.sk.encode('utf-8'),
      string_to_sign.encode('utf-8'),
      hashlib.sha256
    ).hexdigest()

    # 8. Authorization header
    r.headers['Authorization'] = (
      f'SDK-HMAC-SHA256 Access={self.ak}, '
      f'SignedHeaders={signed_headers}, Signature={signature}'
    )
    return r

# ====================================================================
# AWS Signature V4 signer  (for OBS / S3-compatible API)
# ====================================================================

_SERVICE = 's3'
_ALGORITHM = 'AWS4-HMAC-SHA256'

def _sha256_hex(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest()

def _hmac_sha256(key: bytes, msg: bytes | str) -> bytes:
  if isinstance(msg, str):
    msg = msg.encode('utf-8')
  return hmac.new(key, msg, hashlib.sha256).digest()

def _signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
  '''Derive the AWS Signature V4 signing key.'''
  k_secret = ('AWS4' + secret_key).encode('utf-8')
  k_date = _hmac_sha256(k_secret, date_stamp)
  k_region = _hmac_sha256(k_date, region)
  k_service = _hmac_sha256(k_region, _SERVICE)
  return _hmac_sha256(k_service, 'aws4_request')

class OBSAuth(AuthBase):
  '''AWS Signature V4 request signer for OBS (S3-compatible API).

  Supports both permanent and temporary (STS) credentials.

  :param ak:             Access Key
  :param sk:             Secret Key
  :param region:         OBS region (e.g. ``'eu-de'``)
  :param security_token: Optional temporary security token (from IAM)
  '''

  def __init__(self, ak: str, sk: str, region: str,
               security_token: str | None = None) -> None:
    self.ak = ak
    self.sk = sk
    self.region = region
    self.security_token = security_token

  def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
    # 1. Timestamps
    now = datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = now.strftime('%Y%m%d')

    r.headers['X-Amz-Date'] = amz_date
    if self.security_token:
      r.headers['X-Amz-Security-Token'] = self.security_token

    # 2. Payload hash
    body = r.body or b''
    if isinstance(body, str):
      body = body.encode('utf-8')
    payload_hash = _sha256_hex(body)
    r.headers['X-Amz-Content-Sha256'] = payload_hash

    # 3. Canonical URI
    parsed = urlparse(r.url)
    uri = quote(parsed.path or '/', safe='/-_.~')

    # 4. Canonical query string
    query_params = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    canonical_query = urlencode(query_params)

    # 5. Canonical headers (sorted, lowercase keys)
    host = parsed.netloc
    headers_to_sign = {
        'host': host,
        'x-amz-content-sha256': payload_hash,
        'x-amz-date': amz_date,
    }
    if self.security_token:
      headers_to_sign['x-amz-security-token'] = self.security_token

    # Also pick up content-type if set
    ct = r.headers.get('Content-Type', '')
    if ct:
      headers_to_sign['content-type'] = ct

    sorted_headers = sorted(headers_to_sign.items())
    canonical_headers = ''.join(f'{k}:{v}\n' for k, v in sorted_headers)
    signed_headers = ';'.join(k for k, _ in sorted_headers)

    # 6. Canonical request
    canonical_request = '\n'.join([
        r.method.upper(),
        uri,
        canonical_query,
        canonical_headers,
        signed_headers,
        payload_hash,
    ])

    # 7. String to sign
    credential_scope = f'{date_stamp}/{self.region}/{_SERVICE}/aws4_request'
    hashed_cr = _sha256_hex(canonical_request.encode('utf-8'))
    string_to_sign = '\n'.join([
        _ALGORITHM,
        amz_date,
        credential_scope,
        hashed_cr,
    ])

    # 8. Signature
    s_key = _signing_key(self.sk, date_stamp, self.region)
    signature = hmac.new(
        s_key, string_to_sign.encode('utf-8'), hashlib.sha256
    ).hexdigest()

    # 9. Authorization header
    r.headers['Authorization'] = (
        f'{_ALGORITHM} Credential={self.ak}/{credential_scope}, '
        f'SignedHeaders={signed_headers}, Signature={signature}'
    )
    return r



def metadata_config(url: str = METADATA_URL) -> dict[str,str]:
  '''Retrieve credentials from the metadata server.

  Fetches temporary AK/SK credentials and security token from the
  OpenStack metadata service endpoint.

  :param url: URL to metadata server (defaults to METADATA_URL)
  :returns: dictionary containing access, secret, securitytoken and expires_at
  :raises requests.exceptions.RequestException: If metadata server unreachable
  '''
  ic(url)
  response = requests.get(url)
  response.raise_for_status()
  data = response.json()
  return data['credential']

def get_nested_value(path_string:str, nested_dict:dict) -> Any:
  '''
  Retrieve a value from a deeply nested dictionary using a dot-separated path.

  :param path_string: A string with dot-separated keys, e.g., 'something.or.other'
  :param nested_dict: A deeply nested dictionary
  :returns: The value at the specified path
  :raises KeyError: If any key in the path doesn't exist
  :raises TypeError: If a path segment leads to a non-dict value
  '''
  keys = path_string.split('.')
  current = nested_dict
  for key in keys:
    current = current[key]
  return current

def add_format_args(parser:argparse.ArgumentParser) -> None:
  '''Add the --format option to a parser

  :param parser: parser to add the argument to
  :returns: None (modifies the parser in place)
  '''
  formats = ['raw','json','shell']
  if HAS_YAML: formats.append('yaml')
  parser.add_argument('--format', '-f',
                    dest = 'output',
                    default = 'raw',
                    choices = formats,
                    help = 'Output format: %(choices)s (default: %(default)s)')

def parser_factory() -> argparse.ArgumentParser:
  '''Create and configure the command-line argument parser.

  :return: Configured argument parser for the T Cloud Public API call tool
  '''
  parser = argparse.ArgumentParser(
    prog='tcurl.py',
    description='Call T Cloud Public API',
    epilog='Works with Permanent and Temporary AK/SK pairs as well as bearer tokens',
    fromfile_prefix_chars='@',
    allow_abbrev=True,
  )
  parser.add_argument('--verbose', '-v', action='store_true', default=False)
  parser.add_argument('--version', '-V', action='version', version=VERSION)

  subs = parser.add_subparsers(dest='verb', help='REST API verbs or sub commands')
  #
  # Login parser
  #
  subp = subs.add_parser('login',
                          help = 'Issue token using username and password or unscoped token',
                          epilog = 'Ignores other token and AK/SK authentication credentials',
                        )
  xscope = subp.add_mutually_exclusive_group()
  xscope.add_argument('--project','-p',
                    default = os.getenv('OS_PROJECT_NAME',None),
                    help = 'Scope the token to the given project (or environment OS_PROJECT_NAME)')
  xscope.add_argument('--region', '-R',
                    default = os.getenv('OS_TENANT_NAME', os.getenv('OS_REGION', None)),
                    help='Unscoped token for the given region (or environment OS_TENANT_NAME)')
  subp.add_argument('--auth-url','-A',
                  dest = 'auth_url',
                  default = None,
                  help = 'Auth URL (or environment OS_AUTH_URL)')

  authgrp = subp.add_mutually_exclusive_group(required = True)
  #
  # Either do the login by token or by username
  #
  authgrp.add_argument('--token','-t',
                      dest = 'token',
                      default = None,
                      help = 'Unscoped token to exchange for a scoped one')
  authgrp.add_argument('--username','--user','-u',
                      default = None,
                      help = 'Username for password-based authentication')

  subp.add_argument('--password', '--passwd', '-P',
    default = os.getenv('OS_PASSWORD',None),
    help='Password for username+password authentication (or environment: OS_PASSWORD)',
  )
  subp.add_argument('--domain', '--user-domain-name', '--domain-name', '-D',
    default=os.getenv('OS_USER_DOMAIN_NAME', None),
    help='User Domain name e.g. OTC0000xxxx (or environment: OS_USER_DOMAIN_NAME)',
  )
  add_format_args(subp)

  #
  # Logout parser
  #
  subp = subs.add_parser('logout',
                          help = 'Discard issued tokens',
                        )
  xauth = subp.add_mutually_exclusive_group()
  xauth.add_argument('--region', '-R',
                  default = os.getenv('OS_TENANT_NAME', os.getenv('OS_REGION', None)),
                  help = 'Region (used to generate auth-url)',
                  )
  xauth.add_argument('--auth-url','-A',
                  dest = 'auth_url',
                  default = None,
                  help = 'Auth URL (or environment OS_AUTH_URL)')
  subp.add_argument('--shell',
                  default = None,
                  action = 'store_const',
                  const = 'shell',
                  help = 'Generate shell commands')
  subp.add_argument('--format', '-f',
                    dest = 'shell',
                    choices = ['shell'],
                    help = 'Compatibility only')

  subp.add_argument('--token','-t',
      default=os.getenv('OS_AUTH_TOKEN', os.getenv('OS_TOKEN', None)),
      help='Token to discard (or environment: OS_AUTH_TOKEN or OS_TOKEN)',
  )
  #
  # metadata parser
  #
  subp = subs.add_parser('metadata',
                        help='Retrieve Agency credentials from metadata server',
                        )
  add_format_args(subp)
  subp.add_argument('--url',
                      default = METADATA_URL,
                      help=f'Optional URL to use (defaults to {METADATA_URL})')
  #
  # temp AKSK parser
  #
  subp = subs.add_parser('aksk',
                        help = 'Issue temporary AK/SK credentials',
                        )
  xauth = subp.add_mutually_exclusive_group()
  xauth.add_argument('--region', '-R',
                  default = os.getenv('OS_TENANT_NAME', os.getenv('OS_REGION', None)),
                  help = 'Region (used to generate auth-url)',
                  )
  xauth.add_argument('--auth-url','-A',
                  dest = 'auth_url',
                  default = None,
                  help = 'Auth URL (or environment OS_AUTH_URL)')
  add_format_args(subp)
  subp.add_argument('--maxage', '--limit','--duration','-M',
                    help = 'Max age for AK/SK in seconds (default: %(default)s)',
                    type = int,
                    default = 900,
                    )
  subp.add_argument('--token','-t',
      default=os.getenv('OS_AUTH_TOKEN', os.getenv('OS_TOKEN', None)),
      help='Bearer token to use (or environment: OS_AUTH_TOKEN or OS_TOKEN)',
  )

  #
  # REST VERB Parsers
  #
  for verb,has_body in [
    ('get',False),
    ('put',True),
    ('post',True),
    ('delete',False),
    ('patch',True),
    ('head',False),
    ('options',False),
  ]:
    subp = subs.add_parser(verb,
                          help = f'Make a {verb.upper()} REST API call',
                          aliases = [ verb.upper() ],
                          )

    cgrp = subp.add_mutually_exclusive_group()
    cgrp.add_argument('--metadata', '-m',
      help='Retrieve credentials from the standard metadata endpoint',
      const = METADATA_URL,
      action='store_const',
      default = None
    )
    cgrp.add_argument('--url', '-U',
      help='Retrieve credentials from a custom metadata URL (overrides --metadata)',
      metavar = 'METADATA_URL',
      dest = 'metadata',
    )
    cgrp.add_argument('--token','-t',
      default=os.getenv('OS_AUTH_TOKEN', os.getenv('OS_TOKEN', None)),
      help='Bearer token for token authentication (or environment: OS_AUTH_TOKEN or OS_TOKEN)',
    )
    cgrp.add_argument('--ak', '--access-key', '-a',
      default=os.getenv('OS_ACCESS_KEY', None),
      help='Access Key for AK/SK authentication (or environment: OS_ACCESS_KEY)',
    )
    subp.add_argument('--sk', '--secret-key', '-s',
      default=os.getenv('OS_SECRET_KEY', None),
      help='Secret Key for AK/SK authentication (or environment: OS_SECRET_KEY)',
    )
    subp.add_argument('--securitytoken', '--security-token', '-T',
      default=os.getenv('OS_SECURITY_TOKEN', None),
      help='Security token for temporary AK/SK authentication (or environment: OS_SECURITY_TOKEN)',
    )
    subp.add_argument('--header', '-H',
      default=[],
      action = 'append',
      help='Additional header in Key:Value format (can be specified multiple times)')

    aksk_grp = subp.add_argument_group(title='AK/SK options',
                                        description = 'Options specific to AK/SK credentials')
    xgid = aksk_grp.add_mutually_exclusive_group()
    xgid.add_argument('--project-id',
        default = None,
        dest = 'project_id',
        help='Scope the AK/SK-signed request to the given project ID')
    xgid.add_argument('--project-name',
        default = None,
        dest = 'project_name',
        help='Scope the AK/SK-signed request to the given project by name')

    xgid.add_argument('--domain-id',
        default = None,
        dest = 'domain_id',
        help='Scope the AK/SK-signed request to the given domain ID')
    xgid.add_argument('--domain',
        default = False,
        action = 'store_true',
        help='Scope the AK/SK-signed request to the user\'s domain')
    aksk_grp.add_argument('--awsv4-region','--s3region',
        dest = 'awsv4_region',
        default = None,
        help = 'If specified it will use it as the region for '
               'AWS V4 Signatures for AK/SK authentication.  Otherwise '
               'SDK-HMAC-SHA256 signatures will be used.')
    aksk_grp.add_argument('--auth-url','-A',
                  dest = 'auth_url',
                  default = None,
                  help = 'Auth URL (or environment OS_AUTH_URL)')


    subp.add_argument('url',
                      help = 'URL endpoint to call',
                      )
    if has_body:
      subp.add_argument('body',
                      help = 'Payload for REST API call',
                      )

  return parser

def creds(
      ak:str|None = None,
      sk:str|None = None,
      securitytoken:str|None = None,
      token:str|None = None,
      awsv4_region:str|None = None
    ) -> dict[str,Any]:
  '''Given passed credentials, create kwargs to pass to requests

  :param ak: Access Key
  :param sk: Secret Key
  :param securitytoken: Security token for temporary AK/SK requests
  :param token: Bearer token
  :param awsv4_region: If provided, the region to use for a AWS V4 AK/SK signature
  :returns: dict with either {'headers': {'X-Auth-Token': token}} or {'auth': OTCAkSkAuth}
  :raises ValueError: if neither token nor ak/sk pair is provided, or sk is missing with ak
  '''
  if token is not None:
    if ak is not None:
      sys.stderr.write('Using bearer token.  AK/SK is ignored.\n')
    else:
      if VERBOSE: sys.stderr.write('Using bearer token.\n')
    return {
      'headers': {
          'X-Auth-Token': token,
      }
    }
  if ak is not None:
    if sk is None:
      raise ValueError('Secret Key (SK) required when using AK/SK signing')
    if VERBOSE: sys.stderr.write('Using AK/SK\n')
    ic(ak, sk, securitytoken)
    if awsv4_region is None:
      auth = OTCAkSkAuth(
        ak=ak,
        sk=sk,
        security_token=securitytoken,
      )
    else:
      auth = OBSAuth(
        ak=ak,
        sk=sk,
        security_token=securitytoken,
        region= awsv4_region,
      )
    return {
      'auth': auth,
    }
  raise ValueError('No valid credentials found!')

def add_headers(xargs:dict[str,Any], headers:list[str]) -> None:
  '''Add additional headers to xargs
  :param xargs: kwargs for requests call.  Will be modified.
  :param headers: additional headers to include. Each string must be in 'key:value' format.
  :returns: None (modifies xargs in place)
  :raises ValueError: if any header string does not contain ':' separator
  '''
  if len(headers) == 0: return
  if 'headers' not in xargs: xargs['headers'] = dict()
  for h in headers:
    k,v = h.split(':',1)
    xargs['headers'][k.strip()] = v.strip()
def add_project_id(xargs:dict[str,Any], project_id:str) -> None:
  '''Add a project scoping header to AK/SK request
  :param xargs: kwargs for requests call.  Will be modified.
  :param project_id: project ID to scope the request to
  :returns: None (modifies xargs in place)
  '''
  add_headers(xargs, [f'X-Project-Id:{project_id}'])
def add_domain_id(xargs:dict[str,Any], domain_id:str) -> None:
  '''Add a domain scoping header to AK/SK request
  :param xargs: kwargs for requests call.  Will be modified.
  :param domain_id: domain ID to scope the request to
  :returns: None (modifies xargs in place)
  '''
  add_headers(xargs, [f'X-Domain-Id:{domain_id}'])

def login(
        project:str|None = None,
        region:str|None = None,
        token:str|None = None,
        username:str|None = None,
        password:str|None = None,
        domain:str|None = None,
        auth_url:str|None = None,
      ) -> tuple[str,dict]:
  '''Issue bearer tokens
  :param project: scope the token to this project (region is derived from the project name)
  :param region: scope the token to this region (ignored if project is also set)
  :param token: an unscoped token that we want to exchange for a scoped one
  :param username: username to authenticate
  :param password: password for authentication
  :param domain: Tenant domain OTC00000XXXXX
  :returns: bearer_token, token details
  :raises ValueError: if neither token nor (username+password+domain) is provided
  :raises PermissionError: if the API returns a non-201 status or missing X-Subject-Token
  :raises requests.exceptions.RequestException: on network errors
  '''
  if project is not None:
    if region is not None:
      sys.stderr.write('Using project scope, region ignored\n')
    else:
      if VERBOSE: sys.stderr.write(f'Using project scope: {project}\n')
    # Scoped token
    scope = {
      'project': {
        'name': project,
      }
    }
    region = project.split('_')[0]  # Configure region from project name
  else:
    if VERBOSE:
      if region is None:
        sys.stderr.write(f'Unscoped to default region ({DEFAULT_REGION})\n')
      else:
        sys.stderr.write(f'Unscoped to region {region}\n')
    region = region if region is not None else DEFAULT_REGION
    ic(region)
    if domain is None:
      scope = {
        'project': {
          'name': region,
        }
      }
    else:
      scope = {
        'domain': {
          'name': domain,
        }
      }
  if token is not None:
    # Using an unscoped token
    if username is not None:
      sys.stderr.write(f'Using bearer token, username/password ignored\n')
    else:
      if VERBOSE:
        sys.stderr.write(f'Using bearer token\n')
    identity = {
      'methods': [ 'token' ],
      'token': {
        'id': token,
      }
    }
  elif username is not None and password is not None and domain is not None:
    identity = {
      'methods': [ 'password' ],
      'password': {
        'user': {
          'name': username,
          'password': password,
          'domain': {
            'name': domain,
          },
        },
      },
    }
  else:
    raise ValueError('Incomplete credential set provided')

  auth_url = resolve_auth_url(region, auth_url)
  resp = requests.post(f'{auth_url}/v3/auth/tokens',
                        json = ic({
                          'auth': {
                            'identity': identity,
                            'scope': scope,
                          }
                        }))
  if resp.status_code != 201 or 'X-Subject-Token' not in resp.headers:
    raise PermissionError(resp.text)
  data = resp.json()
  return resp.headers['X-Subject-Token'], data['token']

def logout(region:str|None = None,
          auth_url:str|None = None,
          token:str|None = None) -> None:
  '''Revoke a previously issued token

  :param region: Region to use (if auth_url is not available)
  :param auth_url: Define a specific endpoint to use
  :param token: Bearer token we want to revoke
  :returns: None
  :raises requests.exceptions.HTTPError: if the revocation request fails
  '''
  auth_url = resolve_auth_url(region, auth_url)
  if VERBOSE:
    sys.stderr.write('Discarding token: {}\n'.format(
          (token[0:10] + ' ... ' + token[-10:]) if len(token) > 20 else token
        ))
  resp = requests.delete(f'{auth_url}/v3/auth/tokens',
                          headers = {
                            'X-Auth-Token': token,
                            'X-Subject-Token': token,
                          })
  sys.stderr.write(resp.text)
  sys.stderr.write('\n')
  resp.raise_for_status()

def temp_aksk(region:str|None = None,
          auth_url:str|None = None,
          max_secs:int = 900, # default to 15 minutes
          token:str|None = None) -> dict[str,str]:
  '''Issue temporary AK/SK credentials.

  :param region: Region to use (if auth_url is not available)
  :param auth_url: Define a specific endpoint to use
  :param token: Bearer token we want to use
  :param max_secs: Max lifetime for AK/SK
  :returns: dictionary containing access, secret, securitytoken and expires_at
  :raises requests.exceptions.HTTPError: if the credentials request fails

  The AK/SK will have the same permissions as the bearer token.
  '''
  auth_url = resolve_auth_url(region, auth_url)

  response = requests.post(f'{auth_url}/v3.0/OS-CREDENTIAL/securitytokens',
                          headers = {
                            'X-Auth-Token': token,
                            'Content-Type': 'application/json',
                          },
                          json = {
                            'auth': {
                                'identity': {
                                  'methods': [ 'token' ],
                                  'duration_seconds': max_secs,
                                  'token': {
                                    'id': token,
                                  }
                                }
                            }
                          })
  response.raise_for_status()
  data = response.json()
  return data['credential']

def fmt_output(mode:str, data:dict[str,Any], raw:list[str], shell:dict[str,str]) -> str:
  '''Create formatted output

  :param mode: output mode ('raw', 'json', 'yaml', or 'shell')
  :param data: data to output
  :param raw: list of dot-path strings to extract and join for 'raw' mode
  :param shell: dict mapping env-var names to dot-path strings for 'shell' mode
  :returns: formatted string
  :raises ValueError: if mode is not one of 'raw', 'json', 'yaml', 'shell'
  :raises KeyError: if a dot-path in raw or shell does not exist in data
  '''
  if mode == 'raw':
    words = list()
    for i in raw:
      words.append(get_nested_value(i, data))
    return ' '.join(words)
  elif mode == 'json':
    return json.dumps(data, indent=2, default=str)
  elif mode == 'yaml':
    if HAS_YAML:
      return yaml.dump(data, default_flow_style = False, sort_keys = False)
    raise ValueError('YAML output requires the pyyaml package')
  elif mode == 'shell':
    lines = list()
    for k,v in shell.items():
      lines.append(f'export {k}={shlex.quote(get_nested_value(v,data))}')
    return '\n'.join(lines)
  else:
    raise ValueError(f'output_mode: {mode}')

def cli_login(args:argparse.Namespace) -> int:
  '''CLI login implementation
  :param args: Command line arguments
  :returns: Program exit code
  '''
  token, details = login(project = args.project, region = args.region,
                token = args.token,
                username = args.username,
                password = args.password,
                domain = args.domain,
                auth_url = args.auth_url,
  )
  details['token'] = token
  if 'project' in details:
    id_path = 'project.id'
    id_type = 'PROJECT'
  elif 'domain' in details:
    id_path = 'domain.id'
    id_type = 'DOMAIN'
  else:
    id_path = 'user.domain.id'
    id_type = 'USER'

  print(fmt_output(args.output,
                    details,
                    [ 'token', 'expires_at', id_path ],
                    {
                      'OS_AUTH_TOKEN': 'token',
                      'OS_AUTH_EXPIRES_AT': 'expires_at',
                      f'OS_AUTH_{id_type}_ID': id_path,
                    }))
  return 0

def cli_logout(args:argparse.Namespace) -> int:
  '''CLI logout implementation
  :param args: Command line arguments
  :returns: Program exit code
  '''
  logout(region = args.region,
          auth_url = args.auth_url,
          token = args.token)
  if args.shell:
    print('unset OS_AUTH_TOKEN')
    print('unset OS_AUTH_EXPIRES_AT')
    print('unset OS_AUTH_DOMAIN_ID')
    print('unset OS_AUTH_PROJECT_ID')
    print('unset OS_AUTH_USER_ID')
  return 0

def cli_aksk_output(args:argparse.Namespace, aksk:dict[str,str]) -> int:
  '''CLI implementation for AKSK items.
  :param args: Command line arguments
  :param aksk: credentials to output
  :returns: Program exit code
  '''
  print(fmt_output(args.output,
                      aksk,
                      [ 'access', 'secret', 'securitytoken', 'expires_at' ],
                      {
                        'OS_ACCESS_KEY': 'access',
                        'OS_SECRET_KEY': 'secret',
                        'OS_SECURITY_TOKEN': 'securitytoken',
                        'OS_AKSK_EXPIRES_AT': 'expires_at',
                      }))
  return 0

def cli_verb(args:argparse.Namespace) -> int:
  '''HTTP verb implementations
  :param args: Command line arguments
  :returns: Program exit code
  '''
  if args.metadata is not None:
    if VERBOSE:
      sys.stderr.write(f'Fetching credentials from {args.metadata}\n')
    aksk = metadata_config(args.metadata)
    args.ak = aksk['access']
    args.sk = aksk['secret']
    args.securitytoken = aksk['securitytoken']

  xargs = creds(ak = args.ak, sk = args.sk, securitytoken = args.securitytoken,
                token = args.token,
                awsv4_region = args.awsv4_region,
                )
  add_headers(xargs, args.header)
  if args.ak is None:
    opts = list()
    if args.project_id is not None: opts.append('project-id')
    if args.project_name is not None: opts.append('project-name')
    if args.domain_id is not None: opts.append('domain-id')
    if args.domain: opts.append('domain')
    if opts: sys.stderr.write(f'Ignoring options: {", ".join(opts)}\n')
  else:
    if args.project_id is not None:
      add_project_id(xargs, args.project_id)
    elif args.project_name is not None:
      # Find project ID by name
      auth_url = resolve_auth_url(DEFAULT_REGION, args.auth_url)
      resp = requests.get(f'{auth_url}/v3/auth/projects',
                          **xargs)
      resp.raise_for_status()
      jsdat = resp.json()
      for p in jsdat['projects']:
        if p['name'] == args.project_name:
          if VERBOSE: sys.stderr.write(f'Project ID: {p["id"]}\n')
          add_project_id(xargs, p['id'])
          break
      else:
        raise KeyError(args.project_name)
    elif args.domain_id is not None:
      add_domain_id(xargs, args.domain_id)
    elif args.domain:
      auth_url = resolve_auth_url(DEFAULT_REGION, args.auth_url)
      resp = requests.get(f'{auth_url}/v3.0/OS-CREDENTIAL/credentials/{args.ak}',
                          **xargs)
      resp.raise_for_status()
      jsdat = resp.json()
      user_id = jsdat['credential']['user_id']
      if VERBOSE: sys.stderr.write(f'User ID: {user_id}\n')
      resp = requests.get(f'{auth_url}/v3/users/{user_id}',
                          **xargs)
      resp.raise_for_status()
      jsdat = resp.json()
      domain_id = jsdat['user']['domain_id']
      if VERBOSE: sys.stderr.write(f'Domain ID: {domain_id}\n')
      add_domain_id(xargs, domain_id)


  if args.verb.upper() == 'GET':
    resp = requests.get(args.url, **xargs)
  elif args.verb.upper() == 'DELETE':
    resp = requests.delete(args.url, **xargs)
  elif args.verb.upper() == 'HEAD':
    resp = requests.head(args.url, **xargs)
  elif args.verb.upper() == 'OPTIONS':
    resp = requests.options(args.url, **xargs)
  elif args.verb.upper() == 'POST':
    add_headers(xargs, ['Content-Type:application/json'])
    resp = requests.post(
      args.url,
      data=args.body,
      **xargs)
  elif args.verb.upper() == 'PUT':
    add_headers(xargs, ['Content-Type:application/json'])
    resp = requests.put(
      args.url,
      data=args.body,
      **xargs)
  elif args.verb.upper() == 'PATCH':
    add_headers(xargs, ['Content-Type:application/json'])
    resp = requests.patch(
      args.url,
      data=args.body,
      **xargs)
  else:
    raise NotImplementedError(args.verb.upper())

  if resp.ok:
    print(resp.text)
  else:
    sys.stderr.write(resp.text+'\n')
    resp.raise_for_status()

  return 0

if __name__ == '__main__':
  parser = parser_factory()
  args = parser.parse_args()
  ic(args)
  VERBOSE = args.verbose

  if args.verb is None:
    parser.print_help()
  elif args.verb == 'login':
    sys.exit(cli_login(args))
  elif args.verb == 'logout':
    sys.exit(cli_logout(args))
  elif args.verb == 'aksk':
    sys.exit(cli_aksk_output(args, temp_aksk(
            region = args.region,
            auth_url = args.auth_url,
            token = args.token,
            max_secs = args.maxage,
    )))
  elif args.verb == 'metadata':
    sys.exit(cli_aksk_output(args, metadata_config(args.url)))
  else:
    sys.exit(cli_verb(args))

