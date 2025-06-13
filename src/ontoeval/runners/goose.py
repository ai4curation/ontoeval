from pathlib import Path
import subprocess
import time
from ontoeval.runner import AgentConfig

class GooseRunner(AgentConfig):
    """
    Note that running goose involves simulating a home directory in
    the working directory under the ontology repo checkout.

    For AWS bedrock, you may need to copy ~/.aws/
    """
    
    def run(self, input_text: str) -> tuple[str, str]:
        
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
        print(f"🦆 Command took {end_time - start_time} seconds")
        return result