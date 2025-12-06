"""
Bot Filtering Utility Module

This module provides functionality to identify and filter out bot accounts
from GitHub data (PRs, commits, etc.) based on common bot naming patterns.

Usage:
    from utility.bot_filter import filter_bots_from_dataframe, is_bot_username
    
    # Filter entire dataframe
    clean_df = filter_bots_from_dataframe(df, username_column='pr_author')
    
    # Check individual username
    if is_bot_username('dependabot[bot]'):
        print("This is a bot!")
"""

import pandas as pd
import re
from typing import List, Optional


# Default bot patterns - can be extended as needed
DEFAULT_BOT_PATTERNS = [
    r'\[bot\]$',              # Matches usernames ending with [bot]
    r'^bot[-_]',              # Matches usernames starting with bot-/bot_
    r'[-_]bot',               # Matches usernames containing -bot or _bot
    r'^bot\d',                # Matches usernames starting with bot followed by number
    r'dependabot',            # GitHub's dependency update bot
    r'github-actions',        # GitHub Actions bot
    r'renovate',              # Renovate bot for dependency updates
    r'greenkeeper',           # Greenkeeper bot (deprecated but still in history)
    r'codecov',               # Codecov bot
    r'snyk-bot',              # Snyk security bot
    r'github-classroom',      # GitHub Classroom bot
    r'allcontributors',       # All Contributors bot
    r'semantic-release-bot', # Semantic Release bot
    r'mergify',               # Mergify bot
    r'stale\[bot\]',         # Stale issues bot
    r'prettier-bot',          # Prettier formatting bot
    r'pyup-bot',              # PyUp security bot
    r'whitesource',           # WhiteSource security bot
    r'sonarcloud',            # SonarCloud analysis bot
    r'netlify',               # Netlify deploy bot
    r'vercel',                # Vercel deploy bot
    r'coveralls',             # Coveralls coverage bot
    r'travis-ci',             # Travis CI bot
    r'circleci',              # CircleCI bot
    r'jenkins',               # Jenkins bot
]


def get_bot_patterns(additional_patterns: Optional[List[str]] = None) -> List[str]:
    """
    Get the list of bot patterns to use for filtering.
    
    Args:
        additional_patterns: Optional list of additional regex patterns to include
        
    Returns:
        List of regex patterns for identifying bots
    """
    patterns = DEFAULT_BOT_PATTERNS.copy()
    if additional_patterns:
        patterns.extend(additional_patterns)
    return patterns


def is_bot_username(
    username: str, 
    bot_patterns: Optional[List[str]] = None,
    case_sensitive: bool = False
) -> bool:
    """
    Check if a username matches any bot pattern.
    
    Args:
        username: The username to check
        bot_patterns: Optional custom list of bot patterns (uses defaults if None)
        case_sensitive: Whether to perform case-sensitive matching
        
    Returns:
        True if username matches any bot pattern, False otherwise
        
    Example:
        >>> is_bot_username('dependabot[bot]')
        True
        >>> is_bot_username('john_doe')
        False
    """
    if pd.isna(username) or not username:
        return False
    
    patterns = bot_patterns if bot_patterns is not None else DEFAULT_BOT_PATTERNS
    username_str = str(username)
    
    if not case_sensitive:
        username_str = username_str.lower()
    
    # Combine all patterns into a single regex
    combined_pattern = '|'.join(patterns)
    
    try:
        return bool(re.search(combined_pattern, username_str, flags=0 if case_sensitive else re.IGNORECASE))
    except re.error as e:
        print(f"[ERROR] Invalid regex pattern: {e}")
        return False


