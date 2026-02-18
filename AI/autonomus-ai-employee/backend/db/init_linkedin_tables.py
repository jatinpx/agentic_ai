"""
Migration script: Create LinkedIn tables in PostgreSQL with pgvector.
Run once during initial setup:
    python -m db.init_linkedin_tables
"""

from db.linkedin_repo import create_linkedin_tables


def main():
    print("Creating LinkedIn tables...")
    create_linkedin_tables()
    print("Done.")


if __name__ == "__main__":
    main()
