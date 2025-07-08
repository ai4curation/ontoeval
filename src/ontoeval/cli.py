from asyncio import create_task
from collections import defaultdict
from pathlib import Path
import yaml
import click
import json
from typing import List
import pandas as pd

from ontoeval.judges.metadiff_judge import compare_diffs
from ontoeval.runner import change_directory, copy_file_contents, create_agent_wrapper, run_agent_on_pr, run_agent_on_pr_wrapper
from ontoeval.utils.argillo_utils import ACTION_LABELS
from ontoeval.utils.diff_utils import trim_diff
from ontoeval.utils.replay_diff import replay_diff
from ontoeval.utils.self_improver import summarize_suggestions
from .github import analyze_pr, check_for_epics, get_pr_list
from .models import AgentOutput, GitHubComment, PRBenchmark, UserEvalTask


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

        click.echo(f"🔍 {len(benchmarks)} benchmarks")
        epics_pr_numbers = check_for_epics(benchmarks)
        for b in benchmarks:
            b.part_of_epic = b.pr_number in epics_pr_numbers
        
        click.echo(f"🔍 {len(benchmarks)} benchmarks after filtering for epics")
        
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
@click.option('--system-prompt', '-S', help='System prompt template to use (overrides default)')
@click.option('--pass-through/--no-pass-through', '-P', default=False, help='Pass with no system prompt')
@click.argument('command')
def prompt(config_path: str, system_prompt: str, pass_through: bool, command: str):
    """Test a runner"""
    agent = create_agent_wrapper(config_path)
    if pass_through:
        system_prompt = '{input_text}'
    if system_prompt:
        if '{' not in system_prompt and command:
            click.UsageError(f"🚫 System prompt must contain {{command}} if command is provided")
        agent.prompt = system_prompt
    local_path = agent.repo_local_path()
    with change_directory(local_path):
        print(f"🔍 Copying {len(agent.file_contents)} file contents to {local_path}")
        copy_file_contents(agent)
        result = agent.run(command)
    print(yaml.dump(result.model_dump()))

    
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
@click.option('--json-directory', '-J', help='Path to dir to export individual json files for each PR')
@click.option('--problem-directory', '-P', help='Path to dir to export individual problem files for each PR that fails to process')
@click.option('--max-diff-size-lines', '-m', default=10_000, help='Maximum diff size (number of lines, including context) to consider')
@click.option('--cache-only', is_flag=True, help='Only use the cache, do not re-run the agent')
@click.option('--ontology-only', is_flag=True, help='Only include PRs with ontology changes')
@click.option('--redo-stdout-threshold', type=int, default=None, help='Redo run if the diff is null and the character length of stdout is less than this threshold. This is useful for case where the agent did not raise an error (e.g. goose) but just stopped running.')
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
    json_directory: str,
    problem_directory: str,
    ontology_only: bool, 
    redo_stdout_threshold: int,
    max_diff_size_lines: int, 
    cache_only: bool,
    must_include_file: list[str], 
    exclude_epics: bool,
    use_llm_judge: bool,
):
    """Run an agent on all PRs"""
    if not json_directory:
        # note: this is now also used as a cache
        json_directory = Path(output).parent / "json"
    if isinstance(json_directory, str):
        json_directory = Path(json_directory)
    json_directory.mkdir(parents=True, exist_ok=True)
    if not problem_directory:
        problem_directory = Path(output).parent / "problems"

    def write_problem(problem_directory: str, pr: PRBenchmark, problem: dict, problem_type: str):
        """Write a problem to a file"""
        print(f"🔍 Writing problem to {problem_directory}")
        if isinstance(problem_directory, str):
            problem_directory = Path(problem_directory)
        # create the directory if it doesn't exist
        problem_directory.mkdir(parents=True, exist_ok=True)
        with open(problem_directory / f"{pr.pr_number}_{problem_type}.json", "w") as f:
            obj = {**pr.model_dump(exclude_none=False), **problem}
            json.dump(obj, f, indent=2)
    results = []
    agent = create_agent_wrapper(config_path)
    # diffs_stream = open("diffs.md", "w")
    pr_numbers = get_pr_list(agent.repo, state, limit, from_pr=from_pr)
    all_prs = []
    n = 0
    for i, pr_num in enumerate(pr_numbers):
        click.echo(f"🔍 Analyzing PR #{pr_num} ({i+1} of {len(pr_numbers)})")
        json_pr_path = json_directory / f"{pr_num}.json"
        if json_pr_path.exists():
            # use a different emoji
            click.echo(f"🔄 Loading PR #{pr_num} from cache: {json_pr_path}")
            with open(json_pr_path, "r") as f:
                obj = json.load(f)
                pr = PRBenchmark(**obj)
                # TODO: smarter way to reconstitute objects
                #from ontoeval.judges.llm_judge import LLMJudgeComparison
                #from ontoeval.judges.metadiff_judge import MetadiffComparison
                #pr.comparisons["llm_judge"] = LLMJudgeComparison(**obj["comparisons"]["llm_judge"])
                #pr.comparisons["metadiff_judge"] = MetadiffComparison(**obj["comparisons"]["metadiff_judge"])
                #all_prs.append(pr)
        elif cache_only:
            click.echo(f"🚫 Skipping PR #{pr_num} because it is not in the cache")
            continue
        else:
            pr = analyze_pr(agent.repo, pr_num)
            pr.populate_derived_fields()
            all_prs.append(pr)
            if pr.diff_size_lines > max_diff_size_lines:
                click.echo(f"🚫 Skipping PR #{pr_num} because it has a diff size of {pr.diff_size_lines} lines")
                write_problem(problem_directory, pr, {"diff_size_lines": pr.diff_size_lines}, "diff_too_large")
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
                    click.echo(f"🚫 No diff was generated for PR #{pr_num}")
                    if redo_stdout_threshold and len(result.stdout) < redo_stdout_threshold:
                        click.echo(f"🔍 Redoing run because the stdout len ({len(result.stdout)}) is less than {redo_stdout_threshold} characters; stdout: {result.stdout}")
                        calc = run_agent_on_pr_wrapper.call_and_shelve(config_path, pr_num)
                        calc.clear()
                        result = run_agent_on_pr_wrapper(config_path, pr_num)
                        click.echo(f"✅ re-ran agent on PR #{pr_num}")
                    else:
                        write_problem(problem_directory, pr, result.model_dump(exclude_none=False), "no_diff_generated")
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
            result.diff = trim_diff(result.diff)
            pr.agent_stdout = result.stdout
            pr.agent_stderr = result.stderr
            try:
                pr.agent_output = result.agent_output
            except AttributeError as e:
                click.echo(f"🚫 Old data model for #{pr_num}: {e}")
                pr.agent_output = AgentOutput(stdout=result.stdout, stderr=result.stderr)

            # TODO: refactor this part; this is now redundant with the metadiff_judge
            if not pr.diff:
                pr.diff = ""
            if not result.diff:
                result.diff = ""
            comparison = compare_diffs(pr.diff, result.diff)
            click.echo(f"## COMPARISON:\n{yaml.dump(comparison.model_dump())}")
    
            if comparison.identical:
                click.echo(f"🔍 Diff is identical: {comparison.similarity}")
            else:
                click.echo(f"❌ Diff is not identical: {comparison.similarity}")
            pr.predicted_diff = result.diff
            pr.predicted_diff_identical = comparison.identical
            pr.predicted_diff_metadiff = comparison.metadiff
            pr.predicted_diff_similarity = comparison.similarity
            pr.predicted_diff_changes_in_common = comparison.changes_in_common
            pr.changes_unique_to_target = comparison.changes_in_diff1
            pr.changes_unique_to_prediction = comparison.changes_in_diff2

            with open(json_pr_path, "w") as f:
                json.dump(pr.model_dump(exclude_none=False), f, indent=2)

        from ontoeval.judges import metadiff_judge
        judges = [metadiff_judge]
        if use_llm_judge:
            from ontoeval.judges import llm_judge
            judges.append(llm_judge)
        pr.comparisons = {}
        if not pr.diff:
            pr.diff = ""
        if not pr.predicted_diff:
            pr.predicted_diff = ""
        for judge in judges:
            c = judge.compare_diffs(pr.diff, pr.predicted_diff, pr_benchmark=pr)
            pr.comparisons[judge.__name__.split(".")[-1]] = c

        
        # write to markdown folder
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
        
        print(obj["predicted_diff_similarity"])

        for cname, c in obj["comparisons"].items():
            for k, v in c.items():
                obj[f"{cname}_{k}"] = v

        for flatten_col in ["agent_output"]:
            if flatten_col in obj:
                for k, v in obj[flatten_col].items():
                    obj[f"{flatten_col}_{k}"] = v

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
@click.argument('input_file')
@click.option('--output', '-o', required=True, help='Output JSON file for combined results')
def extract_comments(input_file: str, output: str):
    """Extracts comments from linked issues in PRs"""
    all_comments = []
    with open(input_file, 'r') as f:
        bms = json.load(f)["benchmarks"]
        prs = [PRBenchmark(**bm) for bm in bms]
        for pr in prs:
            for issue in pr.linked_issues:
                comments = [GitHubComment(id=str(issue.number), author=issue.author, body=issue.body, created_at=issue.created_at, url=issue.url)]
                for c in issue.comments:
                    comments.append(c)
                all_comments.extend(comments)
    with open(output, 'w') as f:
        json.dump([c.model_dump() for c in all_comments], f, indent=2)

