# Judges

OntoEval provides two evaluation methods (judges) for comparing AI-generated changes against ground truth changes:

## Available Judges

- **[Metadiff Judge](metadiff.md)** - Structural diff comparison with precision/recall metrics
- **[LLM Judge](llm.md)** - AI-powered semantic evaluation using GPT-4o

## Overview

Both judges take two diffs as input - typically the AI-generated diff and the ground truth human-generated diff - and produce evaluation metrics. The judges can be used independently or together to provide comprehensive evaluation from different perspectives.

### Common Use Cases

- **Benchmarking**: Evaluate how well AI agents perform on ontology editing tasks
- **Debugging**: Understand where AI agents are making mistakes 
- **Comparison**: Compare different AI agents or configurations
- **Quality Assessment**: Validate that changes meet expected standards

### Judge Selection

Choose your judge based on your evaluation needs:

- Use **Metadiff Judge** for fast, objective structural comparison
- Use **LLM Judge** for nuanced semantic evaluation and detailed feedback
- Use **both** for comprehensive analysis combining structural and semantic perspectives