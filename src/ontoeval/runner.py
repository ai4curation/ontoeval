from contextlib import contextmanager
import importlib
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Callable
from ontoeval.github import analyze_pr
from ontoeval.models import PRBenchmark
from pydantic import BaseModel, Field

from joblib import Memory

memory = Memory('.memory', verbose=0)


class AgentConfig(BaseModel):
    params: dict | None = Field(None, description="Parameters for the agent")
    file_contents: dict[str, str] | None = Field(None, description="File contents for the agent")
    repo: str = Field(..., description="GitHub repo in format 'owner/name'")
    workdir: str = Field("workdir", description="Working dir where the repo is clone")
    env: dict[str, str] | None = Field(None, description="Environment variables for the agent")
    run_func: Callable | None = Field(None, description="Function to run the agent")
    prompt: str | None = Field(None, description="Prompt for the agent")

    def run(self, input_text: str) -> tuple[str, str]:
        if not self.run_func:
            raise ValueError("run_func is not set, and run is not implemented")
        return self.run_func(input_text, **self.params)
    
    def _run_process(self, command: list[str], env: dict[str, str] | None = None) -> tuple[str, str]:        
        """Run a process and return the output.
        
        Args:
            command: Command to run
            env: Environment variables to use
        
        Returns:
            Tuple of stdout and stderr

        Example:
            >>> agent = create_agent_wrapper("experiments/go-goose-1.yaml")
            >>> agent._run_process(["find", "experiments"])
            experiments
            ...

        Handles failures on long running processes.

            >>> try:
            ...     agent._run_process(["sh", "-c", "sleep 1 && echo 'hello' && exit 1"])
            ... except subprocess.CalledProcessError as e:
            ...     print("🚨 Process failed")
            hello
            🚨 Process failed

        Handles and initial setup.

            >>> try:
            ...     agent._run_process(["NO_SUCH_COMMAND"])
            ... except Exception as e:
            ...     print("🚨 Process failed")
            🚨 Process failed

        """
        if env is None:
            env = self.expand_env(self.env)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1,
            universal_newlines=True
        )
        
        stdout_lines = []
        stderr_lines = []
        
        def stream_output(pipe, output_lines, stream):
            for line in iter(pipe.readline, ''):
                print(line.rstrip(), file=stream)
                output_lines.append(line)
            pipe.close()
        
        # Start threads for both stdout and stderr
        stdout_thread = threading.Thread(
            target=stream_output, 
            args=(process.stdout, stdout_lines, sys.stdout)
        )
        stderr_thread = threading.Thread(
            target=stream_output, 
            args=(process.stderr, stderr_lines, sys.stderr)
        )
        
        stdout_thread.start()
        stderr_thread.start()
        
        # Wait for process and threads to complete
        return_code = process.wait()
        stdout_thread.join()
        stderr_thread.join()
        
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, command)
        
        return stdout_lines, stderr_lines
    
    def expand_env(self, env: dict[str, str]) -> dict[str, str]:
        """Expand environment variables in the agent config."""
        expanded_env = os.environ.copy()
        for key, value in env.items():
            if value.startswith("$"):
                expanded_env[key] = os.getenv(value[1:])
            else:
                expanded_env[key] = value
        return expanded_env
    
    def expand_prompt(self, input_text: str) -> str:
        """Expand environment variables in the prompt."""
        if not self.prompt:
            return input_text
        return self.prompt.format(input_text=input_text)
    
    def repo_local_path(self) -> Path:
        """Get the local path to the repo.

        The repo is cloned into the workdir, and the local path is the name of the repo.

        Args:
            repo: GitHub repo in format 'owner/name'
            workdir: Working dir where the repo is clone

        Returns:
            Path to the local repo
        
        Example:
            >>> task = AgentConfig(repo="geneontology/go-ontology", workdir="/tmp/go-ontology")
            >>> task.repo_local_path()
            PosixPath('/tmp/go-ontology/go-ontology')
        """
        repo_name = self.repo.split('/')[-1]
        return Path(self.workdir) / repo_name

    
class SubProcessAgentConfig(AgentConfig):
    command_template: str = Field(..., description="Command to run the agent")

    def run(self, input_text: str) -> tuple[str, str]:
        command = self.command_template.format(input_text=input_text, **self.params)
        r = subprocess.run(command, capture_output=True, text=True)
        return r.stdout, r.stderr
    
class Result(BaseModel):
    stdout: str = Field(..., description="Output of the agent")
    stderr: str = Field(..., description="Error output of the agent")
    diff: str = Field(..., description="Git diff of the work done")


