# Research Engine Guidelines v1

## Data Sources
- arXiv: cs.AI, cs.LG, cs.CL categories — fetch 20 most recent daily
- GitHub: llm, agents, rag topics — track top 20 by stars
- HuggingFace: text-generation models — monitor for new releases

## Relevance Criteria
- Papers with "agent", "memory", "RAG", "local", "quantization" in abstract → high relevance
- Models < 30B parameters or with GGUF quantizations → runs_on_our_hw=1
- Repos with > 1000 stars and Python language → high tracking priority

## Quality Standards
- All papers should be reviewed for applicability within 7 days
- Generate improvement_proposal for any paper with direct Jarvis applicability
- Track model VRAM requirements against available hardware (assume 24GB VRAM)
