import os
import sys
import ast
import pandas as pd
import pytest

# Ensure repo root is on PYTHONPATH so imports work when running pytest from root
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.utils.label_merge import label_merge_state
import event_labelling.PR.review_helper as review_helper
from event_labelling.PR.llm_prompts import label_pr_descriptions



# integration implementation for lookup dataframes (please make sure to have these files in the data/csv folder)
review_time_lookup_df = pd.read_csv("data/csv/review_timestamp_lookup.csv")
pr_time_lookup_df = pd.read_csv("data/csv/pr_timestamp_lookup.csv")

review_time_lookup = (
review_time_lookup_df
.set_index("comment_id")["created_at"]
.to_dict()
)

pr_time_lookup = (
pr_time_lookup_df
.set_index("pr_id")["created_at"]
.to_dict()
)

PR_LABELS = {
    "self_merge", "reviewed_merge", "no_merge",
    "constructive_first_review", "constructive_second_review", "constructive_additional_review",
    "non_constructive_first_review", "non_constructive_second_review", "non_constructive_additional_review",
    "pr_description_clear", "pr_description_unclear", "changes_requested", "approved_empty_review"
}


def _extract_events(cell) -> list[str]:
    """
    Normalizes an 'event' cell into a list of labels.
    Handles:
      - "label" (string)
      - "['a','b']" (stringified list)
      - ['a','b'] (actual list)
      - NaN/None
    """
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return []
    if isinstance(cell, list):
        return [str(x).strip() for x in cell if str(x).strip()]
    s = str(cell).strip()
    if not s:
        return []
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
            return [str(parsed).strip()]
        except Exception:
            return [s]
    return [s]


def _collect_events_for_pr(df: pd.DataFrame, pr_id: int) -> set[str]:
    """Collects all event labels for a given pr_id from a dataframe with columns: pr_id, event."""
    sub = df[df["pr_id"] == pr_id]
    out = set()
    for cell in sub["event"].tolist():
        out.update(_extract_events(cell))
    return out


def test_merge_labels_assigned_self_reviewed_no_merge():
    """
    Verifies label_merge_state assigns:
      - self_merge when merged_by == pr_author (and merged)
      - reviewed_merge when merged_by != pr_author (and merged)
      - no_merge when not merged
    """
    prs_df = pd.DataFrame([
        {
            "pr_id": 1,
            "created_at": "2025-01-01T00:00:00Z",
            "merged": True,
            "merged_at": "2025-01-01T00:10:00Z",
            "merged_by": "alice",
            "pr_author": "alice",
        },
        {
            "pr_id": 2,
            "created_at": "2025-01-02T00:00:00Z",
            "merged": True,
            "merged_at": "2025-01-02T00:10:00Z",
            "merged_by": "bob",
            "pr_author": "alice",
        },
        {
            "pr_id": 3,
            "created_at": "2025-01-03T00:00:00Z",
            "merged": False,
            "merged_at": None,
            "merged_by": None,
            "pr_author": "alice",
        },
    ])

    out = label_merge_state(prs_df)
    assert {"pr_id", "event"} <= set(out.columns)

    ev1 = _collect_events_for_pr(out, 1)
    ev2 = _collect_events_for_pr(out, 2)
    ev3 = _collect_events_for_pr(out, 3)

    assert "self_merge" in ev1
    assert "reviewed_merge" in ev2
    assert "no_merge" in ev3


def test_review_labels_constructive_first_second_additional(monkeypatch):
    """
    Verifies label_review_constructiveness assigns:
      constructive_first_review, constructive_second_review, constructive_additional_review
    """
    # Patch LLM classifier to deterministic "constructive"
    monkeypatch.setattr(review_helper, "classify_constructiveness", lambda *, main_comment, inline_bodies=None, other_review_bodies=None: "constructive | test")

    reviews_df = pd.DataFrame([
        {"pr_id": 4, "comment_id": 1681326858, "created_at": "2023-10-17 04:08:59+00:00", "comment_type": "review", "comment_body": "Nice work", "state": "COMMENTED", "order_of_review": 1},
        {"pr_id": 4, "comment_id": 1681327174, "created_at": "2023-10-17 04:09:30+00:00", "comment_type": "review", "comment_body": "Consider refactoring", "state": "COMMENTED", "order_of_review": 2},
        {"pr_id": 4, "comment_id": 1688587078, "created_at": "2023-10-19 20:21:28+00:00", "comment_type": "review", "comment_body": "Great improvement", "state": "COMMENTED", "order_of_review": 3},
    ])

    out = review_helper.label_review_constructiveness(reviews_df, pr_time_lookup, review_time_lookup, '')
    assert {"pr_id", "event"} <= set(out.columns)

    ev = _collect_events_for_pr(out, 4)
    assert "constructive_additional_review" in ev


