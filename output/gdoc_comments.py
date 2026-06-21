"""
Pitboss v4 - Google Docs Comments

Posts proposal findings as Google Drive API comments.
Drive comments appear in the right sidebar and can anchor to quoted text.

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
) -> list[str]:
    """
    Post DraftedComments as Google Drive comments.

    Each comment is anchored to the original flagged text (if available)
    using Drive's quotedFileContent feature.

    Args:
        doc_id: Google Doc ID (not URL)
        comments: List of DraftedComment objects from draft_comments()

    Returns:
        List of created comment IDs
    """
    service = get_drive_service()
    posted_ids = []

    for comment in comments:
        body = {
            'content': _format_comment_content(comment),
        }

        # Add text anchor if we have original text
        if comment.original_text:
            anchor_text = comment.original_text[:MAX_ANCHOR_LENGTH]
            body['quotedFileContent'] = {
                'value': anchor_text,
                'mimeType': 'text/plain'
            }

        try:
            result = service.comments().create(
                fileId=doc_id,
                body=body,
                fields='id'
            ).execute()

            posted_ids.append(result['id'])

        except Exception as e:
            logger.warning(f"Failed to post comment for {comment.check_name}: {e}")
            # Continue with other comments

    logger.info(f"Posted {len(posted_ids)}/{len(comments)} comments to doc {doc_id}")
    return posted_ids


def post_comments_batch(
    doc_id: str,
    comments: list[DraftedComment],
    batch_size: int = 10,
) -> int:
    """
    Post comments using batch API with rate limiting.

    Splits into smaller batches to avoid Drive API rate limits.
    The Drive API has a limit of ~10-20 writes per second.

    Args:
        doc_id: Google Doc ID
        comments: List of DraftedComment objects
        batch_size: Number of comments per batch (default 10)

    Returns:
        Number of comments successfully posted
    """
    import time

    service = get_drive_service()
    total_success = 0
    total_failure = 0

    # Split into batches
    for batch_start in range(0, len(comments), batch_size):
        batch_comments = comments[batch_start:batch_start + batch_size]

        # Track success/failure for this batch
        success_count = 0
        failure_count = 0

        def callback(request_id, response, exception):
            nonlocal success_count, failure_count
            if exception:
                logger.warning(f"Batch comment failed: {exception}")
                failure_count += 1
            else:
                success_count += 1

        # Create batch request
        batch = service.new_batch_http_request(callback=callback)

        for i, comment in enumerate(batch_comments):
            body = {
                'content': _format_comment_content(comment),
            }

            if comment.original_text:
                anchor_text = comment.original_text[:MAX_ANCHOR_LENGTH]
                body['quotedFileContent'] = {
                    'value': anchor_text,
                    'mimeType': 'text/plain'
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

        total_success += success_count
        total_failure += failure_count

        # Rate limit: wait between batches to avoid hitting API limits
        if batch_start + batch_size < len(comments):
            time.sleep(1.0)  # 1 second pause between batches

    logger.info(
        f"Batch posted {total_success} comments, {total_failure} failures "
        f"to doc {doc_id}"
    )
    return total_success


def _format_comment_content(comment: DraftedComment) -> str:
    """
    Format a DraftedComment as comment text for Drive.

    Creates a structured, readable comment with severity, issue,
    suggestion (if any), and location context.
    """
    lines = []

    # Header with severity badge and check name
    severity_badge = f"[{comment.severity.upper()}]"
    lines.append(f"{severity_badge} {comment.check_name}")
    lines.append("")

    # Issue description
    lines.append(f"Issue: {comment.issue}")

    # Suggestion if present
    if comment.suggestion:
        lines.append("")
        # Truncate very long suggestions
        suggestion = comment.suggestion
        if len(suggestion) > 200:
            suggestion = suggestion[:200] + "..."
        lines.append(f"Suggested: \"{suggestion}\"")

    # Location context (helps find the issue in long docs)
    lines.append("")
    lines.append(f"Location: {comment.location_desc}")

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