@cli.command()
@click.argument('files', nargs=-1)
@click.option('--use-union/--no-use-union', default=False, show_default=True, help='Whether to use the union of PRs from all experiments')
@click.option('--include-run-id/--no-include-run-id', default=False, show_default=True, help='Whether to include the run_id in the experiment id')
@click.option('--cols-to-average', '-c', default="metadiff_judge_similarity,llm_judge_score_diff,llm_judge_similarity,metadiff_judge_f1_score,metadiff_judge_precision,metadiff_judge_recall", help='Columns to average')
@click.option('--output-dir', '-d', help='Output directory for combined results')
@click.option('--output', '-o', required=True, help='Output JSON file for combined results')
def combine(files: list[str], output_dir: str, output: str, use_union: bool, include_run_id: bool, cols_to_average: str):
    """Combines multiple run outputs into a single consolidated file"""
    
    cols_to_average = cols_to_average.split(",")
    
    results_by_experiment = {}
    prs_by_experiment = {}
    for file in files:
        file = Path(file)
        with open(file, 'r') as f:
            results = json.load(f)
            click.echo(f"🔍 File: {file} total results (unfiltered): {len(results)}")
            results = [r for r in results if all(c in r for c in cols_to_average)]
            experiment_id = str(file.parent.parent.stem)
            conf_file = Path(str(file.parent.parent) + ".yaml")
            if conf_file.exists():
                with open(conf_file, 'r') as f:
                    conf = yaml.safe_load(f)
                    experiment_id = conf.get("name", experiment_id)
            if include_run_id:
                experiment_id = f"{experiment_id}_{file.stem}"
            for result in results:
                # if not result.get("experiment_id"):
                result["experiment_id"] = experiment_id
            results_by_experiment[experiment_id] = results
            prs_by_experiment[experiment_id] = {r["pr_number"] for r in results}
            click.echo(f"🔍 Experiment {experiment_id}: {len(prs_by_experiment[experiment_id])} :: {prs_by_experiment[experiment_id]}")
    
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
    

    all_results = []
    all_results_union = []
    # combine the results
    for experiment_id, results in results_by_experiment.items():
        for r in results:
            all_results_union.append(r)
            if not use_union:
                if r["pr_number"] not in pr_ids_in_common:
                    continue
            all_results.append(r)
    
    # Save combined results
    with open(output, 'w') as f:
        json.dump(all_results, f, indent=2)

    df_maximal = pd.DataFrame(all_results_union)

    df = pd.DataFrame(all_results)
    click.echo(f"🔍 {len(df)} rows in entire_df")
    
    # drop all rows where any of the cols_to_average are None
    df = df.dropna(subset=cols_to_average)
    click.echo(f"🔍 {len(df)} rows after dropping rows with None in {cols_to_average}")
    print(df)
    # get averages grouped by experiment_id
    df_grouped = df.groupby("experiment_id")[cols_to_average]
    df_averaged = df_grouped.mean()
    click.echo(f"🔍 Averaged results: {df_averaged}")

    exp_groups = df.groupby("experiment_id")
    exp_ids = list(exp_groups.groups.keys())

    # Manual t-test implementation
    if len(exp_ids) == 2:
        import numpy as np
        test_results = {}
        for col in cols_to_average:
            exp1_data = exp_groups.get_group(exp_ids[0])[col].dropna()
            exp2_data = exp_groups.get_group(exp_ids[1])[col].dropna()
            
            # Calculate means and standard deviations
            mean1, mean2 = exp1_data.mean(), exp2_data.mean()
            std1, std2 = exp1_data.std(ddof=1), exp2_data.std(ddof=1)
            n1, n2 = len(exp1_data), len(exp2_data)
            
            # Calculate t-statistic (assuming unequal variances - Welch's t-test)
            pooled_se = np.sqrt((std1**2 / n1) + (std2**2 / n2))
            t_stat = (mean1 - mean2) / pooled_se
            
            # Degrees of freedom (Welch-Satterthwaite equation)
            df_welch = ((std1**2 / n1) + (std2**2 / n2))**2 / (
                (std1**2 / n1)**2 / (n1 - 1) + (std2**2 / n2)**2 / (n2 - 1)
            )
            
            test_results[col] = {
                'experiment_1': exp_ids[0],
                'experiment_2': exp_ids[1],
                'mean_1': mean1,
                'mean_2': mean2,
                'difference': mean1 - mean2,
                't_statistic': t_stat,
                'degrees_of_freedom': df_welch,
                'abs_t_stat': abs(t_stat),
                'likely_significant': abs(t_stat) > 2.0  # rough approximation
            }

        # Convert to DataFrame
        results_df = pd.DataFrame(test_results).T
        print("Statistical Test Results:")
        print(results_df)

    if output_dir:
        if isinstance(output_dir, str):
            output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        score_cols = ["metadiff_judge_similarity", "metadiff_judge_f1_score", "llm_judge_score_diff", "llm_judge_similarity"]
        df_maximal["title"] = df_maximal["pr_number"].astype(str) + " -- " + df_maximal["title"] + " PR #" + df_maximal["pr_number"].astype(str)

        subset_df = df_maximal[["pr_number", "title", "experiment_id"] + score_cols]
        # append the pr number onto the title
        # subset_df["title"] = subset_df["pr_number"].astype(str) + " -- " + subset_df["title"] + " PR #" + subset_df["pr_number"].astype(str)
        # sort by pr number
        subset_df = subset_df.sort_values(by="pr_number")
        subset_df.to_csv(output_dir / "scores.csv", index=False)
        df_averaged.to_csv(output_dir / "averaged.csv", index=True)
        # and as html:
        df_averaged.to_html(output_dir / "averaged.html", index=True)
        # pivot such that each column is an experiment_id, each row is a pr title, each cell is the score;
        # include rows for which some experiments have no scores, report as NaN <-- how to do this?
        # pivot_df = subset_df.pivot(index="title", columns="experiment_id", values=score_cols)
        # Reindex to include all titles (missing ones will be NaN)
        # pivot_df = pivot_df.reindex(all_titles)
        # pivot_df.to_csv(output_dir / "scores.csv", index=False)
        for s in score_cols:
            all_titles = df_maximal["title"].unique()
            click.echo(f"🔍 {len(all_titles)} titles in df_maximal from {len(df_maximal)} rows")
            pivot_df = df_maximal.pivot(index="title", columns="experiment_id", values=s)
            # Reindex to include all titles (missing ones will be NaN)
            pivot_df = pivot_df.reindex(all_titles)
            pivot_df.to_csv(output_dir / f"{s}.csv", index=True)
            # get the average of each column, ignoring NaN
            avg_df = pivot_df.mean(axis=0, skipna=True)
            avg_df.to_csv(output_dir / f"{s}_avg.csv", index=False)
            avg_df.to_json(output_dir / f"{s}_avg.json", orient="records", indent=2)
            # get the median of each column, ignoring NaN
            median_df = pivot_df.median(axis=0, skipna=True)
            median_df.to_csv(output_dir / f"{s}_median.csv", index=False)
            median_df.to_json(output_dir / f"{s}_median.json", orient="records", indent=2)
            # get the std of each column, ignoring NaN
            std_df = pivot_df.std(axis=0, skipna=True)
            std_df.to_csv(output_dir / f"{s}_std.csv", index=False)
            std_df.to_json(output_dir / f"{s}_std.json", orient="records", indent=2)
        df.to_csv(output_dir / "summary.csv", index=False)
        df.to_json(output_dir / "combined.json", orient="records", indent=2)
        
    click.echo(f"✅ Combined {len(files)} files into {output}")
    click.echo(f"📊 Total results: {len(all_results)}")


