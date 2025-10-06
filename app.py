from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup, Comment
from typing import Optional
import re
import html as htmlmod

# 👉 опциональный импорт readability (если что-то пойдёт не так — сервис всё равно работает)
try:
    from readability import Document as ReadabilityDocument
except Exception:
    ReadabilityDocument = None

app = FastAPI(title="HTML→Text API")

# Разрешим CORS на всякий случай (удобно для фронтов и внешних вызовов)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExtractRequest(BaseModel):
    html: str
    url: Optional[str] = None
    use_readability: Optional[bool] = True  # если True и модуль доступен — попытаемся вытащить "основной контент"

class ExtractResponse(BaseModel):
    text: str
    title: Optional[str] = None
    source_url: Optional[str] = None
    length: int

def _normalize_text(text: str) -> str:
    """Чистка пробелов/мусора, удаление cookie-строк и пр."""
    text = htmlmod.unescape(text or "")
    lines_out = []

    for raw in (text.splitlines() if text else []):
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue

        # эвристика: слишком много пунктуации относительно букв/цифр — вероятно мусор (cookie, JS-обрывки и т.п.)
        letters = len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]", line))
        punct = len(re.findall(r"[^A-Za-zА-Яа-яЁё0-9\s]", line))
        if letters == 0 or (letters and punct / (letters + punct) > 0.6):
            continue

        # Явные ключевые слова для cookie/GDPR/баннеров
        if re.match(r"^(cookie|cookies|gdpr|privacy|политика|согласие|персональных данных)\b", line, flags=re.I):
            continue

        lines_out.append(line)

    text = "\n".join(lines_out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text

def _strip_tags_keep_text(html: str) -> str:
    """Удаляем мусорные теги/контейнеры и возвращаем текст с разделителями строк."""
    soup = BeautifulSoup(html or "", "lxml")

    # Явно выкидываем «тяжёлые» или неинформационные элементы
    for sel in [
        "script","style","noscript","svg","canvas","template","iframe",
        "form","input","button","nav","footer","header","aside","menu",
        "figure","picture","video","audio","source"
    ]:
        for t in soup.select(sel):
            t.decompose()

    # частые классы/атрибуты для баннеров, модалок, cookie, рекламы
    for sel in [
        '[role="dialog"]','[aria-hidden="true"]','[hidden]',
        '.cookie','#cookie','#cookies','.gdpr','.banner','.popup','.modal','.advert','.ads',
        '[class*="cookie"]','[id*="cookie"]','[class*="banner"]','[id*="banner"]',
        '[class*="advert"]','[id*="advert"]'
    ]:
        for t in soup.select(sel):
            t.decompose()

    # Удаляем HTML-комментарии
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()

    text = soup.get_text(separator="\n", strip=True)
    return _normalize_text(text)

@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    raw = req.html or ""
    title = None

    # Используем readability только если: пользователь не отключил + модуль доступен
    use_readability = bool(req.use_readability and ReadabilityDocument is not None)

    if use_readability:
        try:
            doc = ReadabilityDocument(raw)
            title = (doc.short_title() or "").strip() or None
            main_html = doc.summary(html_partial=True)
            text = _strip_tags_keep_text(main_html)
        except Exception:
            text = _strip_tags_keep_text(raw)
    else:
        text = _strip_tags_keep_text(raw)

    if not title:
        try:
            soup = BeautifulSoup(raw, "lxml")
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
        except Exception:
            pass

    return ExtractResponse(text=text, title=title, source_url=req.url, length=len(text))

@app.get("/")
def health():
    return {"ok": True}

# локальный запуск (не нужен в Docker/на Railway, оставлен на всякий)
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
