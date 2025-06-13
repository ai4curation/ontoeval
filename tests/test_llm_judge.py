import json
import pytest
from pathlib import Path
from ontoeval.judges.llm_judge import compare_diffs
from ontoeval.models import PRBenchmark

INPUT_DIR = Path(__file__).parent / "input" 

@pytest.mark.parametrize("input_file", ["example-result", "example-result-2", "example-result-3"])
def test_llm_judge(input_file: str):
    with open(INPUT_DIR / f"{input_file}.json", "r") as f:
        data = json.load(f)
    pr = PRBenchmark(**data)    
    comparison = compare_diffs(pr.diff, pr.predicted_diff, pr_benchmark=pr)
    import yaml
    print(yaml.dump(comparison.model_dump()))