"""Integration tests for ontoeval using real GitHub data."""

import pytest
from ontoeval.github import analyze_pr
from ontoeval.models import PRBenchmark


def test_analyze_pr_with_ontology_changes():
    """Test analyzing a PR that adds a new GO term."""
    result = analyze_pr("geneontology/go-ontology", 30347)
    
    # Should return a proper Pydantic model
    assert isinstance(result, PRBenchmark)
    
    # Basic structure
    assert result.repo == "geneontology/go-ontology"
    assert result.pr_number == 30347
    assert result.title == "Add new term: spermatid mitochondrial nucleoid elimination"
    
    # Should have commits and file changes
    assert len(result.commits) > 0
    assert 'src/ontology/go-edit.obo' in result.files_changed
    
    # Should have actual diff content
    assert len(result.diff) > 0
    assert '[Term]' in result.diff  # OBO format term addition
    assert 'GO:7770002' in result.diff  # The new term ID
    
    # Should have commit SHAs
    assert result.head_commit
    assert result.base_commit
    assert result.head_commit != result.base_commit
    
    # Test our helper methods
    assert result.has_ontology_changes() is True
    assert result.is_term_addition() is True
    added_terms = result.get_added_term_ids()
    assert 'GO:7770002' in added_terms


def test_analyze_pr_design_pattern_changes():
    """Test analyzing a PR that changes design patterns (not ontology)."""
    result = analyze_pr("geneontology/go-ontology", 30437)
    
    assert isinstance(result, PRBenchmark)
    assert result.repo == "geneontology/go-ontology"
    assert result.pr_number == 30437
    assert "design pattern" in result.title.lower()
    
    # Should be a design pattern file, not the main ontology
    assert any('design_patterns' in f for f in result.files_changed)
    assert 'src/ontology/go-edit.obo' not in result.files_changed
    
    # Should detect no ontology changes
    assert result.has_ontology_changes() is False
    assert result.is_term_addition() is False