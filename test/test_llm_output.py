#!/usr/bin/env python3
"""
Test script for LLM output in branch name assessment.

This script tests the assess_branch_meaningfulness function to:
1. Verify the LLM provides reasons before predictions
2. Check if reasons make sense
3. Validate confidence scores are reasonable
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from event_labelling.CodeStructure_Branching.code_structure_and_branching import assess_branch_meaningfulness


def test_branch_assessment():
    """Test the assess_branch_meaningfulness function with various examples."""
    
    test_cases = [
        {
            "branch_name": "feature/user-authentication",
            "pr_title": "Add user login functionality",
            "pr_description": "Implements OAuth2 authentication for user login",
            "expected_label": "Meaningful Branch Name",
            "description": "Clear feature branch matching PR purpose"
        },
        {
            "branch_name": "fix/navbar-bug",
            "pr_title": "Fix navbar alignment issue",
            "pr_description": "Resolves the navbar alignment problem on mobile devices",
            "expected_label": "Meaningful Branch Name",
            "description": "Clear fix branch matching PR purpose"
        },
        {
            "branch_name": "test",
            "pr_title": "Add new feature",
            "pr_description": "This PR adds a new feature",
            "expected_label": "Random Branch Name",
            "description": "Generic branch name not matching PR"
        },
        {
            "branch_name": "update",
            "pr_title": "Refactor database queries",
            "pr_description": "Optimizes database query performance",
            "expected_label": "Random Branch Name",
            "description": "Generic branch name not matching PR"
        },
        {
            "branch_name": "refactor/api-endpoints",
            "pr_title": "Refactor API endpoints",
            "pr_description": "Restructures API endpoints for better organization",
            "expected_label": "Meaningful Branch Name",
            "description": "Clear refactor branch matching PR"
        },
        {
            "branch_name": "final",
            "pr_title": "Update documentation",
            "pr_description": "Updates README with new instructions",
            "expected_label": "Random Branch Name",
            "description": "Generic branch name not matching PR"
        },
        {
            "branch_name": "feature/payment-integration",
            "pr_title": "Add payment processing",
            "pr_description": "Integrates Stripe payment gateway",
            "expected_label": "Meaningful Branch Name",
            "description": "Feature branch matching payment-related PR"
        },
        {
            "branch_name": "xyz123",
            "pr_title": "Fix critical bug",
            "pr_description": "Fixes a critical security vulnerability",
            "expected_label": "Random Branch Name",
            "description": "Random/nonsensical branch name"
        },
    ]
    
    print("=" * 80)
    print("Testing LLM Output for Branch Name Assessment")
    print("=" * 80)
    print()
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"Test Case {i}: {test_case['description']}")
        print(f"{'='*80}")
        print(f"Branch Name: {test_case['branch_name']}")
        print(f"PR Title: {test_case['pr_title']}")
        print(f"PR Description: {test_case['pr_description']}")
        print(f"Expected Label: {test_case['expected_label']}")
        print()
        
        try:
            label, reason, confidence_score, llm_output = assess_branch_meaningfulness(
                test_case['branch_name'],
                test_case['pr_title'],
                test_case['pr_description']
            )
            
            print(f"✓ LLM Response Received")
            print(f"\n{'─'*80}")
            print("EXTRACTED RESULTS:")
            print(f"{'─'*80}")
            print(f"Label: {label}")
            print(f"Reason: {reason}")
            print(f"Confidence Score: {confidence_score}")
            print(f"\n{'─'*80}")
            print("FULL LLM OUTPUT:")
            print(f"{'─'*80}")
            print(llm_output)
            print()
            
            # Validation checks
            checks = []
            
            # Check 1: Reason should be present and not empty
            if reason and reason != "No explicit reason provided by LLM":
                checks.append(("✓", "Reason provided", "Reason is present"))
            else:
                checks.append(("✗", "Reason missing", "No reason found in output"))
            
            # Check 2: Reason should make sense (basic heuristic: should be more than 10 chars)
            if len(reason) > 10:
                checks.append(("✓", "Reason length", f"Reason has {len(reason)} characters"))
            else:
                checks.append(("⚠", "Reason too short", f"Reason only has {len(reason)} characters"))
            
            # Check 3: Confidence score should be in valid range
            if 0 <= confidence_score <= 100:
                checks.append(("✓", "Confidence score valid", f"Score: {confidence_score}/100"))
            else:
                checks.append(("✗", "Confidence score invalid", f"Score: {confidence_score} (should be 0-100)"))
            
            # Check 4: Confidence score should be reasonable
            if confidence_score >= 80:
                checks.append(("✓", "High confidence", "Confidence >= 80 (high)"))
            elif confidence_score >= 50:
                checks.append(("⚠", "Medium confidence", "Confidence 50-79 (medium)"))
            else:
                checks.append(("⚠", "Low confidence", "Confidence < 50 (low)"))
            
            # Check 5: Label should match expected (if provided)
            if test_case.get('expected_label'):
                if label == test_case['expected_label']:
                    checks.append(("✓", "Label matches expected", f"Got: {label}"))
                else:
                    checks.append(("✗", "Label mismatch", f"Expected: {test_case['expected_label']}, Got: {label}"))
            
            # Check 6: Reason should mention branch name or PR context
            reason_lower = reason.lower()
            branch_lower = test_case['branch_name'].lower()
            pr_title_lower = test_case['pr_title'].lower()
            
            if branch_lower in reason_lower or any(word in reason_lower for word in pr_title_lower.split() if len(word) > 3):
                checks.append(("✓", "Reason references context", "Reason mentions branch or PR context"))
            else:
                checks.append(("⚠", "Reason may lack context", "Reason doesn't clearly reference branch or PR"))
            
            print(f"\n{'─'*80}")
            print("VALIDATION CHECKS:")
            print(f"{'─'*80}")
            for status, check_name, details in checks:
                print(f"{status} {check_name}: {details}")
            
            # Store results
            results.append({
                "test_case": i,
                "description": test_case['description'],
                "branch_name": test_case['branch_name'],
                "label": label,
                "expected_label": test_case.get('expected_label'),
                "reason": reason,
                "confidence_score": confidence_score,
                "llm_output": llm_output,
                "checks": checks
            })
            
        except Exception as e:
            print(f"✗ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append({
                "test_case": i,
                "description": test_case['description'],
                "error": str(e)
            })
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    total_tests = len(test_cases)
    successful_tests = sum(1 for r in results if "error" not in r)
    failed_tests = total_tests - successful_tests
    
    print(f"Total Tests: {total_tests}")
    print(f"Successful: {successful_tests}")
    print(f"Failed: {failed_tests}")
    
    if successful_tests > 0:
        avg_confidence = sum(r.get("confidence_score", 0) for r in results if "confidence_score" in r) / successful_tests
        print(f"Average Confidence Score: {avg_confidence:.1f}/100")
        
        # Count label matches
        label_matches = sum(1 for r in results 
                           if "expected_label" in r and r.get("label") == r.get("expected_label"))
        if label_matches > 0:
            print(f"Label Matches: {label_matches}/{successful_tests}")
    
    print("\n" + "=" * 80)
    print("DETAILED RESULTS")
    print("=" * 80)
    
    for result in results:
        if "error" in result:
            print(f"\nTest {result['test_case']}: ✗ ERROR - {result['error']}")
        else:
            print(f"\nTest {result['test_case']}: {result['description']}")
            print(f"  Branch: {result['branch_name']}")
            print(f"  Label: {result['label']}")
            print(f"  Confidence: {result['confidence_score']}/100")
            print(f"  Reason length: {len(result['reason'])} chars")
            if result.get('expected_label'):
                match = "✓" if result['label'] == result['expected_label'] else "✗"
                print(f"  Expected match: {match}")
    
    return results


if __name__ == "__main__":
    print("Starting LLM Output Tests...")
    print("Note: This requires Ollama to be running with the model specified in code_structure_and_branching.py")
    print()
    
    results = test_branch_assessment()
    
    print("\n" + "=" * 80)
    print("Tests completed!")
    print("=" * 80)

