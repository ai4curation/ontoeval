"""Test comment and metadata functionality."""

import pytest
from ontoeval.github import get_comments, analyze_pr
from ontoeval.models import GitHubComment


def test_analyze_pr_has_rich_metadata():
    """Test that PR analysis includes all rich metadata."""
    result = analyze_pr("geneontology/go-ontology", 30347)
    
    # Should have all GitHubItem fields
    assert result.number == 30347
    assert result.pr_number == 30347  # Should match
    assert result.title
    assert result.author
    assert result.created_at
    assert result.updated_at
    assert result.state
    assert isinstance(result.labels, list)
    assert isinstance(result.comments, list)
    
    # Test helper methods
    assert isinstance(result.get_comment_count(), int)
    assert isinstance(result.get_authors(), list)
    assert result.author in result.get_authors()
    

def test_linked_issue_has_rich_metadata():
    """Test that linked issues include all metadata."""
    result = analyze_pr("geneontology/go-ontology", 30347)
    
    assert len(result.linked_issues) > 0
    issue = result.linked_issues[0]
    
    # Should have all GitHubItem fields
    assert issue.number == 30344
    assert issue.title
    assert issue.author
    assert issue.created_at  
    assert issue.updated_at
    assert issue.state in ["OPEN", "CLOSED"]
    assert isinstance(issue.labels, list)
    assert isinstance(issue.comments, list)
    
    # Test specific methods
    assert issue.is_new_term_request() is True
    assert isinstance(issue.get_comment_count(), int)
    assert isinstance(issue.get_authors(), list)
    

def test_get_all_discussion_text():
    """Test getting comprehensive discussion text."""
    result = analyze_pr("geneontology/go-ontology", 30347)
    
    discussion_text = result.get_all_discussion_text()
    
    # Should contain PR body
    if result.body:
        assert "PR Body:" in discussion_text
        
    # Should contain issue information
    assert "Issue #30344 Body:" in discussion_text
    assert "mitochondrial" in discussion_text.lower()
    

def test_github_comment_model():
    """Test that GitHubComment model structure is correct."""
    # This tests the model structure without requiring actual GitHub API calls
    from ontoeval.models import GitHubComment
    from datetime import datetime
    
    comment_data = {
        "id": "xxx",
        "author": "testuser",
        "body": "This is a test comment",
        "created_at": "2025-01-01T00:00:00Z",
        "url": "https://github.com/test/repo/issues/1#issuecomment-123456"
    }
    
    comment = GitHubComment(**comment_data)
    
    assert comment.id == "xxx"
    assert comment.author == "testuser"
    assert comment.body == "This is a test comment"
    assert isinstance(comment.created_at, datetime)
    # assert isinstance(comment.updated_at, datetime)
    

def test_inheritance_structure():
    """Test that inheritance between GitHubItem, GitHubIssue, and PRBenchmark works."""
    result = analyze_pr("geneontology/go-ontology", 30347)
    
    # PRBenchmark should inherit from GitHubItem
    assert hasattr(result, 'get_comment_count')
    assert hasattr(result, 'get_authors')
    assert hasattr(result, 'get_comment_text')
    
    # Should also have PR-specific methods
    assert hasattr(result, 'has_ontology_changes')
    assert hasattr(result, 'get_all_discussion_text')
    
    # Linked issues should inherit from GitHubItem too
    if result.linked_issues:
        issue = result.linked_issues[0]
        assert hasattr(issue, 'get_comment_count')
        assert hasattr(issue, 'get_authors')
        assert hasattr(issue, 'is_new_term_request')


def test_authors_aggregation():
    """Test that we correctly aggregate authors from item and comments."""
    result = analyze_pr("geneontology/go-ontology", 30347)
    
    authors = result.get_authors()
    
    # Should include the PR author
    assert result.author in authors
    
    # Should be sorted and unique
    assert authors == sorted(set(authors))
    
    # Test for linked issues too
    for issue in result.linked_issues:
        issue_authors = issue.get_authors()
        assert issue.author in issue_authors