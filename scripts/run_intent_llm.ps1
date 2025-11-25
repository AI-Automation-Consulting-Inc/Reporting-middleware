# Run intent parsing using the LLM parser (requires OPENAI_API_KEY in env)
# Usage: .\scripts\run_intent_llm.ps1 -Question "your question here"
param(
    [string]$Question = "Revenue from Hindustan Aeronautics for Landing Gear in the last 12 months"
)

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process | Out-Null
. .\.venv\Scripts\Activate.ps1

python .\run_intent.py --question "$Question"
