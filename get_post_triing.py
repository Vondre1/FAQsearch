from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/hello")
def hello(data: dict):
    name = data.get("name", "гость")
    return {"message": f"Привет, {name}!"}