@cli.command()
@click.argument('input_results')
@click.option('--config-path', '-c', required=False, help='Path to the agent config file')
@click.option('--model', '-m', required=False, help='Alternative model, e.g. openai:o3')
@click.option('--suggestions-json', '-J', required=False, help='Path to a JSON file containing suggestions')
@click.option('--output', '-o', required=True, help='Output JSON file for combined results')
def improve(input_results: str, output: str, config_path: str, suggestions_json: str, **kwargs):
    """
    Improves the documentation of the ontology based on the results of the evaluation.
    """
    with open(input_results, 'r') as f:
        results = json.load(f)
    if not config_path:
        # assume experiments/ONT-NUM/results/results-NNN.json ==> experiments/ONT-NUM.yaml
        config_path = Path(str(Path(input_results).parent.parent) + ".yaml")
        if not Path(config_path).exists():
            click.UsageError(f"No config path provided and no config.yaml found in the same directory as the input results: {config_path}")
    config_path = Path(config_path)
    agent = create_agent_wrapper(config_path)
    instructions = agent.all_instructions()
    from ontoeval.utils.self_improver import propose_documentation_changes
    # hacky - we need to be in the same dir as the instructions
    with change_directory(agent.repo_local_path()):
        suggestions = []
        for r in results:
            pr_benchmark = PRBenchmark(**r)
            suggestion = propose_documentation_changes(pr_benchmark, instructions, **kwargs)
            if suggestion:
                suggestions.append({"pr_number": pr_benchmark.pr_number, "suggestion": suggestion})
    with open(suggestions_json, 'w') as f:
        json.dump(suggestions, f, indent=2)
    print(f"🔍 {len(suggestions)} suggestions; now summarizing...")
    new_docs = summarize_suggestions(agent.all_instructions(), [t["suggestion"] for t in suggestions], **kwargs)
    print(f"🔍 New docs:]\n{new_docs}")
    with open(output, 'w') as f:
        json.dump(new_docs, f, indent=2)


