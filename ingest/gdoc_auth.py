"""
Pitboss v4 - Google Docs Authentication

OAuth flow for Google Docs and Drive APIs.
Handles credential acquisition, token refresh, and storage.

Usage:
    # Test authentication with a doc ID
    python -m ingest.gdoc_auth --test-doc <DOC_ID>

    # Programmatic usage
    from ingest.gdoc_auth import get_credentials, get_docs_service
    creds = get_credentials()
    service = get_docs_service()
"""

from __future__ import annotations
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError


logger = logging.getLogger(__name__)

# Scopes required for Pitboss operations
# - documents: read/write Google Docs
# - drive.file: post comments on docs we access
SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive.file',
]

# Default paths for credential/token storage
DEFAULT_CREDENTIALS_PATH = Path('credentials.json')
DEFAULT_TOKEN_PATH = Path('token.json')


def get_credentials(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> Credentials:
    """
    Get valid Google API credentials, refreshing or re-authenticating as needed.

    Args:
        credentials_path: Path to OAuth client credentials JSON (default: credentials.json)
        token_path: Path to store/load refresh token (default: token.json)

    Returns:
        Valid Credentials object

    Raises:
        FileNotFoundError: If credentials.json doesn't exist
        Exception: If authentication fails
    """
    creds_path = credentials_path or DEFAULT_CREDENTIALS_PATH
    tok_path = token_path or DEFAULT_TOKEN_PATH

    if not creds_path.exists():
        raise FileNotFoundError(
            f"OAuth credentials not found at {creds_path}. "
            "Download from Google Cloud Console (APIs & Services > Credentials > OAuth client)."
        )

    creds = None

    # Load existing token if available
    if tok_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(tok_path), SCOPES)
            logger.debug(f"Loaded existing token from {tok_path}")
        except Exception as e:
            logger.warning(f"Could not load token from {tok_path}: {e}")
            creds = None

    # Check if we need to refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired token...")
            try:
                creds.refresh(Request())
                logger.info("Token refreshed successfully")
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}, re-authenticating...")
                creds = None

        if not creds:
            logger.info("Starting OAuth flow (browser will open)...")
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("Authentication successful")

        # Save token for next run
        tok_path.write_text(creds.to_json())
        logger.debug(f"Token saved to {tok_path}")

    return creds


def get_docs_service(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> Resource:
    """
    Get an authenticated Google Docs API service.

    Args:
        credentials_path: Path to OAuth client credentials JSON
        token_path: Path to store/load refresh token

    Returns:
        Google Docs API service resource
    """
    creds = get_credentials(credentials_path, token_path)
    return build('docs', 'v1', credentials=creds)


def get_drive_service(
    credentials_path: Optional[Path] = None,
    token_path: Optional[Path] = None,
) -> Resource:
    """
    Get an authenticated Google Drive API service.

    Args:
        credentials_path: Path to OAuth client credentials JSON
        token_path: Path to store/load refresh token

    Returns:
        Google Drive API service resource
    """
    creds = get_credentials(credentials_path, token_path)
    return build('drive', 'v3', credentials=creds)


def test_api_access(doc_id: str) -> dict:
    """
    Prove API access by reading a Google Doc's metadata.

    Args:
        doc_id: Google Doc ID (from URL: docs.google.com/document/d/<DOC_ID>/edit)

    Returns:
        Dict with title, doc_id, and revision_id
    """
    service = get_docs_service()

    try:
        doc = service.documents().get(documentId=doc_id).execute()
        return {
            'title': doc.get('title'),
            'doc_id': doc.get('documentId'),
            'revision_id': doc.get('revisionId'),
        }
    except HttpError as e:
        if e.resp.status == 404:
            raise ValueError(f"Document not found: {doc_id}")
        elif e.resp.status == 403:
            raise PermissionError(f"Access denied to document: {doc_id}")
        else:
            raise


def extract_doc_id(url_or_id: str) -> str:
    """
    Extract document ID from a Google Docs URL or return as-is if already an ID.

    Args:
        url_or_id: Either a full URL or just the doc ID

    Returns:
        The document ID

    Examples:
        >>> extract_doc_id("https://docs.google.com/document/d/abc123/edit")
        'abc123'
        >>> extract_doc_id("abc123")
        'abc123'
    """
    # If it looks like a URL, extract the ID
    if 'docs.google.com' in url_or_id or 'drive.google.com' in url_or_id:
        # Pattern: /d/<doc_id>/ or /d/<doc_id>
        import re
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', url_or_id)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract doc ID from URL: {url_or_id}")

    # Assume it's already a doc ID
    return url_or_id


def main():
    """CLI entry point for testing authentication."""
    parser = argparse.ArgumentParser(
        description="Test Google Docs API authentication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m ingest.gdoc_auth --test-doc 1abc123def456
  python -m ingest.gdoc_auth --test-doc "https://docs.google.com/document/d/1abc123/edit"
        """
    )

    parser.add_argument(
        '--test-doc', '-t',
        type=str,
        required=True,
        help='Google Doc ID or URL to test access'
    )

    parser.add_argument(
        '--credentials', '-c',
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help=f'Path to credentials.json (default: {DEFAULT_CREDENTIALS_PATH})'
    )

    parser.add_argument(
        '--token',
        type=Path,
        default=DEFAULT_TOKEN_PATH,
        help=f'Path to token.json (default: {DEFAULT_TOKEN_PATH})'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Extract doc ID from URL if needed
    try:
        doc_id = extract_doc_id(args.test_doc)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Testing API access to document: {doc_id}")
    print()

    try:
        # This will trigger OAuth if needed
        result = test_api_access(doc_id)

        print("=" * 60)
        print("SUCCESS: Google Docs API access confirmed!")
        print("=" * 60)
        print(f"  Title:       {result['title']}")
        print(f"  Doc ID:      {result['doc_id']}")
        print(f"  Revision ID: {result['revision_id']}")
        print("=" * 60)
        print()
        print(f"Token saved to: {args.token}")
        print("Future runs will use this token (no re-auth needed).")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print()
        print("To set up OAuth credentials:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create or select a project")
        print("3. Enable Google Docs API and Google Drive API")
        print("4. Go to APIs & Services > Credentials")
        print("5. Create OAuth client ID (Desktop app type)")
        print("6. Download JSON and save as 'credentials.json'")
        sys.exit(1)

    except PermissionError as e:
        print(f"Error: {e}")
        print("Make sure you have access to this document.")
        sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
