import json
from pathlib import Path
import subprocess
import time
from ontoeval.runner import AgentConfig
from ontoeval.models import AgentOutput

class GooseRunner(AgentConfig):
    """
    Note that running goose involves simulating a home directory in
    the working directory under the ontology repo checkout.

    For AWS bedrock, you may need to copy ~/.aws/
    """

    def instruction_files(self) -> dict[str, str]:
        return {
            k: v for k, v in self.file_contents.items() if k.endswith(".goosehints")
        }
    
    def run(self, input_text: str) -> AgentOutput:
        
        env = self.expand_env(self.env)
        # important - ensure that only local config files are used
        # we assue chdir has been called beforehand
        env["HOME"] = "."
        if not Path("./.config/goose/config.yaml").exists():
            raise ValueError("Goose config file not found")
        if not Path("./.goosehints").exists():
            raise ValueError("Goose hints file not found")
        text = self.expand_prompt(input_text)
        command = ["goose", "run", "-t", text]
        print(f"🦆 Running command: {' '.join(command)}")
        # time the command
        start_time = time.time()
        result = self._run_process(command, env)
        end_time = time.time()
        ao = AgentOutput(stdout=result.stdout, stderr=result.stderr)
        print(f"🦆 Command took {end_time - start_time} seconds")
        # look in output text for a file like: logging to ./.local/share/goose/sessions/20250613_120403.jsonl
        session_file = None
        for line in result.stdout.split("\n"):
            if "logging to" in line:
                session_file = line.split("logging to ")[1]
                break
        if session_file:
            session_file = Path(session_file)
            if session_file.exists():
                with open(session_file, "r") as f:
                    ao.structured_messages = [json.loads(line) for line in f]
        if ao.structured_messages:
            for message in ao.structured_messages:
                if "content" in message:
                    for content in message["content"]:
                        if "text" in content:
                            ao.result_text = content["text"]
        if not ao.result_text:
            raise ValueError("No result text found in goose output")
        return ao