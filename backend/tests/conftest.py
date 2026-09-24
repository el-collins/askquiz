import os

os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql://askquiz:askquiz@localhost:5432/askquiz"
)
os.environ.setdefault("DAILY_REQUEST_CAP", "3")
