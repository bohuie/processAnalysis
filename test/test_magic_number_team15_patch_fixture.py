import os
import sys
import pytest

# Keep existing sys.path approach for now (repo infra may not be standardized yet)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.violations.magic_number_check import (
    MagicNumberConfig,
    detect_magic_numbers_from_code,
    extract_code_from_patch_snippet,
)

# Real Team 15 patch_snippet fixture (JavaScript-heavy repo, but test goal is language-agnostic):
# Ensure diff hunk header numbers like @@ -11,15 +11,17 @@ are not treated as code literals.
TEAM15_PATCH_SNIPPET = """@@ -11,15 +11,17 @@ import { useCurrentUser } from '../hooks/useCurrentUser';
 import { fetchSpecificFriendRequest } from '../services/FriendService';
 import ConfirmationDialog from '../components/ConfirmDialog';
 import { fetchFriendDetails } from '../services/FriendService';
-import AddFriend from './AddFriend';
+import useFriends from '../hooks/useFriends';
+import { useFriend } from '../context/FriendContext';

-const ManageFriends = ({ onFriendDeleted }) => {
+const ManageFriends = () => {
+    const [friendsData, setFriendsData] = useFriends();
     const [expanded, setExpanded] = useState(false);
     const { currentUserId } = useCurrentUser();
     const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
     const [pendingDeleteFriend, setPendingDeleteFriend] = useState({ id: null, name: "" });
-
-
+    const { selectedFriend, clearFriendContext } = useFriend();

     const handleDeleteFriend = async (friendId) => {
         try {
             const friendDetails = await fetchFriendDetails([friendId]);
@@ -56,10 +58,15 @@ const ManageFriends = ({ onFriendDeleted }) => {
                   })
                 ));
           }
-          AddFriend();
-
+          const updatedFriendsData = friendsData.filter(friends => friends.id !== friendId);
+          setFriendsData(updatedFriendsData);
+          if(selectedFriend.id === friendId){
+            clearFriendContext();
+          }
+
         console.log("Friend request(s) deleted for user ID:", friendId);
-        onFriendDeleted(friendId);
+
       } catch (error) {
         console.error("Error deleting friend request:", error);
       }
@@ -72,7 +79,7 @@ return (
         <Typography>My Friends</Typography>
       </AccordionSummary>
       <AccordionDetails>
-        <FriendSearchAndList showDeleteButtons={true} onDelete={handleDeleteFriend} />
+        <FriendSearchAndList friendsData={friendsData} showDeleteButtons={true} onDelete={handleDeleteFriend} />
       </AccordionDetails>
     </Accordion>
     <ConfirmationDialog
"""


def test_team15_patch_snippet_ignores_diff_hunk_header_numbers():
    """
    Team 15 scale test (real patch_snippet):
    - We run the detector on a real GitHub diff hunk
    - We must NOT flag numeric values in diff headers (e.g., @@ -11,15 +11,17 @@)
    - This should hold regardless of the underlying programming language
    """
    code = extract_code_from_patch_snippet(TEAM15_PATCH_SNIPPET)

    findings = detect_magic_numbers_from_code(
        code,
        config=MagicNumberConfig(
            ignored_numbers={"0", "1"},
            ignore_in_constant_declarations=False,
            ignore_in_annotations=True,
            treat_negative_as_literal=True,
        ),
    )

    # This particular snippet has no actual numeric literals in the code body
    # (only diff header numbers). Expect no findings.
    assert findings == []


def test_patch_pipeline_detects_real_literal_in_code_body_language_agnostic():
    """
    Same patch_snippet pipeline, but ensure it DOES detect numeric literals
    when they appear in the actual code lines (not only in diff metadata).

    This fixture is intentionally language-agnostic:
    - "timeout_ms = 3000" looks like Python
    - but even if interpreted as pseudo-code, the detector should still find "3000"
    """
    patch = (
        "@@ -1,1 +1,3 @@\n"
        "+timeout_ms = 3000\n"
        "+print(timeout_ms)\n"
    )

    code = extract_code_from_patch_snippet(patch)

    findings = detect_magic_numbers_from_code(
        code,
        config=MagicNumberConfig(
            ignored_numbers={"0", "1"},
            ignore_in_constant_declarations=False,
            ignore_in_annotations=True,
            treat_negative_as_literal=True,
        ),
    )

    literals = [f.literal for f in findings]
    assert "3000" in literals


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