@cli.command()
@click.argument('input_results')
@click.option('--max-diff-size-lines', '-m', default=100, help='Maximum diff size (number of lines, including context) to consider; small because we want humans to evaluate small diffs')
@click.option('--config-path', '-c', required=True, help='Path to the agent config file')
@click.option('--exclude-terms', '-e', default="cborg,claude,goose,dragon", help='Terms to exclude from the tasks (typically to exclude PRs made by AI agents)')
@click.option('--output', '-o', required=True, help='Output JSON file for combined results')
@click.option('--limit', '-l', default=None, type=int, help='Limit the number of tasks to create')
def create_eval(input_results: str, config_path: str, max_diff_size_lines: int, output: str, limit: int, exclude_terms: str):
    """
    Creates an evaluation object to be send to Argillo
    """
    exclude_terms_list = exclude_terms.split(",")
    experiment_id = Path(input_results).parent.parent.stem
    input_results = Path(input_results)
    config_path = Path(config_path)
    agent = create_agent_wrapper(config_path)
    with open(input_results, 'r') as f:
        results = json.load(f)

    from ontoeval.utils.argillo_utils import create_task

    tasks = []
    n = 0
    for r in results:
        click.echo(f"🔍 Creating task for {r['pr_number']} // {n} of {len(results)}")
        r["experiment_id"] = experiment_id
        task = create_task(agent, r, max_diff_size_lines, exclude_terms=exclude_terms_list)
        if task:
            tasks.extend(task)
            if limit and n >= limit:
                break
            n += 1

    print(f"🔍 {len(tasks)} tasks to create")
    with open(output, 'w') as f:
        json.dump([t.model_dump() for t in tasks], f, indent=2)
    