def test_review_labels_non_constructive_first_second_additional(monkeypatch):
    """
    Verifies label_review_constructiveness assigns:
      non_constructive_first_review, non_constructive_second_review, non_constructive_additional_review
    """
    # Patch LLM classifier to deterministic "non-constructive"
    monkeypatch.setattr(review_helper, "classify_constructiveness", lambda *, main_comment, inline_bodies=None, other_review_bodies=None: "nonconstructive | test")

    reviews_df = pd.DataFrame([
        {"pr_id": 20, "created_at": "2025-03-01T00:00:00Z", "comment_type": "review", "comment_body": "meh", "state": "COMMENTED", "order_of_review": 1},
        {"pr_id": 20, "created_at": "2025-03-01T00:01:00Z", "comment_type": "review", "comment_body": "bad", "state": "COMMENTED", "order_of_review": 2},
        {"pr_id": 20, "created_at": "2025-03-01T00:02:00Z", "comment_type": "review", "comment_body": "no", "state": "COMMENTED", "order_of_review": 3},
    ])

    out = review_helper.label_review_constructiveness(reviews_df, pr_time_lookup, review_time_lookup, '')
    assert {"pr_id", "event"} <= set(out.columns)

    ev = _collect_events_for_pr(out, 20)
    assert "non_constructive_additional_review" in ev


def test_review_labels_changes_requested(monkeypatch):
    """Verifies changes_requested is added when review state == CHANGES_REQUESTED."""
    monkeypatch.setattr(review_helper, "classify_constructiveness", lambda *, main_comment, inline_bodies=None, other_review_bodies=None: "constructive | test")

    reviews_df = pd.DataFrame([
        {"pr_id": 30, "created_at": "2025-04-01T00:00:00Z", "comment_type": "review", "comment_body": "Please fix", "state": "CHANGES_REQUESTED", "order_of_review": 1},
    ])

    out = review_helper.label_review_constructiveness(reviews_df, pr_time_lookup, review_time_lookup, '')
    ev = _collect_events_for_pr(out, 30)

    assert "changes_requested" in ev
    # also should still tag constructive/non-constructive (since non-empty)
    assert "constructive_first_review" in ev or "non_constructive_first_review" in ev


def test_review_labels_approved_empty_review(monkeypatch):
    """Verifies approved_empty_review is added when state == APPROVED and comment_body is empty."""
    # Even if classifier is patched, empty approved review should short-circuit before classification
    monkeypatch.setattr(review_helper, "classify_constructiveness", lambda text: True)

    reviews_df = pd.DataFrame([
        {"pr_id": 40, "created_at": "2025-05-01T00:00:00Z", "comment_type": "review", "comment_body": "", "state": "APPROVED", "order_of_review": 1},
    ])

    out = review_helper.label_review_constructiveness(reviews_df, pr_time_lookup, review_time_lookup, '')
    ev = _collect_events_for_pr(out, 40)

    assert "approved_empty_review" in ev
    # should NOT also create constructive/non-constructive labels for empty approved review
    assert not ({"constructive_first_review", "non_constructive_first_review"} & ev)


def test_pr_description_labels_clear_and_unclear():
    """
    Verifies label_pr_descriptions assigns:
      - pr_description_clear when title+body has >= 10 words
      - pr_description_unclear otherwise
    """
    prs_df = pd.DataFrame([
        {
            "pr_id": 50,
            "created_at": "2025-06-01T00:00:00Z",
            "pr_title": "Fix data pipeline bug",
            "body": "This PR fixes the pipeline bug by validating inputs and improving error handling, and also adds some documentation to the main md file.",
        },
        {
            "pr_id": 51,
            "created_at": "2025-06-02T00:00:00Z",
            "pr_title": "Update",
            "body": "",
        },
    ])

    out = label_pr_descriptions(prs_df)
    assert {"pr_id", "event"} <= set(out.columns)

    ev50 = _collect_events_for_pr(out, 50)
    ev51 = _collect_events_for_pr(out, 51)

    assert "pr_description_clear" in ev50
    assert "pr_description_unclear" in ev51


def test_no_unexpected_labels_emitted_from_these_components(monkeypatch):
    """
    Optional safety net: ensures these components only emit labels we expect.
    (If you later add more PR_LABELS, update PR_LABELS set above.)
    """
    monkeypatch.setattr(review_helper, "classify_constructiveness", lambda *, main_comment, inline_bodies=None, other_review_bodies=None: "constructive | test")

    prs_df = pd.DataFrame([{
        "pr_id": 60, "created_at": "2025-07-01T00:00:00Z",
        "merged": True, "merged_at": "2025-07-01T00:10:00Z",
        "merged_by": "alice", "pr_author": "alice",
        "pr_title": "Some change", "pr_body": "This adds tests and documentation for the pipeline to ensure correctness."
    }])

    reviews_df = pd.DataFrame([{
        "pr_id": 60, "created_at": "2025-07-01T00:05:00Z",
        "comment_type": "review", "comment_body": "Looks good", "state": "COMMENTED", "order_of_review": 1
    }])

    merge_out = label_merge_state(prs_df)
    desc_out = label_pr_descriptions(prs_df)
    rev_out = review_helper.label_review_constructiveness(reviews_df, pr_time_lookup, review_time_lookup, '')

    emitted = set()
    for df in [merge_out, desc_out, rev_out]:
        for cell in df["event"].tolist():
            emitted.update(_extract_events(cell))

    unknown = emitted - PR_LABELS
    assert not unknown, f"Unexpected labels emitted: {sorted(unknown)}"
