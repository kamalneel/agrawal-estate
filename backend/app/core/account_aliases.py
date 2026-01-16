"""
Account name aliases and normalization.

This module provides a central place to define account name aliases,
allowing users to refer to accounts by different names interchangeably.
"""

# Mapping of aliases to canonical account names
# Key: alias (lowercase for case-insensitive matching)
# Value: canonical account name as it appears in the database
ACCOUNT_ALIASES = {
    "neel's ira": "Neel's Retirement",
    "neels ira": "Neel's Retirement",
    "neel ira": "Neel's Retirement",
}


def normalize_account_name(account_name: str) -> str:
    """
    Normalize an account name to its canonical form.

    If the account name matches a known alias, returns the canonical name.
    Otherwise, returns the original name unchanged.

    Args:
        account_name: The account name to normalize

    Returns:
        The canonical account name
    """
    if not account_name:
        return account_name

    # Check if it's an alias (case-insensitive)
    normalized = ACCOUNT_ALIASES.get(account_name.lower().strip())
    if normalized:
        return normalized

    return account_name


def get_all_names_for_account(canonical_name: str) -> list:
    """
    Get all known names (including aliases) for an account.

    Args:
        canonical_name: The canonical account name

    Returns:
        List of all names including the canonical name and aliases
    """
    names = [canonical_name]
    for alias, canonical in ACCOUNT_ALIASES.items():
        if canonical == canonical_name:
            names.append(alias)
    return names