@cli.command()
@click.argument('input_path')
@click.option('--api-url', '-u', default="https://chrismungall-ontoeval.hf.space", help='API URL')
@click.option('--api-key', '-k', help='API Key')
@click.option('--dataset-name', '-d', required=True, help='Dataset name')
@click.option('--create', '-C', is_flag=True, help='Create the dataset if it does not exist')
@click.option('--delete', '-D', is_flag=True, help='Delete the dataset if it exists')
@click.option('--min-submitted', '-m', default=5, help='Minimum number of submissions to consider the task complete')
@click.option('--force', is_flag=True, help='Force the dataset to be created even if it already exists')
def submit_eval(input_path: str, api_url: str, api_key: str, dataset_name: str, create: bool, delete: bool, min_submitted: int, force: bool):
    """
    Submits an evaluation to Argilla.

    The input_path is a JSON file containing the evaluation tasks.
    The dataset_name is the name of the dataset to submit to.
    The create flag indicates whether to create the dataset if it does not exist.
    The delete flag indicates whether to delete the dataset if it exists.
    The min_submitted flag indicates the minimum number of submissions to consider the task complete.

    To create the initial JSON:

        ontoeval create-eval -c experiments/uberon-3.yaml results/uberon-3/results.json -o eval.json -l 6

    Note that the 'id' fields here will be preserved in the questions, so you can look these up after

    Then submit to Argilla, creating the dataset if it does not exist:

        ontoeval submit-eval eval.json --dataset-name uberon-test3 -C

    After users have submitted, you can query the dataset and save the results to a JSON file:

        ontoeval query-eval eval.json --dataset-name uberon-test3 -o eval-results.json

    The eval-results.json file will contain the results of the evaluation, including the user_id, the task_id,
    and the responses to the questions.

    You can then use the eval-results.json file to analyze the results of the evaluation.
    """
    if "test" not in input_path and not force:
        click.UsageError("Input path must contain 'test' to submit to test dataset")

    import argilla as rg

    if not api_key:
        import os
        api_key = os.getenv("ARGILLA_API_KEY")
        if not api_key:
            click.UsageError("No API key provided and no ARGILLA_API_KEY environment variable found")

    client = rg.Argilla(
        api_url=api_url,
        api_key=api_key,
    )

    from ontoeval.utils.argillo_utils import get_settings
    settings = get_settings(min_submitted=min_submitted)

    if delete:
        dataset = client.datasets(dataset_name)
        dataset.delete()
        create = True

    if create:
        dataset = rg.Dataset(
            name=dataset_name,
            settings=settings,
        )
        dataset.create()
    else:
        dataset = client.datasets(dataset_name)

    with open(input_path, 'r') as f:
        tasks = [UserEvalTask(**t) for t in json.load(f)]

    # randomize/shuffle the tasks
    import random
    random.shuffle(tasks)
    records = []
    for t in tasks:
        print(t)
        records.append({
            "id": t.id,
            "title": t.title,
            "description": t.description,
        })
    dataset.records.log(records)


