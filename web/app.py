"""Веб-приложение МЭТР — приватная система управляющего.

Первый экран (онбординг + мгновенный анализ), настройки AI-ассистентов и
сценарии на их основе («Мэтр отвечает»).

Запуск:
    python -m web.app
    # или: uvicorn web.app:app --reload --port 8000
Затем открыть http://localhost:8000

ВНИМАНИЕ: это приватный backend. API-ключи хранятся на сервере и не должны
попадать в публичную статическую витрину (папка site/).
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.analyzer.models import SEGMENTS
from agents.analyzer.service import analyze
from agents.llm import service as llm
from agents.llm.base import LLMError
from agents.content import service as content
from agents.moderation import service as moderation
from agents.recruiting import service as recruiting
from agents.social import service as social
from agents.crm import service as crm
from agents.trends import service as trends
from agents.programming import service as programming
from db import database
from web import auth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("restopulse.web")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="МЭТР", description="AI-управляющий для премиальных ресторанов")

if not auth.auth_enabled():
    log.warning("ADMIN_PASSWORD не задан — вход в панель открыт. "
                "На сервере обязательно задайте ADMIN_PASSWORD.")

# Пути, доступные без авторизации
_OPEN_PATHS = {"/login", "/logout", "/health", "/favicon.ico"}


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    if path in _OPEN_PATHS or path.startswith("/static"):
        return await call_next(request)
    if not auth.is_authed(request):
        if path.startswith("/api/"):
            return JSONResponse({"error": "Требуется вход"}, status_code=401)
        return RedirectResponse("/login", status_code=302)
    return await call_next(request)


# ── Модели запросов ───────────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    name: str
    address: str = ""
    city: str = "Тюмень"
    segment: str = "restaurant"


class SettingsRequest(BaseModel):
    active_provider: str | None = None
    providers: dict[str, dict] = {}


class TestRequest(BaseModel):
    provider: str


class ReplyRequest(BaseModel):
    review: str
    tone: str = "warm"


class LoginRequest(BaseModel):
    password: str


class ChannelsRequest(BaseModel):
    channels: dict[str, dict] = {}


class ChannelTestRequest(BaseModel):
    network: str
    config: dict = {}


class GenerateRequest(BaseModel):
    network: str = "vk"
    content_line: str = ""
    topic: str = ""
    tone: str = ""
    restaurant: str = "Nuar"


class ModerateRequest(BaseModel):
    text: str
    network: str = "vk"


class CrmImportRequest(BaseModel):
    csv: str


class CrmMessageRequest(BaseModel):
    guest_id: str
    trigger: str = "absence"


class VenueRequest(BaseModel):
    venue: dict = {}


class CampaignRequest(BaseModel):
    concept: dict
    networks: list[str] = ["vk"]
    llm: bool = True
    save: bool = False


class PostRequest(BaseModel):
    id: str | None = None
    network: str = "vk"
    content_line: str = ""
    topic: str = ""
    text: str = ""
    status: str | None = None
    scheduled_at: str = ""


# ── Страницы ──────────────────────────────────────────────────────────
def _page(name: str) -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / name).read_text(encoding="utf-8"))


# ── Аутентификация и здоровье ─────────────────────────────────────────
@app.get("/login", response_class=HTMLResponse)
def login_page() -> HTMLResponse:
    return _page("login.html")


@app.post("/login")
def login(req: LoginRequest) -> JSONResponse:
    if not auth.check_password(req.password):
        return JSONResponse({"error": "Неверный пароль"}, status_code=401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.make_token(), max_age=auth.TTL,
                    httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout() -> RedirectResponse:
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(auth.COOKIE)
    return resp


@app.get("/health")
def health() -> dict:
    if database.db_enabled():
        return {"status": "ok" if database.healthcheck() else "degraded", "storage": "postgres"}
    return {"status": "ok", "storage": "json"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _page("index.html")


@app.get("/settings", response_class=HTMLResponse)
def settings_page() -> HTMLResponse:
    return _page("settings.html")


@app.get("/content", response_class=HTMLResponse)
def content_page() -> HTMLResponse:
    return _page("content.html")


@app.get("/recruiting", response_class=HTMLResponse)
def recruiting_page() -> HTMLResponse:
    return _page("recruiting.html")


@app.get("/social", response_class=HTMLResponse)
def social_page() -> HTMLResponse:
    return _page("social.html")


@app.get("/crm", response_class=HTMLResponse)
def crm_page() -> HTMLResponse:
    return _page("crm.html")


@app.get("/trends", response_class=HTMLResponse)
def trends_page() -> HTMLResponse:
    return _page("trends.html")


@app.get("/programma", response_class=HTMLResponse)
def programma_page() -> HTMLResponse:
    return _page("programma.html")


# ── Анализ ────────────────────────────────────────────────────────────
@app.get("/api/segments")
def segments() -> dict:
    return {"segments": [{"value": k, "label": v} for k, v in SEGMENTS.items()]}


@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest) -> JSONResponse:
    try:
        data = analyze(req.name, req.address, req.city, req.segment)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        log.exception("Ошибка анализа")
        return JSONResponse({"error": "Внутренняя ошибка анализа"}, status_code=500)
    return JSONResponse(data)


# ── Настройки AI-ассистентов ──────────────────────────────────────────
@app.get("/api/settings")
def get_settings() -> JSONResponse:
    """Метаданные провайдеров + текущие значения (секреты замаскированы)."""
    return JSONResponse(llm.ui_settings())


@app.post("/api/settings")
def save_settings(req: SettingsRequest) -> JSONResponse:
    try:
        llm.apply_settings(req.active_provider, req.providers)
    except llm.LLMError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(llm.ui_settings())


@app.post("/api/llm/test")
def test_llm(req: TestRequest) -> JSONResponse:
    """Проверка связи с провайдером на сохранённых ключах."""
    return JSONResponse(llm.test_connection(req.provider))


# ── Сценарий: «Мэтр отвечает» на отзыв ────────────────────────────────
@app.post("/api/maitre/reply")
def maitre_reply(req: ReplyRequest) -> JSONResponse:
    try:
        draft = llm.maitre_reply(req.review, tone=req.tone)
    except llm.LLMError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        log.exception("Ошибка генерации ответа")
        return JSONResponse({"error": f"Ошибка: {exc}"}, status_code=500)
    return JSONResponse({"draft": draft})


# ── Каналы публикации (соцсети) ───────────────────────────────────────
@app.get("/api/channels")
def get_channels() -> JSONResponse:
    return JSONResponse(content.ui_channels())


@app.post("/api/channels")
def save_channels(req: ChannelsRequest) -> JSONResponse:
    content.apply_channels(req.channels)
    return JSONResponse(content.ui_channels())


@app.post("/api/channels/test")
def test_channel(req: ChannelTestRequest) -> JSONResponse:
    """Проверка подключения канала на введённых/сохранённых данных."""
    return JSONResponse(content.test_channel(req.network, req.config))


# ── Контент: генерация, черновики, публикация ─────────────────────────
@app.get("/api/content/meta")
def content_meta() -> dict:
    return content.meta()


@app.get("/api/content/ideas")
def content_ideas(network: str = "vk") -> dict:
    return {"ideas": content.ideas(network)}


@app.post("/api/content/generate")
def content_generate(req: GenerateRequest) -> JSONResponse:
    try:
        text = content.generate(req.network, req.content_line, req.topic, req.restaurant, req.tone)
    except LLMError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        log.exception("Ошибка генерации поста")
        return JSONResponse({"error": f"Ошибка: {exc}"}, status_code=500)
    return JSONResponse({"text": text})


@app.get("/api/content")
def content_list() -> dict:
    return {"posts": content.list_posts()}


@app.post("/api/content")
def content_save(req: PostRequest) -> JSONResponse:
    post = content.save_post(req.model_dump(exclude_none=True))
    return JSONResponse({"post": post.to_dict()})


@app.post("/api/content/moderate")
def content_moderate(req: ModerateRequest) -> JSONResponse:
    return JSONResponse(content.moderate(req.text, req.network))


@app.post("/api/content/{post_id}/publish")
def content_publish(post_id: str) -> JSONResponse:
    try:
        post = content.publish_post(post_id)
    except moderation.ModerationError as exc:
        return JSONResponse({"error": "Публикация заблокирована модерацией",
                             "moderation": exc.result.to_dict()}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if post.error:
        return JSONResponse({"post": post.to_dict(), "error": post.error}, status_code=400)
    return JSONResponse({"post": post.to_dict()})


@app.delete("/api/content/{post_id}")
def content_delete(post_id: str) -> dict:
    return {"ok": content.delete_post(post_id)}


# ── Рекрутинг («Мэтр нанимает») ───────────────────────────────────────
@app.get("/api/recruiting/roles")
def recruiting_roles() -> dict:
    return {"roles": recruiting.default_roles()}


@app.get("/api/recruiting/market")
def recruiting_market(city: str = "Тюмень", roles: str = "") -> JSONResponse:
    role_list = [r.strip() for r in roles.split(",") if r.strip()] if roles else None
    try:
        data = recruiting.market(city, role_list)
    except Exception as exc:
        log.exception("Ошибка анализа рынка труда")
        return JSONResponse({"error": f"Ошибка: {exc}"}, status_code=500)
    return JSONResponse(data)


# ── Соцсети конкурентов («Мэтр наблюдает») ────────────────────────────
@app.get("/api/social/vk")
def social_vk(domain: str) -> JSONResponse:
    try:
        data = social.analyze_vk(domain)
    except Exception as exc:
        log.exception("Ошибка анализа VK")
        return JSONResponse({"error": f"Ошибка: {exc}"}, status_code=500)
    return JSONResponse(data)


# ── VIP CRM («Мэтр помнит») ───────────────────────────────────────────
@app.post("/api/crm/import")
def crm_import(req: CrmImportRequest) -> JSONResponse:
    return JSONResponse(crm.import_csv(req.csv))


@app.get("/api/crm/summary")
def crm_summary() -> dict:
    return crm.summary()


@app.get("/api/crm/guests")
def crm_guests() -> dict:
    return {"guests": crm.list_guests()}


@app.get("/api/crm/touches")
def crm_touches() -> dict:
    return {"touches": crm.due_touches()}


@app.post("/api/crm/message")
def crm_message(req: CrmMessageRequest) -> JSONResponse:
    return JSONResponse(crm.generate_message(req.guest_id, req.trigger))


# ── Тренды («Мэтр в тренде») ──────────────────────────────────────────
@app.get("/api/trends/topics")
def trends_topics() -> dict:
    return {"topics": trends.default_topics()}


@app.get("/api/trends")
def trends_analyze(topics: str = "") -> JSONResponse:
    topic_list = [t.strip() for t in topics.split(",") if t.strip()] if topics else None
    try:
        data = trends.analyze(topic_list)
    except Exception as exc:
        log.exception("Ошибка анализа трендов")
        return JSONResponse({"error": f"Ошибка: {exc}"}, status_code=500)
    return JSONResponse(data)


# ── Программа заведения («Мэтр программирует») ────────────────────────
@app.get("/api/venue")
def get_venue() -> dict:
    return {"venue": programming.get_dna().to_dict()}


@app.post("/api/venue")
def save_venue(req: VenueRequest) -> JSONResponse:
    dna = programming.save_dna(req.venue)
    return JSONResponse({"venue": dna.to_dict()})


@app.get("/api/programma")
def api_programma(month: int = 0, n: int = 5, llm: int = 1, trends_on: int = 0) -> JSONResponse:
    try:
        data = programming.programma(
            month=month or None, n=max(1, min(n, 8)),
            use_llm=bool(llm), with_trends=bool(trends_on))
    except Exception as exc:
        log.exception("Ошибка генерации программы")
        return JSONResponse({"error": f"Ошибка: {exc}"}, status_code=500)
    return JSONResponse(data)


@app.post("/api/programma/campaign")
def api_campaign(req: CampaignRequest) -> JSONResponse:
    """Концепт → серия постов. save=true кладёт их черновиками в очередь контента."""
    try:
        data = programming.campaign(req.concept, networks=req.networks,
                                    use_llm=req.llm, save=req.save)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        log.exception("Ошибка сборки кампании")
        return JSONResponse({"error": f"Ошибка: {exc}"}, status_code=500)
    return JSONResponse(data)


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
