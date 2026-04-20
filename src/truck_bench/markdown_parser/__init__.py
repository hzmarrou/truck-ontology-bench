"""Parse a Markdown ontology specification into a neutral dataclass model."""

from .model import Field, ParsedEntity, ParsedOntology
from .parser import parse_markdown

__all__ = ["Field", "ParsedEntity", "ParsedOntology", "parse_markdown"]
