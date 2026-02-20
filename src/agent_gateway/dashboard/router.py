"""Dashboard routes — Jinja2 + HTMX server-rendered UI."""

from __future__ import annotations

import importlib.resources
import json
import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, PackageLoader, select_autoescape

from agent_gateway.dashboard.auth import (
    DashboardAuthError,
    DashboardUser,
    make_get_dashboard_user,
    make_login_handler,
)
from agent_gateway.dashboard.models import (
    AgentCard,
    AnalyticsSummary,
    ExecutionDetail,
    ExecutionRow,
    format_cost,
    format_duration,
    relative_time,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from agent_gateway.config import DashboardConfig

logger = logging.getLogger(__name__)

_PAGE_SIZE = 20


def _build_templates(dash_config: DashboardConfig) -> Jinja2Templates:
    env = Environment(
        loader=PackageLoader("agent_gateway.dashboard"),
        autoescape=select_autoescape(["html"]),
    )
    # Global helpers available in all templates
    env.globals["format_cost"] = format_cost
    env.globals["format_duration"] = format_duration
    env.globals["relative_time"] = relative_time
    env.globals["json_dumps"] = json.dumps
    env.globals["dashboard_title"] = dash_config.title
    env.globals["dashboard_logo_url"] = dash_config.logo_url
    env.globals["dashboard_favicon_url"] = dash_config.favicon_url
    env.globals["dashboard_accent"] = dash_config.theme.accent_color
    env.globals["dashboard_accent_dark"] = dash_config.theme.accent_color_dark
    env.globals["dashboard_theme_mode"] = dash_config.theme.mode
    return Jinja2Templates(env=env)


def _static_dir() -> str:
    ref = importlib.resources.files("agent_gateway.dashboard") / "static"
    with importlib.resources.as_file(ref) as p:
        return str(p)


def register_dashboard(app: FastAPI, dash_config: DashboardConfig) -> None:
    """Mount dashboard routes and static files onto the FastAPI app."""
    templates = _build_templates(dash_config)
    get_dashboard_user = make_get_dashboard_user(dash_config.auth)
    login_handler = make_login_handler(dash_config.auth)

    # Static files
    try:
        static_path = _static_dir()
        app.mount(
            "/dashboard/static",
            StaticFiles(directory=static_path),
            name="dashboard-static",
        )
    except Exception:
        logger.warning("Dashboard static files not found; static assets may be missing")

    # --- Public router (no auth) ---
    public = APIRouter(prefix="/dashboard", include_in_schema=False)

    @public.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="dashboard/login.html",
            context={"error": None},
        )

    @public.post("/login", response_class=HTMLResponse)
    async def login_post(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ) -> Any:
        result = await login_handler(request, username=username, password=password)
        if isinstance(result, dict) and "error" in result:
            return templates.TemplateResponse(
                request=request,
                name="dashboard/login.html",
                context={"error": result["error"]},
                status_code=401,
            )
        return result

    @public.post("/logout")
    async def logout(request: Request) -> RedirectResponse:
        request.session.clear()
        return RedirectResponse(url="/dashboard/login", status_code=303)

    # --- Protected router ---
    protected = APIRouter(
        prefix="/dashboard",
        include_in_schema=False,
        dependencies=[Depends(get_dashboard_user)],
    )

    @protected.get("/", response_class=HTMLResponse)
    @protected.get("/agents", response_class=HTMLResponse)
    async def agents_page(
        request: Request,
        current_user: DashboardUser = Depends(get_dashboard_user),
    ) -> HTMLResponse:
        gw = request.app
        ws = gw.workspace
        agents = list(ws.agents.values()) if ws else []
        cards = [AgentCard.from_definition(a) for a in agents]
        workspace_errors = ws.errors if ws else []

        is_htmx = bool(request.headers.get("HX-Request"))
        template = "dashboard/_agent_cards.html" if is_htmx else "dashboard/agents.html"
        return templates.TemplateResponse(
            request=request,
            name=template,
            context={
                "agents": cards,
                "workspace_errors": workspace_errors,
                "current_user": current_user,
                "active_page": "agents",
            },
        )

    @protected.get("/executions", response_class=HTMLResponse)
    async def executions_page(
        request: Request,
        agent_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        current_user: DashboardUser = Depends(get_dashboard_user),
    ) -> HTMLResponse:
        gw = request.app
        repo = gw._execution_repo
        offset = (page - 1) * _PAGE_SIZE

        records = await repo.list_all(
            limit=_PAGE_SIZE,
            offset=offset,
            agent_id=agent_id or None,
            status=status or None,
        )
        total = await repo.count_all(
            agent_id=agent_id or None,
            status=status or None,
        )
        rows = [ExecutionRow.from_record(r) for r in records]

        ws = gw.workspace
        agent_names = {aid: (a.display_name or aid) for aid, a in ws.agents.items()} if ws else {}

        has_running = any(r.is_running for r in rows)
        total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)

        is_htmx = bool(request.headers.get("HX-Request"))
        template = "dashboard/_exec_rows.html" if is_htmx else "dashboard/executions.html"
        return templates.TemplateResponse(
            request=request,
            name=template,
            context={
                "rows": rows,
                "agent_names": agent_names,
                "agent_id_filter": agent_id or "",
                "status_filter": status or "",
                "page": page,
                "total_pages": total_pages,
                "total": total,
                "has_running": has_running,
                "current_user": current_user,
                "active_page": "executions",
            },
        )

    @protected.get("/executions/{execution_id}", response_class=HTMLResponse)
    async def execution_detail(
        request: Request,
        execution_id: str,
        current_user: DashboardUser = Depends(get_dashboard_user),
    ) -> HTMLResponse:
        gw = request.app
        repo = gw._execution_repo
        record = await repo.get_with_steps(execution_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Execution not found")

        ws = gw.workspace
        agent = ws.agents.get(record.agent_id) if ws else None
        agent_name = (agent.display_name or record.agent_id) if agent else record.agent_id

        detail = ExecutionDetail.from_record(record, agent_name)

        is_htmx = bool(request.headers.get("HX-Request"))
        is_running = record.status in ("queued", "running")
        template = (
            "dashboard/_trace_steps.html"
            if (is_htmx and is_running)
            else "dashboard/execution_detail.html"
        )
        return templates.TemplateResponse(
            request=request,
            name=template,
            context={
                "detail": detail,
                "is_running": is_running,
                "current_user": current_user,
                "active_page": "executions",
            },
        )

    @protected.get("/chat", response_class=HTMLResponse)
    async def chat_page(
        request: Request,
        agent_id: str | None = None,
        current_user: DashboardUser = Depends(get_dashboard_user),
    ) -> HTMLResponse:
        gw = request.app
        ws = gw.workspace
        agents = list(ws.agents.values()) if ws else []
        agent_cards = [AgentCard.from_definition(a) for a in agents]
        selected_agent_id = agent_id or (agents[0].id if agents else None)
        return templates.TemplateResponse(
            request=request,
            name="dashboard/chat.html",
            context={
                "agents": agent_cards,
                "selected_agent_id": selected_agent_id,
                "session_id": None,
                "messages": [],
                "current_user": current_user,
                "active_page": "chat",
            },
        )

    @protected.post("/chat/send", response_class=HTMLResponse)
    async def chat_send(
        request: Request,
        agent_id: str = Form(...),
        message: str = Form(...),
        session_id: str = Form(""),
        current_user: DashboardUser = Depends(get_dashboard_user),
    ) -> HTMLResponse:
        from agent_gateway.chat.session import ChatSession
        from agent_gateway.engine.models import ExecutionOptions

        gw = request.app
        ws = gw.workspace
        engine = gw.engine

        agent = ws.agents.get(agent_id) if ws else None
        if agent is None:
            return templates.TemplateResponse(
                request=request,
                name="dashboard/_chat_message.html",
                context={
                    "role": "error",
                    "content": f"Agent '{agent_id}' not found.",
                    "session_id": session_id,
                    "agent_id": agent_id,
                },
            )

        # Get or create session
        store = gw._session_store
        chat_session: ChatSession | None = None
        if session_id and store:
            chat_session = store.get_session(session_id)

        if chat_session is None and store:
            chat_session = store.create_session(agent_id)

        # Build message history
        if chat_session:
            chat_session.append_user_message(message)
            history = chat_session.messages
        else:
            history = None

        # Execute
        try:
            if engine is None or ws is None:
                raise RuntimeError("Engine not ready")
            from agent_gateway.workspace.prompt import assemble_system_prompt

            system_prompt = await assemble_system_prompt(
                agent,
                ws,
                query=message,
                retriever_registry=gw._retriever_registry,
                context_retrieval_config=gw._config.context_retrieval if gw._config else None,
                memory_block="",
            )
            if history:
                msgs = [{"role": "system", "content": system_prompt}] + [
                    m for m in history if m["role"] != "system"
                ]
            else:
                msgs = None

            result = await engine.execute(
                agent=agent,
                message=message,
                workspace=ws,
                options=ExecutionOptions(),
                message_history=msgs,
            )
            reply = result.raw_text or ""
            if chat_session:
                chat_session.append_assistant_message(reply)
        except Exception as exc:
            logger.error("Chat execution error: %s", exc)
            reply = f"Error: {exc}"

        return templates.TemplateResponse(
            request=request,
            name="dashboard/_chat_message.html",
            context={
                "role": "assistant",
                "content": reply,
                "user_message": message,
                "session_id": chat_session.session_id if chat_session else session_id,
                "agent_id": agent_id,
            },
        )

    @protected.get("/analytics", response_class=HTMLResponse)
    async def analytics_page(
        request: Request,
        days: int = 30,
        current_user: DashboardUser = Depends(get_dashboard_user),
    ) -> HTMLResponse:
        gw = request.app
        repo = gw._execution_repo
        persistence_enabled = gw._config.persistence.enabled if gw._config else True

        cost_by_day_data: list[dict[str, Any]] = []
        exec_by_day_data: list[dict[str, Any]] = []
        cost_by_agent_data: list[dict[str, Any]] = []
        total_cost = 0.0
        total_execs = 0
        success_count = 0

        if persistence_enabled:
            cost_by_day_data = await repo.cost_by_day(days=days)
            exec_by_day_data = await repo.executions_by_day(days=days)
            cost_by_agent_data = await repo.cost_by_agent(days=days)

            for row in cost_by_day_data:
                total_cost += float(row.get("total_cost_usd") or 0)
            for row in exec_by_day_data:
                total_execs += int(row.get("count") or 0)
                success_count += int(row.get("success_count") or 0)

        success_rate = (success_count / total_execs * 100) if total_execs > 0 else 0.0

        ws = gw.workspace
        agent_names = {aid: (a.display_name or aid) for aid, a in ws.agents.items()} if ws else {}

        summary = AnalyticsSummary(
            total_cost_usd=total_cost,
            total_executions=total_execs,
            success_rate=success_rate,
            avg_duration_ms=0.0,
            cost_by_day=cost_by_day_data,
            executions_by_day=exec_by_day_data,
            cost_by_agent=cost_by_agent_data,
            days=days,
        )

        is_htmx = bool(request.headers.get("HX-Request"))
        template = "dashboard/_analytics_charts.html" if is_htmx else "dashboard/analytics.html"
        return templates.TemplateResponse(
            request=request,
            name=template,
            context={
                "summary": summary,
                "days": days,
                "persistence_enabled": persistence_enabled,
                "agent_names": agent_names,
                "current_user": current_user,
                "active_page": "analytics",
            },
        )

    # Register exception handler for auth redirects
    @app.exception_handler(DashboardAuthError)
    async def _auth_redirect(request: Request, exc: DashboardAuthError) -> RedirectResponse:
        return RedirectResponse(url=exc.redirect_url, status_code=302)

    app.include_router(public)
    app.include_router(protected)
