-- Run once: safe to re-run (all statements are idempotent)

-- Drop duration_minutes column
ALTER TABLE courses DROP COLUMN IF EXISTS duration_minutes;

-- Change duration column from text to integer (number of days)
ALTER TABLE courses ALTER COLUMN duration TYPE INTEGER USING NULLIF(duration, '')::INTEGER;

-- Create faqs table
CREATE TABLE IF NOT EXISTS faqs (
    id          SERIAL PRIMARY KEY,
    question    VARCHAR NOT NULL,
    answer      TEXT NOT NULL,
    course_id   INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    "order"     INTEGER NOT NULL DEFAULT 0,
    created_at  VARCHAR NOT NULL DEFAULT NOW()::TEXT
);

CREATE INDEX IF NOT EXISTS ix_faqs_course_id ON faqs (course_id);

-- Create course_overviews table
CREATE TABLE IF NOT EXISTS course_overviews (
    id          SERIAL PRIMARY KEY,
    course_id   INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    week_start  INTEGER NOT NULL,
    week_end    INTEGER NOT NULL,
    title       VARCHAR NOT NULL,
    description TEXT,
    "order"     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_course_overviews_course_id ON course_overviews (course_id);

-- Add admin rating fields to courses
ALTER TABLE courses ADD COLUMN IF NOT EXISTS admin_rating FLOAT DEFAULT 4.5;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS admin_learners_count INTEGER DEFAULT 10;

-- Create course_ratings table
CREATE TABLE IF NOT EXISTS course_ratings (
    id          SERIAL PRIMARY KEY,
    course_id   INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating      FLOAT NOT NULL,
    created_at  VARCHAR NOT NULL DEFAULT NOW()::TEXT,
    UNIQUE (course_id, user_id)
);

CREATE INDEX IF NOT EXISTS ix_course_ratings_course_id ON course_ratings (course_id);

-- Add description to blog_posts, make category free text (nullable)
ALTER TABLE blog_posts ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE blog_posts ALTER COLUMN category DROP NOT NULL;

-- Instructor support
ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS assigned_instructor_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- Free/locked lessons
ALTER TABLE lessons ADD COLUMN IF NOT EXISTS is_free BOOLEAN NOT NULL DEFAULT FALSE;

-- Packages
CREATE TABLE IF NOT EXISTS packages (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR NOT NULL,
    tag         VARCHAR,
    price       FLOAT NOT NULL,
    description TEXT,
    features    JSON DEFAULT '[]',
    is_popular  BOOLEAN NOT NULL DEFAULT FALSE,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  VARCHAR NOT NULL DEFAULT NOW()::TEXT
);

CREATE TABLE IF NOT EXISTS package_courses (
    id          SERIAL PRIMARY KEY,
    package_id  INTEGER NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
    course_id   INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE (package_id, course_id)
);

CREATE TABLE IF NOT EXISTS user_packages (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    package_id   INTEGER NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
    purchased_at VARCHAR NOT NULL DEFAULT NOW()::TEXT,
    UNIQUE (user_id, package_id)
);

ALTER TABLE orders ADD COLUMN IF NOT EXISTS package_id INTEGER REFERENCES packages(id) ON DELETE SET NULL;
ALTER TABLE orders ALTER COLUMN course_ids DROP NOT NULL;
