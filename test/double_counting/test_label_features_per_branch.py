import pandas as pd

from event_labelling.CodeStructure_Branching.label_features_per_branch import (
    label_features_per_branch,
)


def test_label_features_per_branch_repeats_branch_event_for_each_pr():
    prs_df = pd.DataFrame(
        [
            {
                "pr_id": 101,
                "pr_author": "alice",
                "head_branch": "feature/auth-flow",
                "created_at": "2026-01-01T10:00:00Z",
            },
            {
                "pr_id": 102,
                "pr_author": "alice",
                "head_branch": "feature/auth-flow",
                "created_at": "2026-01-02T10:00:00Z",
            },
        ]
    )

    out = label_features_per_branch(prs_df, "2026-03-09T00:00:00Z")

    assert len(out) == 2
    assert set(out["pr_id"]) == {101, 102}
    assert set(out["event"]) == {"multiple Features Per Branch"}
    assert set(out["main_label"]) == {"Features Per Branch"}