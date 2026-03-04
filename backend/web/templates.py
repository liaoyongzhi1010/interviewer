"""模板渲染辅助函数。"""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).resolve().parents[2]

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "frontend" / "templates"))


def render_template(request: Request, template_name: str, **context: Any):
    context.update({"request": request})
    return templates.TemplateResponse(template_name, context)
