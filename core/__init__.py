# Pitboss v4 Core Module
# Contains the three frozen contracts: Document, Finding, and CheckBase

from .document import Document, Location, Paragraph, Heading, List, Table, Section
from .finding import Finding, FindingFactory, FindingCollection
from .check_base import CheckBase, CheckRegistry, register_check, get_registry
from .standards_engine import Standards, StandardsEngine

__all__ = [
    # Document model
    "Document",
    "Location",
    "Paragraph",
    "Heading",
    "List",
    "Table",
    "Section",
    # Finding
    "Finding",
    "FindingFactory",
    "FindingCollection",
    # Check interface
    "CheckBase",
    "CheckRegistry",
    "register_check",
    "get_registry",
    # Standards
    "Standards",
    "StandardsEngine",
]
