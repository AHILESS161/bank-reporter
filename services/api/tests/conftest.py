import os
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent / ".runtime"
TEST_ROOT.mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'bank-reporter.sqlite3').as_posix()}"
os.environ["DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["MODEL_API_KEY"] = ""
os.environ["MODEL_BASE_URL"] = ""
os.environ["ENVIRONMENT"] = "test"
