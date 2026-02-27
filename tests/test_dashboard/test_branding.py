"""Tests for dashboard branding configurability."""

from __future__ import annotations

from agent_gateway import Gateway
from agent_gateway.config import DashboardConfig


class TestDashboardConfigDefaults:
    """DashboardConfig default values."""

    def test_default_subtitle(self) -> None:
        cfg = DashboardConfig()
        assert cfg.subtitle == "AI Control Plane"

    def test_default_icon_url_is_none(self) -> None:
        cfg = DashboardConfig()
        assert cfg.icon_url is None

    def test_default_title(self) -> None:
        cfg = DashboardConfig()
        assert cfg.title == "Agent Gateway"

    def test_default_favicon_url_is_none(self) -> None:
        cfg = DashboardConfig()
        assert cfg.favicon_url is None


class TestDashboardConfigCustom:
    """DashboardConfig with custom values."""

    def test_custom_subtitle(self) -> None:
        cfg = DashboardConfig(subtitle="My Platform")
        assert cfg.subtitle == "My Platform"

    def test_custom_icon_url(self) -> None:
        cfg = DashboardConfig(icon_url="/static/icon.png")
        assert cfg.icon_url == "/static/icon.png"

    def test_custom_favicon_url(self) -> None:
        cfg = DashboardConfig(favicon_url="/static/fav.ico")
        assert cfg.favicon_url == "/static/fav.ico"


class TestUseDashboardOverrides:
    """use_dashboard() correctly populates _pending_dashboard_overrides."""

    def test_subtitle_override(self) -> None:
        gw = Gateway(workspace="./workspace")
        gw.use_dashboard(subtitle="Custom Sub")
        assert gw._pending_dashboard_overrides["subtitle"] == "Custom Sub"

    def test_icon_url_override(self) -> None:
        gw = Gateway(workspace="./workspace")
        gw.use_dashboard(icon_url="/img/icon.png")
        assert gw._pending_dashboard_overrides["icon_url"] == "/img/icon.png"

    def test_favicon_url_override(self) -> None:
        gw = Gateway(workspace="./workspace")
        gw.use_dashboard(favicon_url="/img/fav.ico")
        assert gw._pending_dashboard_overrides["favicon_url"] == "/img/fav.ico"

    def test_none_values_not_stored(self) -> None:
        gw = Gateway(workspace="./workspace")
        gw.use_dashboard()
        assert "subtitle" not in gw._pending_dashboard_overrides
        assert "icon_url" not in gw._pending_dashboard_overrides
        assert "favicon_url" not in gw._pending_dashboard_overrides


class TestTemplateBranding:
    """Template rendering with branding globals."""

    def test_build_templates_default_branding(self) -> None:
        from agent_gateway.dashboard.router import _build_templates

        cfg = DashboardConfig()
        templates = _build_templates(cfg)
        assert templates.env.globals["dashboard_subtitle"] == "AI Control Plane"
        assert templates.env.globals["dashboard_icon_url"] is None

    def test_build_templates_custom_branding(self) -> None:
        from agent_gateway.dashboard.router import _build_templates

        cfg = DashboardConfig(subtitle="My Hub", icon_url="/icons/logo.png")
        templates = _build_templates(cfg)
        assert templates.env.globals["dashboard_subtitle"] == "My Hub"
        assert templates.env.globals["dashboard_icon_url"] == "/icons/logo.png"

    def test_template_renders_custom_subtitle(self) -> None:
        from agent_gateway.dashboard.router import _build_templates

        cfg = DashboardConfig(subtitle="Custom Platform")
        templates = _build_templates(cfg)
        # Render base.html snippet via the Jinja2 env
        tmpl = templates.env.from_string("{{ dashboard_subtitle }}")
        assert tmpl.render() == "Custom Platform"

    def test_template_renders_default_material_icon(self) -> None:
        from agent_gateway.dashboard.router import _build_templates

        cfg = DashboardConfig()
        templates = _build_templates(cfg)
        tmpl = templates.env.from_string(
            "{% if dashboard_icon_url %}"
            '<img src="{{ dashboard_icon_url }}">'
            "{% else %}"
            '<span class="material-symbols-outlined">hub</span>'
            "{% endif %}"
        )
        result = tmpl.render()
        assert "hub" in result
        assert "<img" not in result

    def test_template_renders_custom_icon(self) -> None:
        from agent_gateway.dashboard.router import _build_templates

        cfg = DashboardConfig(icon_url="/static/icon.png")
        templates = _build_templates(cfg)
        tmpl = templates.env.from_string(
            "{% if dashboard_icon_url %}"
            '<img src="{{ dashboard_icon_url }}">'
            "{% else %}"
            '<span class="material-symbols-outlined">hub</span>'
            "{% endif %}"
        )
        result = tmpl.render()
        assert '<img src="/static/icon.png">' in result
        assert "hub" not in result
