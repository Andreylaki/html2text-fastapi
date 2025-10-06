from fastapi import FastAPI
from pydantic import BaseModel
from bs4 import BeautifulSoup, Comment
from readability import Document
from typing import Optional
import re, html as htmlmod

app = FastAPI(title="HTML→Text API")

class ExtractRequest(BaseModel):
    html: str
    url: Optional[str] = None
    use_readability: Optional[bool] = True  # сначала пробуем извлечь “статью”, потом fallback

class ExtractResponse(BaseModel):
    text: str
    title: Optional[str] = None
    source_url: Optional[str] = None
    length: int

def _normalize_text(text: str) -> str:
    text = htmlmod.unescape(text or "")
    # по строкам: чистим пробелы, выбрасываем мусор
    lines = []
    for raw in text.splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if not line:
            continue
        # выкидываем заведомый мусор вроде cookie-строк (много ; и =, мало букв/цифр)
        letters = len(re.findall(r'[A-Za-zА-Яа-яЁё0-9]', line))
        punct = len(re.findall(r'[^A-Za-zА-Яа-яЁё0-9\s]', line))
        if letters == 0 or (letters and punct/(letters+punct) > 0.6):
            continue
        # типичные “cookies / политика” баннеры по началу строки
        if re.match(r'^(cookie|cookies|политика|privacy|gdpr)\b', line, flags=re.I):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text

def _strip_tags_keep_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")

    # Удаляем скрипты/стили/рекаму/диалоги/шаблоны и пр.
    for sel in [
        "script","style","noscript","svg","canvas","template","iframe",
        "form","input","button","nav","footer","header","aside","menu",
        "figure","picture","video","audio","source"
    ]:
        for t in soup.select(sel):
            t.decompose()

    # cookie/баннеры/модалки/реклама — по классам/ролям/атрибутам
    for sel in [
        '[role="dialog"]','[aria-hidden="true"]','[hidden]','.cookie','#cookie','#cookies',
        '.gdpr','.banner','.popup','.modal','.advert','.ads',
        '[class*="cookie"]','[id*="cookie"]','[class*="banner"]','[id*="banner"]',
        '[class*="advert"]','[id*="advert"]'
    ]:
        for t in soup.select(sel):
            t.decompose()

    # Комментарии
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()

    text = soup.get_text(separator="\n", strip=True)
    return _normalize_text(text)

@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    raw = req.html or ""
    title = None
    text = ""

    if req.use_readability:
        try:
            doc = Document(raw)
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
