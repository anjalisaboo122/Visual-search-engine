from fastapi import FastAPI

app = FastAPI(title="Visual Search Engine API")


@app.get("/health")
def health_check():
    return {"status": "ok"}
