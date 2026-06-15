"""
Pitboss v4 - Brief Format Parsers

Format-specific parsers for brief files.
Each parser self-registers via the @register_brief_parser decorator.

Available parsers:
- xlsx_parser: Excel briefs (.xlsx)
- docx_parser: Word briefs (.docx)
- sheets_parser: Google Sheets (via URL) - deferred
"""

# Import parsers to trigger self-registration
from ingest.brief_formats import xlsx_parser
from ingest.brief_formats import docx_parser

# sheets_parser deferred - requires Google API credentials
