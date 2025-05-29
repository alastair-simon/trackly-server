This is an api for finding tracklists

## Running the server (without Docker)

1. Create and activate a virtual environment (optional but recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate  # on macOS/Linux
```

2. Install dependencies:

```bash
pip3 install -r requirements.txt
```

3. Start the API with Uvicorn:

```bash
python main.py
```

The server will start on `http://127.0.0.1:4242` by default.
