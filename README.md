# LLM Agent over a PostgreSQL Database

A reference implementation for the CSE 412 group project: a terminal
chatbot that answers natural-language questions by writing and running
SQL against a PostgreSQL database.

Built by Tvishaa Kandala (UGTA) using free-tier Gemini. It runs against
a hotel booking database, but the code is not specific to that schema —
point it at your own database and it works the same way.

**This is a reference, not a starting template.** Read it, understand
the pattern, then build your own version for your own application.

## How it works

```
your question
  -> agent picks a tool
  -> get_database_schema()  or  execute_sql(...)
  -> PostgreSQL
  -> rows come back
  -> agent answers using only those rows
```

The LLM never touches the database directly. It can only call two
functions, and one of those refuses anything that is not a SELECT.

## The files

| File | What it does |
|---|---|
| `db.py` | Connects to PostgreSQL. Reads settings from `.env`. |
| `tools.py` | The two tools. Works on its own with no LLM. |
| `agent.py` | The Gemini loop: ask, call tool, feed result back, repeat. |
| `main.py` | Terminal chat. Run this. |
| `eval.py` | Runs 10 fixed questions and reports accuracy and quota use. |

## Setup

### 1. Install

```bash
pip install psycopg2-binary google-genai python-dotenv
```

### 2. Make a read-only database user

Do this. The agent will be running SQL that a language model wrote,
against a database you spent weeks populating.

```sql
CREATE USER agent_ro WITH PASSWORD 'pick_something';
GRANT CONNECT ON DATABASE your_db TO agent_ro;
GRANT USAGE ON SCHEMA public TO agent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_ro;
```

Check it worked. The SELECT should return a number, the DELETE should
be refused:

```sql
SELECT count(*) FROM some_table;
DELETE FROM some_table WHERE id = 1;
```

### 3. Get a Gemini API key

Free from [aistudio.google.com](https://aistudio.google.com) under
**API Keys**. No billing setup, no card.

### 4. Configure

```bash
cp .env.example .env
```

Fill in your key and database details. `.env` is gitignored — do not
commit it.

### 5. Test the database side first

```bash
python tools.py
```

You should see your schema, your foreign keys, five sample rows, and a
rejected DELETE. If this works, your database half is correct
regardless of which LLM you use later. Phase 2 asks you to show exactly
this.

### 6. Run it

```bash
python main.py
```

```
> how many rooms are available?

  SQL: SELECT status, COUNT(*) FROM room GROUP BY status;
  status | count
  occupied | 4
  available | 19
  maintenance | 2

There are 19 available rooms.
[3 requests, 2.1s]
```

## Things that will bite you

### Use a Flash Lite model

Free-tier limits are wildly different between models on the same key:

| Model | Per minute | Per day |
|---|---|---|
| Gemini 3.5 Flash | 5 | **20** |
| Gemini 3.5 Flash Lite | 15 | **500** |
| Gemini 3.1 Flash Lite | 15 | **500** |
| Any Pro model | 0 | 0 |

One question costs about 3 requests, because the agent calls the schema
tool, then the SQL tool, then answers. On full Flash that is 7 questions
a day. On Flash Lite it is around 165.

Check your own numbers under **Rate Limit** in AI Studio. They vary by
account.

Also avoid the `-latest` aliases. They move to a new model when Google
ships one, and you do not want that happening the week before demos.

### You must handle 429 and 503

Both will happen. Neither means your code is broken.

**429** is the per-minute cap. You get 15 requests a minute, and a fast
agent burns that in under a minute of steady use. The error includes a
`retryDelay` telling you exactly how long to wait — read it and use it,
do not guess. See `retry_delay()` in `agent.py`.

**503** means Google is busy and free tier got deprioritized. Retry with
backoff.

Without both, roughly one question in ten dies. During a live demo.

### `information_schema` will silently hide your foreign keys

The obvious query for foreign keys is
`information_schema.constraint_column_usage`. Under a read-only user it
returns **nothing** — no error, just an empty result — because that view
only shows constraints on tables you own.

Your agent then gets a schema with no relationships and starts guessing
how to join. Nothing tells you why.

Query `pg_constraint` instead. See `get_database_schema()` in
`tools.py`.

### Ambiguous questions cost double

Asking "which guest has the most reservations" when there are two
reservation tables made the agent try four different interpretations
before answering. 7 requests instead of 3.

## Why bother displaying the SQL

The project spec asks for verification, and here is a concrete reason.

Asked "which guest has the most reservations?", the agent answered:

> Kevin Brown, with 2 reservations.

Valid SQL. Real rows. Misleading answer. In that dataset every guest had
exactly one room reservation and 20 had exactly one space reservation,
so 20 guests were tied at 2. The agent reported an arbitrary tie-break
as a unique winner.

The prose answer hides this completely. The SQL and the source rows make
it obvious in a second. That is why `main.py` prints the query and the
rows before the answer, and why your project should do something
equivalent.

## Checking your agent honestly

`eval.py` runs 10 questions. Each one has a hand-written SQL query that
computes the true answer straight from the database, printed next to
what the agent said.

Do this instead of eyeballing a few questions. A wrong answer that reads
fluently is easy to miss.

Latest run on this database: 10 of 10 correct, 3.3 requests per
question, no failures.

Note `eval.py` waits 15 seconds between questions on purpose. Without
that pause it trips the per-minute limit and the last few questions die.

## Adapting it to your project

1. Point `.env` at your database.
2. Rewrite the questions in `eval.py` for your schema, each with a
   ground-truth SQL query.
3. Adjust `SYSTEM_PROMPT` in `agent.py` if your domain needs
   explaining.

Everything else is schema-independent. `get_database_schema()` reads
whatever tables you have.

Adding a third tool is a good idea and the spec asks for at least three.
`search_metadata()` and `verify_result()` are both reasonable next
steps.

## Questions

Ask in office hours or on the course forum.
