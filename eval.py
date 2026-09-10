"""Run a fixed set of questions and log how the free tier holds up.

Each question has an expected answer computed directly in SQL, so the
agent's answer is checked against the database rather than by eye.
"""

import json
import os
import time

from dotenv import load_dotenv
from google import genai

from agent import MODEL, ask
from db import run_query

load_dotenv()

# question, check_sql, what the check returns
QUESTIONS = [
    (
        "How many rooms are currently under maintenance?",
        "SELECT count(*) FROM room WHERE status = 'maintenance'",
    ),
    (
        "How many guests are in the database?",
        "SELECT count(*) FROM guest",
    ),
    (
        "Which room type has the highest base price?",
        "SELECT typename FROM roomtype ORDER BY baseprice DESC LIMIT 1",
    ),
    (
        "How many room reservations are there for each status?",
        "SELECT status, count(*) FROM roomreservation GROUP BY status ORDER BY status",
    ),
    (
        "How many guests have booked both a room and a space?",
        """SELECT count(*) FROM guest g
           WHERE EXISTS (SELECT 1 FROM roomreservation r
                         WHERE r.guestid = g.guestid)
             AND EXISTS (SELECT 1 FROM spacereservation s
                         WHERE s.guestid = g.guestid)""",
    ),
    (
        "What is the average number of guests per room reservation?",
        "SELECT round(avg(numguests), 2) FROM roomreservation",
    ),
    (
        "How many rooms are there of each room type? Use the type name.",
        """SELECT t.typename, count(*) FROM room r
           JOIN roomtype t ON r.roomtypeid = t.roomtypeid
           GROUP BY t.typename ORDER BY t.typename""",
    ),
    (
        "Which guests have never made a room reservation?",
        """SELECT count(*) FROM guest g
           WHERE NOT EXISTS (SELECT 1 FROM roomreservation r
                             WHERE r.guestid = g.guestid)""",
    ),
    (
        "Which upgrade has been ordered the most times by quantity?",
        """SELECT u.upgradename, sum(ru.quantity) AS total
           FROM upgrade u JOIN roomreservationupgrade ru
             ON u.upgradeid = ru.upgradeid
           GROUP BY u.upgradename ORDER BY total DESC LIMIT 1""",
    ),
    (
        "What is the total hourly revenue if every space were booked for one hour?",
        "SELECT sum(hourlyrate) FROM space",
    ),
]


# Free-tier RPM limit is 15 on Flash Lite and one question costs about
# 3 requests, so wait between questions to stay under the per-minute cap.
PACE_SECONDS = 15


def expected(check_sql):
    _, rows = run_query(check_sql)
    return rows


def main():
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    results = []
    total_requests = 0
    started = time.time()

    for i, (question, check_sql) in enumerate(QUESTIONS, 1):
        if i > 1:
            time.sleep(PACE_SECONDS)
        truth = expected(check_sql)
        print(f"\n{'=' * 70}\nQ{i}: {question}")
        print(f"expected: {truth}")

        try:
            out = ask(question, client=client, verbose=False)
        except Exception as e:
            print(f"FAILED: {e}")
            results.append({
                "question": question, "answer": None, "sql": [],
                "requests": 0, "seconds": 0, "error": str(e),
            })
            continue

        total_requests += out["requests"]
        print(f"answer: {out['answer']}")
        print(f"sql: {out['sql']}")
        print(f"[{out['requests']} requests, {out['seconds']}s]")

        results.append({
            "question": question,
            "expected": str(truth),
            "answer": out["answer"],
            "sql": out["sql"],
            "requests": out["requests"],
            "seconds": out["seconds"],
            "error": out["error"],
        })

    elapsed = round(time.time() - started, 1)
    failures = sum(1 for r in results if r.get("error"))

    print(f"\n{'=' * 70}")
    print(f"model: {MODEL}")
    print(f"questions: {len(QUESTIONS)}")
    print(f"hard failures: {failures}")
    print(f"total requests: {total_requests}")
    print(f"avg requests per question: {round(total_requests / len(QUESTIONS), 1)}")
    print(f"total time: {elapsed}s (includes {PACE_SECONDS}s pacing between questions)")
    print("\nCompare each answer to expected by hand and mark correctness.")

    out_path = f"results_{MODEL}.json"
    with open(out_path, "w") as f:
        json.dump({
            "model": MODEL,
            "total_requests": total_requests,
            "seconds": elapsed,
            "results": results,
        }, f, indent=2)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
