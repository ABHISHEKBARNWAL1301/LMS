import os
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not found in environment variables")
    exit(1)

engine = create_engine(DATABASE_URL)


def check_and_fix_courses_table():
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("courses")]

    print(f"Current columns in 'courses' table: {columns}")

    if "is_live_class" not in columns:
        print("Column 'is_live_class' is MISSING in 'courses' table.")
        print("Adding 'is_live_class' column...")

        with engine.connect() as connection:
            with connection.begin():
                # Add the column with a default value of False (as per model definition)
                connection.execute(
                    text(
                        "ALTER TABLE courses ADD COLUMN is_live_class BOOLEAN DEFAULT FALSE"
                    )
                )

        print("Column 'is_live_class' added successfully.")

        # Verify again
        inspector = inspect(engine)
        columns_after = [col["name"] for col in inspector.get_columns("courses")]
        if "is_live_class" in columns_after:
            print("Verification SUCCESS: 'is_live_class' is now present.")
        else:
            print("Verification FAILED: 'is_live_class' is still missing.")

    else:
        print("Column 'is_live_class' ALREADY EXISTS in 'courses' table.")


if __name__ == "__main__":
    check_and_fix_courses_table()
