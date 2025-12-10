def anonymize_column(series: pd.Series, mapping: dict) -> pd.Series:
    """Replace exact matches or substrings based on mapping (case-insensitive)."""
    if not mapping:
        return series
    
    s = series.astype(str)
    for real_name, anon in mapping.items():
        pattern = re.compile(re.escape(real_name), re.IGNORECASE)
        s = s.str.replace(pattern, anon, regex=True)
    return s

def anonymize_branch_names(series: pd.Series, mapping: dict) -> pd.Series:
    """Anonymize branch names by replacing username parts within the full branch string."""
    if not mapping:
        return series
    
    s = series.astype(str)
    for real_name, anon in mapping.items():
        pattern = re.compile(re.escape(real_name), re.IGNORECASE)
        s = s.str.replace(pattern, anon, regex=True)
    return s