"""
Utility functions for Spoils of Empire
"""

from .models import ResourceType


def normalize_resource_type(resource_str: str) -> str:
    """
    Normalize a resource type string to match enum values.

    Handles plural forms by removing trailing 's'.
    Examples:
        - "soldiers" -> "SOLDIER"
        - "horses" -> "HORSE"
        - "gold" -> "GOLD"
    """
    normalized = resource_str.upper()

    # Try exact match first
    try:
        ResourceType[normalized]
        return normalized
    except KeyError:
        pass

    # Try removing trailing 's' for plurals
    if normalized.endswith('S') and len(normalized) > 1:
        singular = normalized[:-1]
        try:
            ResourceType[singular]
            return singular
        except KeyError:
            pass

    # Return as-is if no match found (will fail later with proper error)
    return normalized


def parse_resource_type(resource_str: str) -> ResourceType:
    """
    Parse a resource type string into a ResourceType enum.

    Raises KeyError if resource type is not valid.
    """
    normalized = normalize_resource_type(resource_str)
    return ResourceType[normalized]
