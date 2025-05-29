import uvicorn
from app import app

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=4242, reload=True)