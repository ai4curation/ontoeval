import json
from pathlib import Path
import subprocess
import time
from ontoeval.runner import AgentConfig
from ontoeval.models import AgentOutput

class CodexRunner(AgentConfig):
    """
    Runs openai codex runner
    """

    def instruction_files(self) -> dict[str, str]:
        return {
            k: v for k, v in self.file_contents.items() if k.endswith("AGENTS.md")
        }
    
    def run(self, input_text: str) -> AgentOutput:
        
        env = self.expand_env(self.env)
        # important - ensure that only local config files are used
        # we assue chdir has been called beforehand
        env["HOME"] = "."
        if not Path("./.codex/config.yaml").exists():
            raise ValueError("Codex config.yaml file not found")
        if not Path("./AGENTS.md").exists():
            raise ValueError("AGENTS.md file not found")
        text = self.expand_prompt(input_text)
        command = ["codex", "-a", "auto-edit", "--quiet", text]

        print(f"🤖 Running command: {' '.join(command)}")
        # time the command
        start_time = time.time()
        ao = self._run_process(command, env)
        # parse the jsonl output
        ao.structured_messages = [json.loads(line) for line in ao.stdout.split("\n") if line]
        total_cost_usd = None
        is_error = None
        for message in ao.structured_messages:
            #if "total_cost_usd" in message:
            #    total_cost_usd = message["total_cost_usd"]
            #if "is_error" in message:
            #    is_error = message["is_error"]
            for c in message.get("content", []):
                ao.result_text = c.get("text", "")
        end_time = time.time()
        print(f"🤖 Command took {end_time - start_time} seconds")
        ao.total_cost_usd = total_cost_usd
        ao.success = not is_error
        if not ao.success:
            raise ValueError(f"Claude failed with error: {ao.stderr} // {ao}")
        return ao