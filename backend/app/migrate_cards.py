"""Explicit, atomic conversion of legacy cards using user-supplied answers.

Run `python -m app.migrate_cards` to list IDs, then supply --answers answers.json.
The JSON maps flashcards and study_session_cards IDs to their answer text.
No content is deleted and no answer is inferred from a question.
"""
import argparse
import json

from sqlalchemy import inspect, text

from app.database import engine
from app.schemas import CardInput

CARD_TABLES = ("flashcards", "study_session_cards")


def legacy_cards(connection):
    inspector = inspect(connection)
    return {
        table: list(connection.execute(text(f"""
            SELECT id, front FROM {table}
            WHERE card_type IS NOT 'two_sided' OR back IS NULL
               OR length(trim(back)) NOT BETWEEN 1 AND 10000
            ORDER BY id
        """)).mappings()) if inspector.has_table(table) else []
        for table in CARD_TABLES
    }


def repair_cards(target, answers):
    if not isinstance(answers, dict) or set(answers) - set(CARD_TABLES):
        raise ValueError("Answers must map flashcards and/or study_session_cards IDs to answer text.")
    with target.connect() as connection:
        connection.execute(text("BEGIN IMMEDIATE"))
        try:
            legacy = legacy_cards(connection)
            updates = []
            for table, rows in legacy.items():
                supplied = answers.get(table, {})
                required = {str(row["id"]) for row in rows}
                if not isinstance(supplied, dict) or set(supplied) != required:
                    raise ValueError(f"Supply exactly these {table} IDs: {sorted(required)}")
                for row in rows:
                    validated = CardInput(front=row["front"], back=supplied[str(row["id"])])
                    updates.append((table, row["id"], validated.back))
            for table, identity, back in updates:
                connection.execute(text(f"UPDATE {table} SET card_type = 'two_sided', back = :back WHERE id = :id"),
                                   {"id": identity, "back": back})
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return len(updates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", help="JSON file containing explicit answers for every reported ID")
    args = parser.parse_args()
    if args.answers:
        with open(args.answers, encoding="utf-8") as source:
            try:
                count = repair_cards(engine, json.load(source))
            except ValueError as exc:
                parser.error(str(exc))
        print(f"Converted {count} legacy cards. Restart the Flashcards API to install its database guards.")
    else:
        with engine.connect() as connection:
            print(json.dumps({table: [row["id"] for row in rows]
                              for table, rows in legacy_cards(connection).items()}, indent=2))


if __name__ == "__main__":
    main()