def create_agent_wrapper(config_path: str | Path) -> AgentConfig:
    """Create a wrapper function for an agent.
    
    Args:
        config_path: Path to the config file
    
    Returns:
        AgentConfig object

    Example:
        >>> agent = create_agent_wrapper("experiments/go-goose-1.yaml")
        >>> type(agent)
        <class 'ontoeval.runners.goose.GooseRunner'>
        >>> agent.env["OPENAI_API_KEY"]
        '$CBORG_CONTEXTUALIZER_API_KEY'
        >>> sorted(list(agent.file_contents.keys()))
        ['.config/goose/config.yaml', '.goosehints']

    """
    if isinstance(config_path, str):
        config_path = Path(config_path)
    with open(config_path, "r") as f:
        import yaml
        config = yaml.safe_load(f)
    config_path_dir = Path(str(config_path).replace(".yaml", "")) / "config"
    # read all files in config_path_dir
    file_contents = {}
    for file in config_path_dir.rglob("*"):
        # skip directories
        if file.is_dir():
            continue
        # get the relative path to the config_path_dir
        relative_path = file.relative_to(config_path_dir)
        file_contents[str(relative_path)] = file.read_text()
    typ = config["type"]
    # this will be a class like ontoeval.runners.goose.GooseRunner
    # we need to import the class and create an instance of it
    module_name, class_name = typ.rsplit(".", 1)
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls(file_contents=file_contents, **config)


def get_parent_commit(base_commit: str) -> str:
    """Get the parent commit of a PR.
    
    Args:
        base_commit: Base commit of the PR

    Returns:
        Parent commit of the base commit

    Example:
    
        >>> os.chdir("workdir/go-ontology")
        >>> get_parent_commit("9bcc2bdf80d2d30d9ebac95829b14f5e2856e960")
        '2b3f16a6a103fb520837bc33a970e8124e86ad95'

    """
    parents = subprocess.run(["git", "show", "--format=%P", "-s", base_commit], capture_output=True, text=True).stdout.strip().split()
    if not parents:
        raise ValueError(f"No parent commit found for {base_commit} (maybe try a git pull?)")
    return parents[-1]
    
@contextmanager
def change_directory(path):
    """Context manager to temporarily change directory."""
    original_dir = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(original_dir)

@memory.cache
def run_agent_on_pr_wrapper(config_path: str, pr_number: int) -> Result:
    agent = create_agent_wrapper(config_path)
    return run_agent_on_pr(agent, pr_number)

def run_agent_on_pr(agent: AgentConfig, pr_number: int, iteration: int | None = None) -> Result:
    """Run an agent on a PR."""
    pr = analyze_pr(agent.repo, pr_number)
    with change_directory(agent.repo_local_path()):

        # get current directory
        current_dir = os.getcwd()
        if not current_dir.endswith(str(agent.repo_local_path())):
            raise ValueError(f"Current directory {current_dir} is not the repo local path {agent.repo_local_path()}")
        # do a git reset --hard <base_commit>
        subprocess.run(["git", "reset", "--hard", pr.base_commit])
        # get the parents of base commit using git show --format="%P" -s <base_commit>
        parents = subprocess.run(["git", "show", "--format=%P", "-s", pr.base_commit], capture_output=True, text=True).stdout.strip().split()
        if not parents:
            raise ValueError(f"No parent commit found for {pr.base_commit} (maybe try a git pull?)")
        
        # copy the files from config/ to the repo
        for file, content in agent.file_contents.items():
            # get the relative path to the repo
            file = Path(file)
            # create the directory if it doesn't exist
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)
            print(f"Copied {file}")

        # checkout the state of the repo at the time just before the PR was merged
        subprocess.run(["git", "checkout", parents[0]])
        stdout, stderr = agent.run(pr.input_text)
        if "Please retry if you think this is a transient or recoverable error" in stdout:
            raise ValueError("Transient or recoverable error")
        # capture git diff for work we have done    
        diff = subprocess.run(["git", "diff"], capture_output=True, text=True).stdout
        return Result(stdout="\n".join(stdout), stderr="\n".join(stderr), diff=diff)
    
# DEPRECATED
def clear_cache_for_pr(config_path: str, pr_number: int):
    """Clear the cache for a specific set of arguments."""
    from joblib._store_backends import FileSystemStoreBackend

    # Access the store backend
    store = memory.store_backend

    # You can inspect what's cached
    cached_items = store.get_items()

    # Clear items matching certain criteria
    for item in cached_items:
        print(item)
        # item contains metadata about cached function calls
        # You can inspect and selectively delete
        pass
    raise ValueError("Cache cleared")
