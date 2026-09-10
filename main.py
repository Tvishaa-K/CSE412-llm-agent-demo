import os

from dotenv import load_dotenv
from google import genai

from agent import MODEL, ask

load_dotenv()


def main():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    print(f"Hotel database agent ({MODEL}). Type 'quit' to exit.\n")

    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit"):
            break

        try:
            out = ask(question, client=client)
        except Exception as e:
            print(f"FAILED: {e}\n")
            continue

        if out["error"]:
            print(f"FAILED: {out['error']}")
        else:
            print(out["answer"])

        print(f"[{out['requests']} requests, {out['seconds']}s]\n")


if __name__ == "__main__":
    main()
