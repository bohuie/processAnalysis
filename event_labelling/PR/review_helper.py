import pandas as pd
from tqdm import tqdm

# helper imports
from event_labelling.PR.helpers_pr import (
    append_event,
)

# llm prompt imports
from event_labelling.PR.llm_prompts import (
    classify_constructiveness,
)

def label_review_constructiveness(
    reviews_df: pd.DataFrame,
    pr_time_lookup: dict,
    review_time_lookup: dict,
    run_timestamp: str,
) -> pd.DataFrame:
    """
    Enrich reviews_df with:
      - changes_requested
      - approved_without_review
      - review_resolved / review_unresolved
      - constructive_* / non_constructive_* labels

    All of these are applied ONLY to rows where comment_type == 'review'.
    Constructiveness is decided per (pr_id, review_author) using:
      - the chosen target review body
      - inline comments by that reviewer on that PR
      - other review bodies (excluding APPROVED at/after target).
    """

    # Basic cleanup / helper columns
    reviews_df = reviews_df.copy()
    reviews_df["comment_body"] = reviews_df["comment_body"].fillna("")
    reviews_df["state_lower"] = reviews_df["state"].fillna("").str.lower()
    reviews_df["state_upper"] = reviews_df["state"].fillna("").str.upper()
    reviews_df["comment_type_lower"] = reviews_df["comment_type"].fillna("").str.lower()

    # Count comments per PR (for context / debugging)
    review_counts = reviews_df.groupby("pr_id").size().reset_index(name="comment_count")
    reviews_df = reviews_df.merge(review_counts, on="pr_id", how="left")

    # Init event / LLM columns
    if "event" not in reviews_df.columns:
        reviews_df["event"] = [[] for _ in range(len(reviews_df))]
    else:
        reviews_df["event"] = reviews_df["event"].apply(
            lambda x: x if isinstance(x, list) else (list(x) if pd.notna(x) else [])
        )

    reviews_df["llm_output"] = ""
    reviews_df["llm_timestamp"] = ""
    reviews_df["review_author"] = reviews_df.get("author", "unknown")

    # Ensure created_at is populated and sort for stable ordering
    reviews_df["created_at"] = reviews_df["created_at"].combine_first(
        reviews_df["comment_id"].map(review_time_lookup)
        if "comment_id" in reviews_df.columns
        else pd.Series([pd.NaT] * len(reviews_df))
    )
    reviews_df["created_at"] = reviews_df["created_at"].combine_first(
        reviews_df["pr_id"].map(pr_time_lookup)
    )

    sort_cols = ["pr_id", "review_author", "created_at"]
    if "comment_id" in reviews_df.columns:
        sort_cols.append("comment_id")
    reviews_df = reviews_df.sort_values(sort_cols)

    # Group by (PR, reviewer) and apply labelling logic
    grouped = reviews_df.groupby(["pr_id", "review_author"], sort=False)
    for (pr_id, reviewer), group in tqdm(
        grouped,
        total=grouped.ngroups,
        desc="[STEP 3] Review labelling per (PR, reviewer)",
    ):
        ct_lower = group["comment_type_lower"]
        is_review = ct_lower.eq("review")
        is_inline = ct_lower.eq("inline")

        review_rows = group[is_review].copy()
        inline_rows = group[is_inline].copy()

        if review_rows.empty:
            continue

        review_rows = review_rows.sort_values("created_at")
        review_idx = review_rows.index
        review_states_upper = review_rows["state_upper"].astype(str)

        # --- (A) changes_requested on CHANGES_REQUESTED review rows ---
        cr_mask = review_states_upper.eq("CHANGES_REQUESTED")
        for idx in review_idx[cr_mask]:
            reviews_df.at[idx, "event"] = append_event(
                reviews_df.at[idx, "event"],
                "changes_requested"
            )

        # --- (B) approved_without_review (single empty APPROVED review) ---
        if len(review_rows) == 1:
            idx = review_idx[0]
            state_up = review_states_upper.iloc[0]
            body = str(review_rows.loc[idx, "comment_body"]).strip()
            if state_up == "APPROVED" and body == "":
                reviews_df.at[idx, "event"] = append_event(
                    reviews_df.at[idx, "event"],
                    "approved_without_review"
                )

        # --- (C) review_resolved / review_unresolved ----------------------
        cr_indices = list(review_idx[cr_mask])
        approved_mask = review_states_upper.eq("APPROVED")
        approved_indices = list(review_idx[approved_mask])

        if cr_indices:
            changes_rows = review_rows[cr_mask].sort_values("created_at")
            last_change_idx = changes_rows.index[-1]
            last_change_time = changes_rows["created_at"].iloc[-1]

            if approved_indices:
                approved_rows = review_rows[approved_mask].sort_values("created_at")

                # label review_resolved on APPROVED rows that have earlier CHANGES_REQUESTED
                any_change_before = changes_rows["created_at"].min()
                for idx in approved_rows.index:
                    if any_change_before < review_rows.loc[idx, "created_at"]:
                        reviews_df.at[idx, "event"] = append_event(
                            reviews_df.at[idx, "event"],
                            "review_resolved"
                        )

                # review_unresolved if last CHANGES_REQUESTED has no later APPROVED
                any_approved_after = (approved_rows["created_at"] > last_change_time).any()
                if not any_approved_after:
                    reviews_df.at[last_change_idx, "event"] = append_event(
                        reviews_df.at[last_change_idx, "event"],
                        "review_unresolved"
                    )
            else:
                # no APPROVED at all -> last CHANGES_REQUESTED is unresolved
                reviews_df.at[last_change_idx, "event"] = append_event(
                    reviews_df.at[last_change_idx, "event"],
                    "review_unresolved"
                )

        # --- (D) Constructiveness classification (only for review rows) ---
        approved_rows = review_rows[review_rows["state_upper"] == "APPROVED"]

        if not approved_rows.empty:
            first_approved = approved_rows.iloc[0]
            before_approved = review_rows[review_rows["created_at"] < first_approved["created_at"]]
            if not before_approved.empty:
                target_row = before_approved.iloc[-1]
            else:
                # only APPROVED exists or it is the first review: target is that APPROVED
                target_row = first_approved
        else:
            # no APPROVED: target is last review row
            target_row = review_rows.iloc[-1]

        target_idx = target_row.name
        main_body = str(target_row["comment_body"]).strip()
        if not main_body:
            # no text -> skip LLM classification
            continue

        target_time = target_row["created_at"]

        # Inline bodies: all inline comments from this reviewer on this PR
        inline_bodies = [
            str(b).strip()
            for b in inline_rows["comment_body"].tolist()
            if str(b).strip()
        ]

        # Other review bodies as context, excluding APPROVED at/after target
        other_review_bodies = []
        for idx, row2 in review_rows.iterrows():
            if idx == target_idx:
                continue
            body2 = str(row2["comment_body"]).strip()
            if not body2:
                continue
            state2 = str(row2["state_upper"])
            created2 = row2["created_at"]
            # Exclude APPROVED bodies at or after the target (your Case 2 rule)
            if state2 == "APPROVED" and created2 >= target_time:
                continue
            other_review_bodies.append(body2)

        llm_response = classify_constructiveness(
            main_comment=main_body,
            inline_bodies=inline_bodies,
            other_review_bodies=other_review_bodies,
        )
        resp_lower = llm_response.lower()
        label_prefix = (
            "constructive"
            if "constructive" in resp_lower and "non" not in resp_lower
            else "non_constructive"
        )
        reason = (
            llm_response.split("|")[-1].strip()
            if "|" in llm_response
            else llm_response
        )

        order_str = str(target_row.get("order_of_review", "first")).lower()
        if "1" in order_str or "first" in order_str:
            event_label = f"{label_prefix}_first_review"
        elif "2" in order_str or "second" in order_str:
            event_label = f"{label_prefix}_second_review"
        else:
            event_label = f"{label_prefix}_additional_review"

        reviews_df.at[target_idx, "event"] = append_event(
            reviews_df.at[target_idx, "event"],
            event_label
        )
        reviews_df.at[target_idx, "llm_output"] = reason
        reviews_df.at[target_idx, "llm_timestamp"] = run_timestamp

    return reviews_df
