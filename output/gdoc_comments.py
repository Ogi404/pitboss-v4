"""
Pitboss v4 - Google Docs Comments

Posts proposal findings as Google Drive API comments.
Comments appear in the right sidebar with embedded location context.

NOTE: Google Docs ignores quotedFileContent anchors for API-created comments
(known limitation since 2016 - issuetracker.google.com/issues/36763384).
Instead, we embed the quoted text and section info directly in the comment
body so reviewers can find the exact location by searching the doc.

Usage:
    from output.gdoc_comments import post_comments
    from output.comments import draft_comments

    proposals = [f for f in findings if not f.auto_applicable]
    drafted = draft_comments(proposals, document)
    comment_ids = post_comments(doc_id, drafted)
"""

from __future__ import annotations
import logging
from typing import Optional

from output.comments import DraftedComment
from ingest.gdoc_auth import get_drive_service


logger = logging.getLogger(__name__)


# Maximum length for quoted text anchors (Drive API limit)
MAX_ANCHOR_LENGTH = 100


def post_comments(
    doc_id: str,
    comments: list[DraftedComment],
) -> dict[str, str]:
    """
    Post DraftedComments as Google Drive comments.

    Comments include embedded location context (section, element number,
    quoted text) in the body since Google Docs doesn't support API-based
    text anchoring.

    Args:
        doc_id: Google Doc ID (not URL)
        comments: List of DraftedComment objects from draft_comments()

    Returns:
        Dict mapping finding_id -> comment_id for successfully posted comments
    """
    service = get_drive_service()
    finding_to_comment: dict[str, str] = {}

    for comment in comments:
        # NOTE: We intentionally DO NOT use quotedFileContent here.
        # Google Docs ignores anchor fields for API-created comments
        # (known limitation since 2016 - see issuetracker #36763384).
        # Instead, we embed the quoted text in the comment body itself
        # so reviewers can find the exact location.
        body = {
            'content': _format_comment_content(comment),
        }

        try:
            result = service.comments().create(
                fileId=doc_id,
                body=body,
                fields='id'
            ).execute()

            finding_to_comment[comment.finding_id] = result['id']

        except Exception as e:
            logger.warning(f"Failed to post comment for {comment.check_name}: {e}")
            # Continue with other comments

    logger.info(f"Posted {len(finding_to_comment)}/{len(comments)} comments to doc {doc_id}")
    return finding_to_comment


def post_comments_batch(
    doc_id: str,
    comments: list[DraftedComment],
    batch_size: int = 10,
) -> dict[str, str]:
    """
    Post comments using batch API with rate limiting.

    Splits into smaller batches to avoid Drive API rate limits.
    The Drive API has a limit of ~10-20 writes per second.

    Args:
        doc_id: Google Doc ID
        comments: List of DraftedComment objects
        batch_size: Number of comments per batch (default 10)

    Returns:
        Dict mapping finding_id -> comment_id for successfully posted comments
    """
    import time

    service = get_drive_service()
    finding_to_comment: dict[str, str] = {}

    # Split into batches
    for batch_start in range(0, len(comments), batch_size):
        batch_comments = comments[batch_start:batch_start + batch_size]

        # Map request_id to finding_id for callback
        request_id_to_finding: dict[str, str] = {}
        for i, comment in enumerate(batch_comments):
            request_id_to_finding[str(i)] = comment.finding_id

        def callback(request_id, response, exception):
            if exception:
                logger.warning(f"Batch comment failed: {exception}")
            else:
                finding_id = request_id_to_finding.get(request_id)
                if finding_id and response:
                    finding_to_comment[finding_id] = response.get('id', '')

        # Create batch request
        batch = service.new_batch_http_request(callback=callback)

        for i, comment in enumerate(batch_comments):
            # No quotedFileContent - see note in post_comments()
            body = {
                'content': _format_comment_content(comment),
            }

            batch.add(
                service.comments().create(
                    fileId=doc_id,
                    body=body,
                    fields='id'
                ),
                request_id=str(i)
            )

        # Execute batch
        batch.execute()

        # Rate limit: wait between batches to avoid hitting API limits
        if batch_start + batch_size < len(comments):
            time.sleep(1.0)  # 1 second pause between batches

    logger.info(
        f"Batch posted {len(finding_to_comment)}/{len(comments)} comments "
        f"to doc {doc_id}"
    )
    return finding_to_comment


def _format_comment_content(comment: DraftedComment) -> str:
    """
    Format a DraftedComment as comment text for Drive.

    Creates a structured, readable comment with severity, issue,
    suggestion (if any), location context, and QUOTED TEXT.

    NOTE: Since Google Docs ignores quotedFileContent anchors for API-created
    comments (known limitation since 2016), we embed the quoted text directly
    in the comment body so reviewers can find the exact location.
    """
    lines = []

    # Header with severity badge and check name
    severity_badge = f"[{comment.severity.upper()}]"
    lines.append(f"{severity_badge} {comment.check_name}")

    # Location context FIRST (helps find the issue)
    lines.append(f"@ {comment.location_desc}")

    # Quoted text - THE KEY for finding the exact spot
    if comment.original_text:
        quoted = comment.original_text
        if len(quoted) > 80:
            quoted = quoted[:80] + "..."
        lines.append(f'> "{quoted}"')

    lines.append("")

    # Issue description
    lines.append(f"Issue: {comment.issue}")

    # Suggestion if present
    if comment.suggestion:
        lines.append("")
        suggestion = comment.suggestion
        if len(suggestion) > 150:
            suggestion = suggestion[:150] + "..."
        lines.append(f'Fix: "{suggestion}"')

    return "\n".join(lines)


def delete_all_comments(doc_id: str) -> int:
    """
    Delete all comments from a document.

    Useful for cleanup during testing.

    Args:
        doc_id: Google Doc ID

    Returns:
        Number of comments deleted
    """
    service = get_drive_service()

    # List all comments
    result = service.comments().list(
        fileId=doc_id,
        fields='comments(id)'
    ).execute()

    comments = result.get('comments', [])
    deleted = 0

    for comment in comments:
        try:
            service.comments().delete(
                fileId=doc_id,
                commentId=comment['id']
            ).execute()
            deleted += 1
        except Exception as e:
            logger.warning(f"Failed to delete comment {comment['id']}: {e}")

    logger.info(f"Deleted {deleted}/{len(comments)} comments from doc {doc_id}")
    return deleted


def list_comments(doc_id: str) -> list[dict]:
    """
    List all comments on a document.

    Useful for verification and debugging.

    Args:
        doc_id: Google Doc ID

    Returns:
        List of comment dicts with id, content, quotedFileContent
    """
    service = get_drive_service()

    result = service.comments().list(
        fileId=doc_id,
        fields='comments(id,content,quotedFileContent,author,createdTime)'
    ).execute()

    return result.get('comments', [])


def count_comments(doc_id: str) -> int:
    """
    Count comments on a document.

    Args:
        doc_id: Google Doc ID

    Returns:
        Number of comments
    """
    return len(list_comments(doc_id))
