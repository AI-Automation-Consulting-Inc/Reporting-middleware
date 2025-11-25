# Run intent parsing using the local heuristic parser
# Usage: .\scripts\run_intent_local.ps1 -Question "your question here"
param(
    [string]$Question = "Revenue from Hindustan Aeronautics for Landing Gear in the last 12 months"
)

# Activate venv in this session (Process-scoped execution policy may be required)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process | Out-Null
. .\.venv\Scripts\Activate.ps1

python .\run_intent.py --local --question "$Question"