def filter_bots_from_dataframe(
    df: pd.DataFrame,
    username_column: str = 'author',
    bot_patterns: Optional[List[str]] = None,
    case_sensitive: bool = False,
    inplace: bool = False,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Filter out bot accounts from a pandas DataFrame.
    
    Args:
        df: The DataFrame to filter
        username_column: Name of the column containing usernames
        bot_patterns: Optional custom list of bot patterns (uses defaults if None)
        case_sensitive: Whether to perform case-sensitive matching
        inplace: Whether to modify the DataFrame in place
        verbose: Whether to print filtering statistics
        
    Returns:
        Filtered DataFrame with bot accounts removed
        
    Raises:
        KeyError: If username_column doesn't exist in the DataFrame
        
    Example:
        >>> df = pd.DataFrame({'author': ['alice', 'dependabot[bot]', 'bob']})
        >>> clean_df = filter_bots_from_dataframe(df, username_column='author')
        [INFO] Filtered out 1 bot records from 3 total (33.3%)
    """
    if username_column not in df.columns:
        raise KeyError(f"Column '{username_column}' not found in DataFrame. "
                      f"Available columns: {', '.join(df.columns)}")
    
    original_count = len(df)
    
    if original_count == 0:
        if verbose:
            print("[INFO] DataFrame is empty, no filtering needed")
        return df if inplace else df.copy()
    
    patterns = bot_patterns if bot_patterns is not None else DEFAULT_BOT_PATTERNS
    combined_pattern = '|'.join(patterns)
    
    # Create mask for non-bot entries
    mask = ~df[username_column].str.lower().str.contains(
        combined_pattern,
        na=False,
        regex=True,
        case=case_sensitive
    )
    
    if inplace:
        df.drop(df[~mask].index, inplace=True)
        filtered_df = df
    else:
        filtered_df = df[mask].copy()
    
    bots_filtered = original_count - len(filtered_df)
    
    if verbose and bots_filtered > 0:
        percentage = (bots_filtered / original_count) * 100
        print(f"[INFO] Filtered out {bots_filtered} bot records from "
              f"{original_count} total ({percentage:.1f}%)")
    elif verbose:
        print("[INFO] No bot records found to filter")
    
    return filtered_df


def get_bot_usernames(
    df: pd.DataFrame,
    username_column: str = 'author',
    bot_patterns: Optional[List[str]] = None,
    case_sensitive: bool = False
) -> List[str]:
    """
    Extract list of unique bot usernames found in a DataFrame.
    
    Args:
        df: The DataFrame to analyze
        username_column: Name of the column containing usernames
        bot_patterns: Optional custom list of bot patterns (uses defaults if None)
        case_sensitive: Whether to perform case-sensitive matching
        
    Returns:
        List of unique bot usernames found
        
    Example:
        >>> df = pd.DataFrame({'author': ['alice', 'dependabot[bot]', 'renovate[bot]']})
        >>> bots = get_bot_usernames(df, username_column='author')
        >>> print(bots)
        ['dependabot[bot]', 'renovate[bot]']
    """
    if username_column not in df.columns:
        raise KeyError(f"Column '{username_column}' not found in DataFrame")
    
    patterns = bot_patterns if bot_patterns is not None else DEFAULT_BOT_PATTERNS
    combined_pattern = '|'.join(patterns)
    
    # Find all entries matching bot patterns
    bot_mask = df[username_column].str.lower().str.contains(
        combined_pattern,
        na=False,
        regex=True,
        case=case_sensitive
    )
    
    bot_usernames = df.loc[bot_mask, username_column].dropna().unique().tolist()
    return sorted(bot_usernames)


def filter_bots_from_multiple_columns(
    df: pd.DataFrame,
    username_columns: List[str],
    bot_patterns: Optional[List[str]] = None,
    case_sensitive: bool = False,
    filter_mode: str = 'any',
    inplace: bool = False,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Filter out rows where ANY or ALL specified columns contain bot usernames.
    
    Args:
        df: The DataFrame to filter
        username_columns: List of column names to check for bot usernames
        bot_patterns: Optional custom list of bot patterns
        case_sensitive: Whether to perform case-sensitive matching
        filter_mode: 'any' (remove if any column is bot) or 'all' (remove if all columns are bots)
        inplace: Whether to modify the DataFrame in place
        verbose: Whether to print filtering statistics
        
    Returns:
        Filtered DataFrame
        
    Example:
        >>> df = pd.DataFrame({
        ...     'author': ['alice', 'dependabot[bot]'],
        ...     'reviewer': ['bob', 'alice']
        ... })
        >>> clean_df = filter_bots_from_multiple_columns(df, ['author', 'reviewer'])
    """
    # Verify all columns exist
    missing_cols = [col for col in username_columns if col not in df.columns]
    if missing_cols:
        raise KeyError(f"Columns not found in DataFrame: {', '.join(missing_cols)}")
    
    original_count = len(df)
    patterns = bot_patterns if bot_patterns is not None else DEFAULT_BOT_PATTERNS
    combined_pattern = '|'.join(patterns)
    
    # Create masks for each column
    masks = []
    for col in username_columns:
        col_mask = ~df[col].str.lower().str.contains(
            combined_pattern,
            na=False,
            regex=True,
            case=case_sensitive
        )
        masks.append(col_mask)
    
    # Combine masks based on mode
    if filter_mode == 'any':
        # Keep row only if ALL columns are non-bots
        final_mask = pd.concat(masks, axis=1).all(axis=1)
    elif filter_mode == 'all':
        # Keep row if ANY column is non-bot
        final_mask = pd.concat(masks, axis=1).any(axis=1)
    else:
        raise ValueError(f"Invalid filter_mode: {filter_mode}. Must be 'any' or 'all'")
    
    if inplace:
        df.drop(df[~final_mask].index, inplace=True)
        filtered_df = df
    else:
        filtered_df = df[final_mask].copy()
    
    bots_filtered = original_count - len(filtered_df)
    
    if verbose and bots_filtered > 0:
        percentage = (bots_filtered / original_count) * 100
        print(f"[INFO] Filtered out {bots_filtered} bot records from "
              f"{original_count} total ({percentage:.1f}%) using mode='{filter_mode}'")
    elif verbose:
        print("[INFO] No bot records found to filter")
    
    return filtered_df


# Convenience function for common use case
def remove_bot_prs(prs_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Convenience function to remove bot PRs from a pull requests DataFrame.
    
    Args:
        prs_df: DataFrame containing PR data with 'pr_author' column
        verbose: Whether to print filtering statistics
        
    Returns:
        Filtered DataFrame with bot PRs removed
    """
    return filter_bots_from_dataframe(
        prs_df,
        username_column='pr_author',
        verbose=verbose,
        inplace=False
    )


def remove_bot_commits(commits_df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Convenience function to remove bot commits from a commits DataFrame.
    
    Args:
        commits_df: DataFrame containing commit data with 'author' column
        verbose: Whether to print filtering statistics
        
    Returns:
        Filtered DataFrame with bot commits removed
    """
    return filter_bots_from_dataframe(
        commits_df,
        username_column='author',
        verbose=verbose,
        inplace=False
    )


if __name__ == "__main__":
    # Example usage and testing
    print("Bot Filter Utility - Example Usage\n")
    print("="*60)
    
    # Example 1: Check individual usernames
    print("\nExample 1: Checking individual usernames")
    print("-"*60)
    test_usernames = [
        'alice',
        'dependabot[bot]',
        'github-actions[bot]',
        'john_doe',
        'renovate[bot]'
    ]
    
    for username in test_usernames:
        is_bot = is_bot_username(username)
        print(f"  {username:25} -> {'BOT' if is_bot else 'HUMAN'}")
    
    # Example 2: Filter DataFrame
    print("\n\nExample 2: Filtering DataFrame")
    print("-"*60)
    sample_data = pd.DataFrame({
        'pr_author': ['alice', 'dependabot[bot]', 'bob', 'renovate[bot]', 'charlie'],
        'pr_id': [1, 2, 3, 4, 5],
        'title': ['Feature A', 'Bump deps', 'Fix bug', 'Update deps', 'Feature B']
    })
    
    print("\nOriginal DataFrame:")
    print(sample_data.to_string(index=False))
    
    filtered_data = filter_bots_from_dataframe(sample_data, username_column='pr_author')
    
    print("\nFiltered DataFrame:")
    print(filtered_data.to_string(index=False))
    
    # Example 3: Get list of bot usernames
    print("\n\nExample 3: Extract bot usernames")
    print("-"*60)
    bots = get_bot_usernames(sample_data, username_column='pr_author')
    print(f"  Found bots: {bots}")
    
    print("\n" + "="*60)
    print("Examples complete!")