@cli.command()
@click.argument('input_path')
@click.option('--dataset-name', '-d', required=True, help='Dataset name')
@click.option('--api-url', '-u', default="https://chrismungall-ontoeval.hf.space", help='API URL')
@click.option('--api-key', '-k', help='API Key')
@click.option('--output', '-o', required=True, help='Output file for combined results')
def query_eval(input_path: str, dataset_name: str, api_url: str, api_key: str, output: str):
    """
    Queries an Argilla dataset and saves the results to a JSON file.

    The input_path is a JSON file containing the evaluation tasks.
    The dataset_name is the name of the dataset to query.
    The api_url is the URL of the Argilla server.
    """
    with open(input_path, 'r') as f:
        tasks = [UserEvalTask(**t) for t in json.load(f)]
    import argilla as rg

    task_ix = {t.id: t for t in tasks}

    if not api_key:
        import os
        api_key = os.getenv("ARGILLA_API_KEY")
        if not api_key:
            click.UsageError("No API key provided and no ARGILLA_API_KEY environment variable found")

    client = rg.Argilla(
        api_url=api_url,
        api_key=api_key,
    )
    dataset = client.datasets(dataset_name)
    records = list(dataset.records)
    print(f"🔍 {len(records)} records in dataset {dataset_name}")
    results = {}
    for r in records:
        task_id = r.id
        task = task_ix[task_id]
        #print(r)
        #result = r.to_dict()
        #for response in r.responses:
        #    print(response.value)
        #result["__responses"] = r.responses.to_dict()
        for k, vals in r.responses.to_dict().items():
            
            print(task_id, k, vals)
            

            for v in vals:
                user_id = v["user_id"]
                response_id = f"{r.id}_{user_id}"
                if response_id not in results:
                    results[response_id] = {
                        "task_id": task_id,
                        "title": r.fields["title"],
                        "user_id": user_id,
                    }
                results[response_id][k] = v["value"]
                for k2 in ["is_ai", "pr_number", "experiment_id"]:
                    results[response_id][k2] = getattr(task, k2)
        
    rows = results.values()
    with open(output, 'w') as f:
        json.dump(results, f, indent=2)


    

def main():
    cli()


if __name__ == '__main__':
    main()