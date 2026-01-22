import uvicorn
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file if it exists
project_root = Path(__file__).parent
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

from app import app

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=4242, reload=True)