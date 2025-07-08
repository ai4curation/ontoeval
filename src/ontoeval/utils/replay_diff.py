from pathlib import Path
import shutil
import subprocess
from pydantic import BaseModel
from ontoeval.judges.metadiff_judge import ansi_to_html
from ontoeval.models import PRBenchmark
from ontoeval.runner import AgentConfig, create_agent_wrapper
from joblib import Memory
from ontoeval.runner import change_directory

memory = Memory('.memory-replay_diff', verbose=1)

class ReplayResult(BaseModel):
    pr_number: int | None = None
    repo: str | None = None
    base_commit: str
    robot_diff_map: dict[str, str]
    icdiff_diff_map: dict[str, str] | None = None
    icdiff_diff_map_html: dict[str, str] | None = None
    errors: list[str] | None = None


@memory.cache
def replay_diff(repo_local_path: Path, base_commit: str, patch_string: str, files_to_compare: list[str], diff_methods: list[str] | None = None, _version="0.4.0", **kwargs) -> ReplayResult:
    """
    Replay the diff of a PR on a given agent.

    Args:
        agent: The agent to replay the diff on.
        pr: The PR to replay the diff on.
        patch_string: The patch string to apply to the repo.
        files_to_compare: The files to compare.
        diff_methods: The diff methods to use.
        _version: The version of the function (used to control the cache)
        **kwargs: Additional keyword arguments.

    Returns:
        A ReplayResult object containing the robot diff map and any errors.
    """
    print(f"🔄 Replaying diff for {base_commit} in {repo_local_path}")
    with change_directory(repo_local_path):
        # get the parents of base commit using git show --format="%P" -s <base_commit>
        parents = subprocess.run(["git", "show", "--format=%P", "-s", base_commit], capture_output=True, text=True).stdout.strip().split()
        if not parents:
            raise ValueError(f"No parents found for commit {base_commit}")
        
        # do a git reset --hard <base_commit>
        subprocess.run(["git", "reset", "--hard", base_commit])

        # make a temp copy of all the files to compare
        def temp_file_path(file: str) -> Path:
            """May be normalized by robot"""
            return Path(file + ".tmp" + Path(file).suffix)
        
        def temp_origfile_path(file: str) -> Path:
            """Original file, not normalized by robot"""
            return Path(file + ".original" + Path(file).suffix)

        skip_files = []
        for file in files_to_compare:
            if not Path(file).exists():
                print(f"🚫 File {file} does not exist; skipping")
                skip_files.append(file)
                continue
            # make an original copy of the file
            shutil.copy(file, temp_origfile_path(file))
            # use robot to make a temp copy of the file
            try:
                subprocess.run(["robot", "convert", "-i", file, "-o", temp_file_path(file)], check=True)
            except subprocess.CalledProcessError as e:
                print(f"🚫 Robot diff failed for {file}: {e}")
                errors.append(f"Robot diff failed for {file}: {e}")
                skip_files.append(file)
                continue

        # apply the patch; should we make a temp file or use stdin ("-")?
        subprocess.run(["git", "apply", "-"], input=patch_string, text=True)

        # run robot diff on the files to compare
        robot_diff_map = {}
        icdiff_diff_map = {}
        icdiff_diff_map_html = {}
        errors = []
        for file in files_to_compare:
            if file in skip_files:
                continue
            # check if file exists
            if not Path(file).exists():
                print(f"🚫 File {file} does not exist; skipping robot diff")
                continue
            # check if file contents are identical at character level
            if Path(file).read_text() == Path(temp_file_path(file)).read_text():
                print(f"🔍 File {file} is identical at character level; skipping robot diff")
                continue
            diff_output = str(temp_file_path(file)) + ".md"
            # fail hard if the robot diff fails, but report the error
            print(f"🆚 robot diffing {file} with {temp_file_path(file)}")
            try:
                subprocess.run(["robot", "diff", "--labels", "true", "--right", file, "--left", temp_file_path(file), "--output", diff_output], check=True)
            except subprocess.CalledProcessError as e:
                print(f"🚫 Robot diff failed for {file}: {e}")
                errors.append(f"Robot diff failed for {file}: {e}")
                continue
            # read the diff output
            diff_output_text = Path(diff_output).read_text()
            robot_diff_map[file] = diff_output_text

            cmd = ["icdiff", str(temp_origfile_path(file)), str(file), "-E", "@@"]
            print(f"🆚 icdiffing {file} with {temp_origfile_path(file)}")
            try:
                output = subprocess.run(cmd, check=False, capture_output=True, text=True)
                icdiff_diff_map[file] = output.stdout
                print(output.stdout)
                icdiff_diff_map_html[file] = ansi_to_html(output.stdout)
            except subprocess.CalledProcessError as e:
                print(f"🚫 icdiff failed for {file}: {e}")
                errors.append(f"icdiff failed for {file}: {e}")
                continue

    return ReplayResult(
        base_commit=base_commit,
        robot_diff_map=robot_diff_map,
        icdiff_diff_map=icdiff_diff_map,
        icdiff_diff_map_html=icdiff_diff_map_html,
        errors=errors,
        )
            
        
