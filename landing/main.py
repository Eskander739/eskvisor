import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")


@app.get("/", response_class=HTMLResponse)
async def main(request: Request):
    return templates.TemplateResponse(
        "landing.html", {"request": request, "title": "Главная страница"}
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        ssl_keyfile="./key.pem",
        ssl_certfile="./cert.pem",
    )