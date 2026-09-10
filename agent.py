import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

import tools

load_dotenv()

MODEL = "gemini-3.5-flash-lite"
MAX_STEPS = 8

SYSTEM_PROMPT = """You answer questions about a hotel database.

Rules:
- Always call get_database_schema first if you do not know the schema.
- Never invent table or column names. Only use what the schema returns.
- Answer only from rows returned by execute_sql. Never guess a number.
- Only SELECT queries are allowed.
- If a query fails, read the error and try a corrected query.
- Keep the final answer short and state the numbers you found.
"""

SCHEMA_TOOL = types.FunctionDeclaration(
    name="get_database_schema",
    description="Return all tables, columns, types and foreign keys.",
    parameters=types.Schema(type="OBJECT", properties={}),
)

SQL_TOOL = types.FunctionDeclaration(
    name="execute_sql",
    description="Run a read-only SELECT query and return the rows.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "sql": types.Schema(type="STRING", description="A single SELECT query."),
        },
        required=["sql"],
    ),
)

TOOL_CONFIG = types.Tool(function_declarations=[SCHEMA_TOOL, SQL_TOOL])


def run_tool(name, args):
    if name == "get_database_schema":
        return tools.get_database_schema()
    if name == "execute_sql":
        return tools.execute_sql(args.get("sql", ""))
    return f"ERROR: unknown tool {name}"


def retry_delay(error, default):
    """Pull the server's suggested retry delay out of a 429, if present."""
    try:
        details = error.details["error"]["details"]
    except (AttributeError, KeyError, TypeError):
        return default
    for item in details:
        if item.get("@type", "").endswith("RetryInfo"):
            raw = str(item.get("retryDelay", "")).rstrip("s")
            try:
                return int(float(raw)) + 1
            except ValueError:
                return default
    return default


def call_model(client, contents, config, tries=5):
    """Call the model, retrying on 503 (overload) and 429 (rate limit)."""
    for attempt in range(tries):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
        except genai.errors.ServerError:
            if attempt == tries - 1:
                raise
            wait = 2 ** attempt
            print(f"  503, retrying in {wait}s")
            time.sleep(wait)
        except genai.errors.ClientError as e:
            if e.code != 429 or attempt == tries - 1:
                raise
            wait = retry_delay(e, 2 ** attempt)
            print(f"  429 rate limit, waiting {wait}s")
            time.sleep(wait)


def ask(question, client=None, verbose=True):
    """Ask one question. Returns a dict with the answer and run stats."""
    if client is None:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[TOOL_CONFIG],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    contents = [types.Content(role="user", parts=[types.Part(text=question)])]

    requests = 0
    sql_run = []
    start = time.time()

    for _ in range(MAX_STEPS):
        response = call_model(client, contents, config)
        requests += 1

        calls = response.function_calls
        if not calls:
            return {
                "answer": response.text,
                "requests": requests,
                "seconds": round(time.time() - start, 1),
                "sql": sql_run,
                "error": None,
            }

        contents.append(response.candidates[0].content)

        parts = []
        for call in calls:
            args = dict(call.args) if call.args else {}
            if call.name == "execute_sql":
                sql = args.get("sql", "")
                sql_run.append(sql)
                if verbose:
                    print(f"\n  SQL: {sql}")

            result = run_tool(call.name, args)

            if verbose and call.name == "execute_sql":
                print(f"  {result}\n")

            parts.append(
                types.Part.from_function_response(
                    name=call.name, response={"result": result}
                )
            )

        contents.append(types.Content(role="user", parts=parts))

    return {
        "answer": None,
        "requests": requests,
        "seconds": round(time.time() - start, 1),
        "sql": sql_run,
        "error": f"gave up after {MAX_STEPS} steps",
    }


if __name__ == "__main__":
    out = ask("How many rooms are currently under maintenance?")
    print(out["answer"])
    print(f"[{out['requests']} requests, {out['seconds']}s]")
