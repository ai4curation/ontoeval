from contextlib import contextmanager
import importlib
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Callable
from ontoeval.github import analyze_pr
from ontoeval.models import AgentOutput, PRBenchmark
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
    description: str | None = Field(None, description="Description of the configuration")
    name: str | None = Field(None, description="Shorthand name of the configuration")
    prompt: str | None = Field(None, description="Prompt for the agent")

    def run(self, input_text: str) -> AgentOutput:
        if not self.run_func:
            raise ValueError("run_func is not set, and run is not implemented")
        return self.run_func(input_text, **self.params)
    
    def _run_process(self, command: list[str], env: dict[str, str] | None = None) -> AgentOutput:        
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
            # check for loops: https://github.com/google-gemini/gemini-cli/issues/1531
            for loop_len in range(1, 4):
                if len(output_lines) >= loop_len*2:
                    if all(line.startswith("I have completed ") for line in output_lines[-loop_len:]):
                        if output_lines[-loop_len:] == output_lines[-loop_len*2:-loop_len]:
                            stderr_lines.append("🚨 Loop detected in output; stopping process")
                            pipe.close()
                            return AgentOutput(stdout="\n".join(output_lines), stderr="\n".join(stderr_lines))
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
        
        return AgentOutput(stdout="\n".join(stdout_lines), stderr="\n".join(stderr_lines))
    
    def instruction_files(self) -> dict[str, str]:
        raise NotImplementedError("instruction_files is not implemented")
    
    def all_instructions(self) -> str:
        """Get all instructions from the instruction files."""
        return "\n\n".join(self.instruction_files().values())
    
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
    agent_output: AgentOutput | None = Field(None, description="Output from the agent")
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

LOCK_FILE = ".ontoeval.lock"
    
@contextmanager
def change_directory(path):
    """Context manager to temporarily change directory."""
    original_dir = os.getcwd()
    lock_file = Path(path) / LOCK_FILE
    print(f"🔒 Obtaining lock for {path}; current_dir={original_dir}")
    if lock_file.exists():
        print(f"🚫 Lock file {lock_file} exists in {path}. If you are SURE no other process is running in this directory, delete the lock file and try again.")
        sys.exit(1)
    # write the current process id to the lock file
    lock_file.write_text(str(os.getpid()))
    try:
        os.chdir(path)
        yield
    finally:
        print(f"🔓 Releasing lock for {path}; current_dir={original_dir}")
        os.chdir(original_dir)
        lock_file.unlink()

def copy_file_contents(agent: AgentConfig):
    """Copy the file contents to the repo."""
    for file, content in agent.file_contents.items():
        # get the relative path to the repo
        file = Path(file)
        # create the directory if it doesn't exist
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)
        print(f"Copied {file}")
        # make executable if it is a script
        if file.is_file() and file.suffix in [".sh", ".py", ".pl"]:
            file.chmod(0o755)



@memory.cache
def run_agent_on_pr_wrapper(config_path: str, pr_number: int) -> Result:
    print(f"🔍 Running agent on PR {pr_number} with config {config_path}")
    agent = create_agent_wrapper(config_path)
    return run_agent_on_pr(agent, pr_number)

def run_agent_on_pr(agent: AgentConfig, pr_number: int, iteration: int | None = None) -> Result:
    """Run an agent on a PR."""
    pr = analyze_pr(agent.repo, pr_number)
    with change_directory(agent.repo_local_path()):

        # get current directory
        current_dir = os.getcwd()
        print(f"🔍 Current directory {current_dir}")
        if not current_dir.endswith(str(agent.repo_local_path())):
            raise ValueError(f"Current directory {current_dir} is not the repo local path {agent.repo_local_path()}")
        # do a git reset --hard <base_commit>
        print(f"🔍 Resetting to base commit {pr.base_commit}")
        subprocess.run(["git", "reset", "--hard", pr.base_commit])
        print(f"🔍 Base commit {pr.base_commit} reset; now doing git show --format=%P -s {pr.base_commit}")
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
            print(f"🔄 Copied {file}")
            # make executable if it is a script
            if file.is_file() and file.suffix in [".sh", ".py", ".pl"]:
                file.chmod(0o755)

        # checkout the state of the repo at the time just before the PR was merged
        subprocess.run(["git", "checkout", parents[0]])
        print(f"🔍 Running agent on PR {pr_number}")
        agent_output = agent.run(pr.input_text) 
        if "Please retry if you think this is a transient or recoverable error" in agent_output.stdout:
            raise ValueError("Transient or recoverable error")
        # capture git diff for work we have done    
        print(f"🔍 Capturing git diff for work we have done")
        diff = subprocess.run(["git", "diff"], capture_output=True, text=True).stdout
        print(f"🔍 Git diff: {len(diff)} characters")
        return Result(stdout=agent_output.stdout, stderr=agent_output.stderr, agent_output=agent_output, diff=diff)
    
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
