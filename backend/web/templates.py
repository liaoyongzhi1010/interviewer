"""模板渲染辅助函数。"""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).resolve().parents[2]

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "frontend" / "templates"))


def url_for_compat(request: Request, endpoint: str, **values: Any) -> str:
    if endpoint == "static" and "filename" in values and "path" not in values:
        values["path"] = values.pop("filename")
    return str(request.url_for(endpoint, **values))


def render_template(request: Request, template_name: str, **context: Any):
    context.update(
        {
            "request": request,
            "url_for": lambda endpoint, **values: url_for_compat(request, endpoint, **values),
        }
    )
    return templates.TemplateResponse(template_name, context)
