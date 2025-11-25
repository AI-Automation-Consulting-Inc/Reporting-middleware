import json
from pathlib import Path
from nlp.llm_intent_parser import parse_intent_with_llm


def main():
    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    question = "Revenue from Hindustan Aeronautics for Landing Gear in the last 12 months"

    intent = parse_intent_with_llm(question, config)
    print(json.dumps(intent, indent=2))


if __name__ == "__main__":
    main()
