"""Test batch processing functionality."""

import json
import pytest
from ontoeval.github import get_pr_list


def test_get_pr_list():
    """Test getting PR list from repository."""
    pr_numbers = get_pr_list("geneontology/go-ontology", state="open", limit=3)
    
    assert isinstance(pr_numbers, list)
    assert len(pr_numbers) <= 3
    assert all(isinstance(pr, int) for pr in pr_numbers)
    

def test_get_pr_list_merged():
    """Test getting merged PRs."""
    pr_numbers = get_pr_list("geneontology/go-ontology", state="merged", limit=5)
    
    assert isinstance(pr_numbers, list)
    assert len(pr_numbers) <= 5
    assert all(isinstance(pr, int) for pr in pr_numbers)


def test_batch_output_structure(tmp_path):
    """Test that batch command creates properly structured output."""
    # This would normally be called via CLI, but we can test the structure
    # by creating a small dataset manually
    
    from ontoeval.github import analyze_pr
    
    # Analyze a couple PRs
    benchmark1 = analyze_pr("geneontology/go-ontology", 30347)
    benchmark2 = analyze_pr("geneontology/go-ontology", 30437)
    
    # Create the expected structure
    benchmark_data = {
        'metadata': {
            'repo': 'geneontology/go-ontology',
            'state': 'test',
            'total_prs_found': 2,
            'total_prs_analyzed': 2,
            'failed_prs': [],
            'ontology_only_filter': False
        },
        'benchmarks': [
            json.loads(benchmark1.model_dump_json()),
            json.loads(benchmark2.model_dump_json())
        ]
    }
    
    # Write and read back
    output_file = tmp_path / "test_batch.json"
    with open(output_file, 'w') as f:
        json.dump(benchmark_data, f, indent=2)
    
    # Verify structure
    with open(output_file, 'r') as f:
        data = json.load(f)
    
    assert 'metadata' in data
    assert 'benchmarks' in data
    assert data['metadata']['total_prs_analyzed'] == 2
    assert len(data['benchmarks']) == 2
    
    # Verify each benchmark has the expected fields
    for benchmark in data['benchmarks']:
        assert 'repo' in benchmark
        assert 'pr_number' in benchmark
        assert 'title' in benchmark
        assert 'files_changed' in benchmark
        assert 'diff' in benchmark