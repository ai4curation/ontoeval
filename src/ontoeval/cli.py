from pathlib import Path
import yaml
import click
import json
from typing import List
import pandas as pd

from ontoeval.judges.metadiff_judge import compare_diffs
from ontoeval.runner import create_agent_wrapper, run_agent_on_pr, run_agent_on_pr_wrapper
from .github import analyze_pr, check_for_epics, get_pr_list
from .models import PRBenchmark


@click.group()
def cli():
    """Ontobench - Create benchmarks from ontology changes"""
    pass


@cli.command()
@click.argument('repo')
@click.argument('pr_number', type=int)
@click.option('--output', '-o', help='Output file for benchmark data')
def analyze(repo: str, pr_number: int, output: str = None):
    """Analyze a GitHub PR to extract benchmark data"""
    try:
        result = analyze_pr(repo, pr_number)
        
        if output:
            with open(output, 'w') as f:
                f.write(result.model_dump_json(indent=2))
            click.echo(f"Benchmark data saved to {output}")
        else:
            # Pretty print summary
            click.echo(f"PR #{pr_number}: {result.title}")
            click.echo(f"Files changed: {', '.join(result.files_changed)}")
            click.echo(f"Commits: {len(result.commits)}")
            click.echo(f"Diff size: {len(result.diff)} characters")
            
            # Show ontology-specific info
            if result.has_ontology_changes():
                click.echo("✓ Contains ontology changes")
                if result.is_term_addition():
                    term_ids = result.get_added_term_ids()
                    click.echo(f"✓ Adds new terms: {', '.join(term_ids)}")
            else:
                click.echo("- No ontology changes detected")
                
            # Show linked issues
            if result.linked_issues:
                click.echo(f"🔗 Linked issues: {', '.join(f'#{i.number}' for i in result.linked_issues)}")
                if result.has_new_term_request_labels():
                    click.echo("📝 Has New Term Request (NTR) labels")
                    
                # Show comment counts
                total_issue_comments = sum(i.get_comment_count() for i in result.linked_issues)
                if total_issue_comments > 0:
                    click.echo(f"💬 Issue comments: {total_issue_comments}")
            else:
                click.echo("- No linked issues found")
                
            # Show PR comment info
            if result.get_comment_count() > 0:
                click.echo(f"💬 PR comments: {result.get_comment_count()}")
                authors = result.get_authors()
                if len(authors) > 1:
                    click.echo(f"👥 Discussion participants: {', '.join(authors)}")
            else:
                click.echo("- No PR comments")
            
    except Exception as e:
        click.echo(f"Error analyzing PR: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument('repo')
@click.option('--state', default='merged', help='PR state: open, closed, merged, or all')
@click.option('--limit', '-l', default=50, help='Maximum number of PRs to process')
@click.option('--output', '-o', required=True, help='Output JSON file for benchmark dataset')
@click.option('--ontology-only', is_flag=True, help='Only include PRs with ontology changes')
def batch(repo: str, state: str, limit: int, output: str, ontology_only: bool):
    """Analyze multiple PRs from a repository to create a benchmark dataset"""
    try:
        click.echo(f"Fetching {state} PRs from {repo} (limit: {limit})...")
        pr_numbers = get_pr_list(repo, state, limit)
        click.echo(f"Found {len(pr_numbers)} PRs to analyze")
        
        benchmarks: List[PRBenchmark] = []
        failed_prs: List[int] = []
        
        with click.progressbar(pr_numbers, label='Analyzing PRs') as bar:
            for pr_num in bar:
                try:
                    benchmark = analyze_pr(repo, pr_num)
                    benchmark.populate_derived_fields()
                    # Filter for ontology changes if requested
                    if ontology_only and not benchmark.has_ontology_changes():
                        continue
                        
                    benchmarks.append(benchmark)
                except Exception as e:
                    click.echo(f"\nWarning: Failed to analyze PR #{pr_num}: {e}")
                    failed_prs.append(pr_num)
                    continue

        epics_pr_numbers = check_for_epics(benchmarks)
        for b in benchmarks:
            b.part_of_epic = b.pr_number in epics_pr_numbers
        
        # Save results
        benchmark_data = {
            'metadata': {
                'repo': repo,
                'state': state,
                'total_prs_found': len(pr_numbers),
                'total_prs_analyzed': len(benchmarks),
                'failed_prs': failed_prs,
                'ontology_only_filter': ontology_only
            },
            'benchmarks': [json.loads(b.model_dump_json()) for b in benchmarks]
        }
        
        with open(output, 'w') as f:
            json.dump(benchmark_data, f, indent=2)
        
        # Summary
        ontology_count = sum(1 for b in benchmarks if b.has_ontology_changes())
        term_additions = sum(1 for b in benchmarks if b.is_term_addition())
        with_issues = sum(1 for b in benchmarks if b.linked_issues)
        ntr_count = sum(1 for b in benchmarks if b.has_new_term_request_labels())
        total_pr_comments = sum(b.get_comment_count() for b in benchmarks)
        total_issue_comments = sum(
            sum(issue.get_comment_count() for issue in b.linked_issues) 
            for b in benchmarks
        )
        
        click.echo(f"\n✅ Analysis complete!")
        click.echo(f"📊 Results saved to: {output}")
        click.echo(f"📈 Total benchmarks: {len(benchmarks)}")
        click.echo(f"🧬 With ontology changes: {ontology_count}")
        click.echo(f"➕ Term additions: {term_additions}")
        click.echo(f"🔗 With linked issues: {with_issues}")
        click.echo(f"📝 New Term Requests: {ntr_count}")
        click.echo(f"💬 Total PR comments: {total_pr_comments}")
        click.echo(f"💬 Total issue comments: {total_issue_comments}")
        if failed_prs:
            click.echo(f"⚠️  Failed PRs: {len(failed_prs)}")
        
    except Exception as e:
        click.echo(f"Error processing repository: {e}", err=True)
        raise click.Abort()
    
@cli.command()
@click.option('--config-path', '-c', required=True, help='Path to the agent config file')
@click.argument('pr', type=int)
def run(config_path: str, pr: int):
    """Run an agent on a PR"""
    agent = create_agent_wrapper(config_path)
    result = run_agent_on_pr(agent, pr)
    print(yaml.dump(result.model_dump()))


@cli.command()
@click.option('--state', default='merged', help='PR state: open, closed, merged, or all')
@click.option('--from-pr', '-S', type=int, help='Start from this PR number (note that we are working backwards from most recent PR)')
@click.option('--limit', '-l', default=50, help='Maximum number of PRs to process')
@click.option('--output', '-o', required=True, help='Output JSON file for benchmark dataset')
@click.option('--markdown-directory', '-R', help='Path to dir to export individual markdown files for each PR')
@click.option('--max-diff-size-lines', '-m', default=10_000, help='Maximum diff size (number of lines, including context) to consider')
@click.option('--ontology-only', is_flag=True, help='Only include PRs with ontology changes')
@click.option('--must-include-file', '-I', multiple=True, help='The diff must modify at least one of these files')
@click.option('--config-path', '-c', required=True, help='Path to the agent config file')
@click.option('--use-llm-judge/--no-use-llm-judge', '-j', default=True, help='Whether to use the LLM judge to compare the diffs')
@click.option('--exclude-epics/--no-exclude-epics',
              default=True, 
              show_default=True,
              help='Whether to exclude PRs that are part of an epic. These are less meaningful to evaluate.')
def run_all(
    config_path: str, 
    state: str, 
    from_pr: int, 
    limit: int, 
    output: str, 
    markdown_directory: str, 
    ontology_only: bool, 
    max_diff_size_lines: int, 
    must_include_file: list[str], 
    exclude_epics: bool,
    use_llm_judge: bool,
):
    """Run an agent on all PRs"""
    results = []
    agent = create_agent_wrapper(config_path)
    # diffs_stream = open("diffs.md", "w")
    pr_numbers = get_pr_list(agent.repo, state, limit, from_pr=from_pr)
    all_prs = []
    n = 0
    for pr_num in pr_numbers:
        click.echo(f"🔍 Analyzing PR #{pr_num}")
        pr = analyze_pr(agent.repo, pr_num)
        pr.populate_derived_fields()
        all_prs.append(pr)
        if pr.diff_size_lines > max_diff_size_lines:
            click.echo(f"🚫 Skipping PR #{pr_num} because it has a diff size of {pr.diff_size_lines} lines")
            continue
        if ontology_only and not pr.has_ontology_changes():
            # Add a emoji to the output
            click.echo(f"🚫 Skipping PR #{pr_num} because it has no ontology changes")
            continue
        if not pr.linked_issues:
            click.echo(f"🚫 Skipping PR #{pr_num} because it has no linked issues")
            continue
        if must_include_file:
            exclude = True
            for file in must_include_file:
                if file in pr.files_changed:                    
                    exclude = False
                    break
            if exclude:
                click.echo(f"🚫 Skipping PR #{pr_num} because it does not modify any of the required files")
                continue
        click.echo(f"🔍 Running agent on PR #{pr_num}")
        try:
            result = run_agent_on_pr_wrapper(config_path, pr_num)
            if not result.diff:
                # TODO: there may be a variety of causes...
                click.echo(f"🚫 No diff found on PR #{pr_num}")
                continue
            if "Please retry if you think this is a transient or recoverable error" in result.stdout:
                click.echo(f"🚫 Transient or recoverable error on PR #{pr_num}")
                # clear the cache for this specific set of arguments
                #clear_cache_for_pr(config_path, pr_num)
                calc = run_agent_on_pr_wrapper.call_and_shelve(config_path, pr_num)
                calc.clear()
                result = run_agent_on_pr_wrapper(config_path, pr_num)
                click.echo(f"✅ re-ran agent on PR #{pr_num}")
                raise ValueError("Transient or recoverable error")
        except Exception as e:
            click.echo(f"🚫 Error running agent on PR #{pr_num}: {e}")
            continue
        # combine the result with the pr; flatten
        pr.agent_stdout = result.stdout
        pr.agent_stderr = result.stderr            

        # TODO: refactor this part
        comparison = compare_diffs(pr.diff, result.diff)
        pr.predicted_diff = result.diff
        pr.predicted_diff_identical = comparison.identical
        pr.predicted_diff_metadiff = comparison.metadiff
        pr.predicted_diff_similarity = comparison.similarity
        pr.predicted_diff_changes_in_common = comparison.changes_in_common
        pr.changes_unique_to_target = comparison.changes_in_diff1
        pr.changes_unique_to_prediction = comparison.changes_in_diff2

        from ontoeval.judges import metadiff_judge
        judges = [metadiff_judge]
        if use_llm_judge:
            from ontoeval.judges import llm_judge
            judges.append(llm_judge)
        pr.comparisons = {}
        for judge in judges:
            c = judge.compare_diffs(pr.diff, result.diff, pr_benchmark=pr)
            pr.comparisons[judge.__name__.split(".")[-1]] = c

        from ontoeval.renderers import markdown
        renderer = markdown
        # md_stanzas.append(renderer.render_result(pr))
        if markdown_directory:
            if isinstance(markdown_directory, str):
                markdown_directory = Path(markdown_directory)
            # create the directory if it doesn't exist
            markdown_directory.mkdir(parents=True, exist_ok=True)
            with open(markdown_directory / f"{pr_num}.md", "w") as f:
                f.write(renderer.render_result(pr))

        obj = pr.model_dump(exclude_none=False)
        click.echo(f"## COMPARISON:\n{yaml.dump(comparison.model_dump())}")
        #click.echo(f"## PREDICTED DIFF:\n{result.diff}")
        #click.echo(f"## TARGET DIFF:\n{pr.diff}")
        
        if comparison.identical:
            click.echo(f"🔍 Diff is identical: {comparison.similarity}")
        else:
            click.echo(f"❌ Diff is not identical: {comparison.similarity}")
            
        print(obj["predicted_diff_similarity"])

        for cname, c in pr.comparisons.items():
            for k, v in c.model_dump().items():
                obj[f"{cname}_{k}"] = v

        results.append(obj)
        n += 1
        # print(yaml.dump(obj))
        
        click.echo(f"✅ PR #{pr_num} analyzed")
    epics_pr_numbers = check_for_epics(all_prs)
    click.echo(f"🔍 Epics: {epics_pr_numbers}")
    for r in results:
        r["part_of_epic"] = r["pr_number"] in epics_pr_numbers
    if exclude_epics:   
        results = [r for r in results if not r["part_of_epic"]]
    with open(output, 'w') as f:
        json.dump(results, f, indent=2)
    click.echo(f"✅ {n} PRs analyzed")

@cli.command()
@click.argument('files', nargs=-1)
@click.option('--use-union/--no-use-union', default=False, show_default=True, help='Whether to use the union of PRs from all experiments')
@click.option('--include-run-id/--no-include-run-id', default=False, show_default=True, help='Whether to include the run_id in the experiment id')
@click.option('--output', '-o', required=True, help='Output JSON file for combined results')
def combine(files: list[str], output: str, use_union: bool, include_run_id: bool):
    """Combines multiple run outputs into a single consolidated file"""
    all_results = []
    cols_to_average = ["metadiff_judge_similarity", "llm_judge_score_diff"]
    
    results_by_experiment = {}
    prs_by_experiment = {}
    for file in files:
        file = Path(file)
        with open(file, 'r') as f:
            results = json.load(f)
            click.echo(f"🔍 File: {file} total results (unfiltered): {len(results)}")
            results = [r for r in results if all(c in r for c in cols_to_average)]
            experiment_id = str(file.parent.parent.stem)
            if include_run_id:
                experiment_id = f"{experiment_id}_{file.stem}"
            for result in results:
                if "experiment_id" not in result:
                    result["experiment_id"] = experiment_id
            results_by_experiment[experiment_id] = results
            prs_by_experiment[experiment_id] = {r["pr_number"] for r in results}
            click.echo(f"🔍 Experiment {experiment_id}: {prs_by_experiment[experiment_id]}")
    
    pr_ids_in_union = set.union(*prs_by_experiment.values())
    click.echo(f"🔍 PRs in union: {len(pr_ids_in_union)}")
    pr_ids_in_common = set.intersection(*prs_by_experiment.values())
    click.echo(f"🔍 PRs in common: {len(pr_ids_in_common)}")
    click.echo(f"🔍 PRs in union but not in common: {len(pr_ids_in_union - pr_ids_in_common)}")

    # make a df, every row is a pr, every column is an experiment, value is true/false,
    # depending on whether the pr is in the experiment
    pr_ids_sorted = sorted(pr_ids_in_union)
    experiment_ids_sorted = sorted(results_by_experiment.keys())
    import pandas as pd
    pr_experiment_matrix = pd.DataFrame(
        False,
        index=pr_ids_sorted,
        columns=experiment_ids_sorted
    )
    for experiment_id, pr_set in prs_by_experiment.items():
        for pr_id in pr_set:
            pr_experiment_matrix.at[pr_id, experiment_id] = True
    click.echo(f"\n🔍 PR presence matrix (rows=PRs, cols=experiments):\n{pr_experiment_matrix.to_string()}")

    # combine the results
    for experiment_id, results in results_by_experiment.items():
        for r in results:
            if not use_union:
                if r["pr_number"] not in pr_ids_in_common:
                    continue
            all_results.append(r)
    
    # Save combined results
    with open(output, 'w') as f:
        json.dump(all_results, f, indent=2)

    df = pd.DataFrame(all_results)
    print(df.columns)
    
    # drop all rows where any of the cols_to_average are None
    df = df.dropna(subset=cols_to_average)
    print(df)
    # get averages grouped by experiment_id
    df_averaged = df.groupby("experiment_id")[cols_to_average].mean()
    click.echo(f"🔍 Averaged results: {df_averaged}")
    # write the averaged results to stdout
    click.echo(f"🔍 Averaged results: {df_averaged}")
        
    click.echo(f"✅ Combined {len(files)} files into {output}")
    click.echo(f"📊 Total results: {len(all_results)}")

def main():
    cli()


if __name__ == '__main__':
    main()