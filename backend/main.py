import os
import sys
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

load_dotenv()  # Load .env before anything else reads os.getenv()

from database import engine  # noqa: E402
from routers import (  # noqa: E402
    auth,
    courses,
    users,
    lessons,
    blog,
    gallery,
    webhooks,
    payment,
    contact,
    coupons,
    faqs,
    overviews,
    ratings,
    instructors,
    packages,
)

app = FastAPI(title="EvolveU API", description="Learning Management System API")


def _wait_for_db(max_attempts: int = 30, delay: float = 2.0):
    """Retry DB connection until Postgres is ready (handles cold-start race on Railway)."""
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[startup] DB ready after {attempt} attempt(s).")
            return
        except Exception as exc:
            print(f"[startup] DB not ready (attempt {attempt}/{max_attempts}): {exc}")
            if attempt == max_attempts:
                print("[startup] DB never became ready — exiting.")
                sys.exit(1)
            time.sleep(delay)


def _run_migrations():
    """Run migrations.sql on every startup — all statements are idempotent."""
    migrations_path = os.path.join(os.path.dirname(__file__), "migrations.sql")
    with open(migrations_path) as f:
        sql = f.read()
    with engine.begin() as conn:
        conn.execute(text(sql))
    print("[startup] Migrations applied.")


@app.on_event("startup")
def on_startup():
    _wait_for_db()
    # _run_migrations()



# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://evolveu.in", "https://www.evolveu.in", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Create uploads directory if it doesn't exist
if not os.path.exists("uploads"):
    os.makedirs("uploads")

# Include routers
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(users.router)
app.include_router(lessons.router)
app.include_router(blog.router)
app.include_router(gallery.router)
app.include_router(webhooks.router)
app.include_router(payment.router)
app.include_router(contact.router)
app.include_router(coupons.router)
app.include_router(faqs.router)
app.include_router(overviews.router)
app.include_router(ratings.router)
app.include_router(instructors.router)
app.include_router(packages.router)

# Static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
def read_root():
    return {"message": "Welcome to the EvolveU API"}
