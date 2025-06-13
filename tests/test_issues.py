"""Test issue linking functionality."""

import pytest
from ontoeval.github import extract_issue_numbers_from_text, get_issue_info, analyze_pr


def test_extract_issue_numbers_basic():
    """Test extracting issue numbers from text."""
    text = "This fixes #123 and closes #456"
    numbers = extract_issue_numbers_from_text(text)
    assert numbers == [123, 456]


def test_extract_issue_numbers_various_patterns():
    """Test different issue linking patterns."""
    test_cases = [
        ("fixes #123", [123]),
        ("Fixes #456", [456]),
        ("closes #789", [789]),
        ("resolves #111", [111]),
        ("This addresses issue #222", [222]),
        ("#333 is fixed", [333]),
        ("Multiple issues: #111, #222, #333", [111, 222, 333]),
        ("No issues here", []),
        ("PR #123 fixes #456", [123, 456]),  # Should extract both
    ]
    
    for text, expected in test_cases:
        result = extract_issue_numbers_from_text(text)
        assert result == expected, f"Failed for text: '{text}', got {result}, expected {expected}"


def test_extract_issue_numbers_edge_cases():
    """Test edge cases for issue number extraction."""
    # Should not extract these
    edge_cases = [
        ("Version 1.2.3", []),  # No # symbol
        ("##123", []),  # Double hash
        ("#", []),  # Just hash
        ("", []),  # Empty string
        (None, []),  # None input
    ]
    
    for text, expected in edge_cases:
        result = extract_issue_numbers_from_text(text)
        assert result == expected, f"Failed for text: '{text}'"


def test_get_issue_info():
    """Test fetching issue information from GitHub."""
    # Use the issue we know exists and is linked to PR 30347
    issue = get_issue_info("geneontology/go-ontology", 30344)
    
    assert issue.number == 30344
    assert "spermatid" in issue.title.lower()
    assert issue.url
    assert issue.state in ["OPEN", "CLOSED"]
    assert "New term request" in issue.labels


def test_analyze_pr_with_linked_issues():
    """Test that PR analysis includes linked issues."""
    result = analyze_pr("geneontology/go-ontology", 30347)
    
    # Should have found the linked issue
    assert len(result.linked_issues) > 0
    
    # Check the specific issue we know is linked
    issue_numbers = result.get_linked_issue_numbers()
    assert 30344 in issue_numbers
    
    # Should detect NTR labels
    assert result.has_new_term_request_labels() is True
    
    # Verify the issue details
    issue_30344 = next(issue for issue in result.linked_issues if issue.number == 30344)
    assert "New term request" in issue_30344.labels
    assert issue_30344.state in ["OPEN", "CLOSED"]


def test_analyze_pr_without_linked_issues():
    """Test PR analysis when no issues are linked."""
    result = analyze_pr("geneontology/go-ontology", 30437)
    
    # This PR has no linked issues
    assert len(result.linked_issues) == 0
    assert result.get_linked_issue_numbers() == []
    assert result.has_new_term_request_labels() is False