import json
from pathlib import Path
import subprocess
import time
from ontoeval.runner import AgentConfig
from ontoeval.models import AgentOutput

class GeminiRunner(AgentConfig):
    """
    Runs google gemini runner

    Note: this frequently gets stuck in a loop, see https://github.com/google-gemini/gemini-cli/issues/1531
    """

    def instruction_files(self) -> dict[str, str]:
        return {
            k: v for k, v in self.file_contents.items() if k.endswith("GEMINI.md")
        }
    
    def run(self, input_text: str) -> AgentOutput:
        
        env = self.expand_env(self.env)
        # important - ensure that only local config files are used
        # we assue chdir has been called beforehand
        env["HOME"] = "."
        if not Path("./.codex/config.yaml").exists():
            raise ValueError("Codex config.yaml file not found")
        if not Path("./GEMINI.md").exists():
            raise ValueError("GEMINI.md file not found")
        text = self.expand_prompt(input_text)
        command = ["gemini", "-d", "-m", "gemini-2.5-pro", "-y", "-p", text]

        print(f"🤖 Running command: {' '.join(command)}")
        # time the command
        start_time = time.time()
        ao = self._run_process(command, env)
        # parse the jsonl output
        lines = ao.stdout.split("\n")
        blocks = []
        block = {"text": ""}
        for line in lines:
            if line.startswith("[DEBUG]"):
                
                if block["text"]:
                    # new block
                    blocks.append(block)
                    block = {"text": ""}
                # parse; typical line: [DEBUG] [BfsFileSearch] TEXT
                import re
                m = re.match(r"\[DEBUG\] \[(.*)\] (.*)", line)
                if m:
                    blocks.append({"debug_type": m.group(1), "text": m.group(2)})
            else:
                block["text"] += line + "\n"
        if block["text"]:
            blocks.append(block)
        ao.structured_messages = blocks
        ao.result_text = blocks[-1]["text"] if blocks else ""
        end_time = time.time()
        print(f"🤖 Command took {end_time - start_time} seconds")
        ao.success = True
        return ao