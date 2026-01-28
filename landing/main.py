import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import FileResponse

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")
IMAGE_PATH = "app/templates/rospatent.jpg"

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")


@app.get("/", response_class=HTMLResponse)
@app.head("/", response_class=HTMLResponse)
async def main(request: Request):
    return templates.TemplateResponse(
        "landing.html", {"request": request, "title": "Главная страница"}
    )


@app.get("/rospatent.jpg")
async def get_rospatent_image():
    """Возвращает изображение свидетельства"""
    if not os.path.exists(IMAGE_PATH):
        return {"error": "Изображение не найдено"}

    return FileResponse(IMAGE_PATH, media_type="image/jpeg", filename="rospatent.jpg")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        # ssl_keyfile="./key.pem",
        # ssl_certfile="./cert.pem",
    )
