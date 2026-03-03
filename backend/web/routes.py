"""页面路由（服务端模板渲染）。"""

import threading
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from backend.api.deps import get_current_user_optional, is_valid_uuid
from backend.clients.digitalhub_client import ping_dh
from backend.clients.minio_client import download_resume_data, get_resume_pdf_url
from backend.common.logger import get_logger
from backend.services.interview_service import RoomService, RoundService, SessionService
from backend.services.resume_service import ResumeService
from backend.web.templates import render_template

logger = get_logger(__name__)

router = APIRouter(tags=["Pages"])


def _redirect_to_index(request: Request) -> RedirectResponse:
    return RedirectResponse(url=str(request.url_for("room.index")), status_code=302)


def _require_page_user(request: Request) -> str | None:
    return get_current_user_optional(request)


def _calculate_system_stats(rooms: list[Any]) -> dict[str, int]:
    total_sessions = 0
    total_rounds = 0
    total_questions = 0

    for room in rooms:
        sessions = SessionService.get_sessions_by_room(room.id)
        total_sessions += len(sessions)

        for session in sessions:
            rounds = RoundService.get_rounds_by_session(session.id)
            total_rounds += len(rounds)
            for round_obj in rounds:
                total_questions += round_obj.questions_count

    return {
        "total_rooms": len(rooms),
        "total_sessions": total_sessions,
        "total_rounds": total_rounds,
        "total_questions": total_questions,
    }


def _ping_digital_human_async() -> None:
    def _async_ping() -> None:
        try:
            ping_dh()
            logger.info("Digital human ping successful (async)")
        except Exception as exc:
            logger.warning("Failed to ping digital human (async): %s", exc)

    thread = threading.Thread(target=_async_ping, daemon=True)
    thread.start()


def _alert_back_html(message: str) -> HTMLResponse:
    html = f"""
    <html>
    <head>
        <meta charset=\"UTF-8\">
        <script>
            alert('{message}');
            window.history.back();
        </script>
    </head>
    <body></body>
    </html>
    """
    return HTMLResponse(content=html, status_code=400)


@router.get("/", name="room.index")
def index(request: Request):
    current_user = get_current_user_optional(request)
    if not current_user:
        return render_template(request, "landing.html")

    rooms = RoomService.get_rooms_by_owner(current_user)
    rooms_dict = [RoomService.to_dict(room) for room in rooms]

    resumes = ResumeService.get_resumes_by_owner(current_user)
    resumes_dict = [ResumeService.to_dict(resume) for resume in resumes[:2]]

    stats = _calculate_system_stats(rooms)

    return render_template(
        request,
        "index.html",
        rooms=rooms_dict,
        resumes=resumes_dict,
        stats=stats,
        current_user=current_user,
    )


@router.get("/rooms", name="room.rooms_list")
def rooms_list(request: Request):
    current_user = _require_page_user(request)
    if not current_user:
        return _redirect_to_index(request)

    rooms = RoomService.get_rooms_by_owner(current_user)
    rooms_dict = [RoomService.to_dict(room) for room in rooms]
    return render_template(request, "rooms.html", rooms=rooms_dict)


@router.get("/resumes", name="room.resumes_list")
def resumes_list(request: Request):
    current_user = _require_page_user(request)
    if not current_user:
        return _redirect_to_index(request)

    resumes = ResumeService.get_resumes_by_owner(current_user)
    resumes_dict = [ResumeService.to_dict(resume) for resume in resumes]
    stats = ResumeService.get_resume_stats(current_user)

    return render_template(request, "resumes.html", resumes=resumes_dict, stats=stats)


@router.get("/resumes/{resume_id}", name="room.resume_detail")
def resume_detail(request: Request, resume_id: str):
    current_user = _require_page_user(request)
    if not current_user:
        return _redirect_to_index(request)

    if not is_valid_uuid(resume_id):
        return PlainTextResponse("简历不存在", status_code=404)

    resume = ResumeService.get_resume(resume_id)
    if not resume:
        return PlainTextResponse("简历不存在", status_code=404)

    if resume.owner_address != current_user:
        return PlainTextResponse("无权访问此简历", status_code=403)

    resume_data = None
    if resume.parse_status == "parsed":
        resume_data = download_resume_data(resume_id)
    pdf_url = get_resume_pdf_url(resume_id, expires_hours=24)

    return render_template(
        request,
        "resume_detail.html",
        resume=ResumeService.to_dict(resume),
        resume_data=resume_data,
        pdf_url=pdf_url,
    )


@router.get("/mistakes", name="room.mistakes_list")
def mistakes_list(request: Request):
    current_user = _require_page_user(request)
    if not current_user:
        return _redirect_to_index(request)
    return render_template(request, "mistakes.html")


@router.get("/room/{room_id}", name="room.room_detail")
def room_detail(request: Request, room_id: str):
    current_user = _require_page_user(request)
    if not current_user:
        return _redirect_to_index(request)

    if not is_valid_uuid(room_id):
        return PlainTextResponse("面试间不存在", status_code=404)

    room = RoomService.get_room(room_id)
    if not room:
        return PlainTextResponse("面试间不存在", status_code=404)

    if room.owner_address != current_user:
        return _redirect_to_index(request)

    _ping_digital_human_async()

    sessions = SessionService.get_sessions_by_room(room_id)
    sessions_dict = [SessionService.to_dict(session) for session in sessions]

    return render_template(
        request,
        "room.html",
        room=RoomService.to_dict(room),
        sessions=sessions_dict,
    )


@router.get("/create_session/{room_id}", name="session.create_session")
def create_session(request: Request, room_id: str):
    current_user = _require_page_user(request)
    if not current_user:
        return _redirect_to_index(request)

    if not is_valid_uuid(room_id):
        return PlainTextResponse("面试间不存在", status_code=404)

    room = RoomService.get_room(room_id)
    if not room:
        return PlainTextResponse("面试间不存在", status_code=404)

    if room.owner_address != current_user:
        return _redirect_to_index(request)

    if not room.resume_id:
        return _alert_back_html("请先为面试间关联简历后再创建面试会话！")

    resume = ResumeService.get_resume(room.resume_id)
    if not resume:
        return _alert_back_html("关联简历不存在，请重新选择简历！")

    if resume.parse_status in {"pending", "parsing"}:
        return _alert_back_html("简历正在解析中，请稍后再创建会话。")

    if resume.parse_status == "failed":
        return _alert_back_html("简历解析失败，请到简历详情页查看失败原因后重试。")

    resume_data = download_resume_data(room.resume_id)
    if not resume_data:
        return _alert_back_html("简历解析结果尚未就绪，请稍后重试。")

    session = SessionService.create_session(room_id)
    if not session:
        return PlainTextResponse("面试间不存在", status_code=404)

    return RedirectResponse(
        url=str(request.url_for("session.session_detail", session_id=session.id)),
        status_code=302,
    )


@router.get("/session/{session_id}", name="session.session_detail")
def session_detail(request: Request, session_id: str):
    current_user = _require_page_user(request)
    if not current_user:
        return _redirect_to_index(request)

    if not is_valid_uuid(session_id):
        return PlainTextResponse("面试会话不存在", status_code=404)

    session = SessionService.get_session(session_id)
    if not session:
        return PlainTextResponse("面试会话不存在", status_code=404)

    if session.room.owner_address != current_user:
        return _redirect_to_index(request)

    room = session.room
    resume_data = None
    if room.resume_id:
        resume = ResumeService.get_resume(room.resume_id)
        if resume and resume.parse_status == "parsed":
            resume_data = download_resume_data(room.resume_id)

    has_custom_jd = bool(room.jd_id)

    return render_template(
        request,
        "session.html",
        session=SessionService.to_dict(session),
        rounds=[],
        resume=resume_data,
        has_custom_jd=has_custom_jd,
        dh_message=None,
        dh_connect_url=None,
    )


@router.get("/pricing", name="room.pricing")
def pricing(request: Request):
    return render_template(request, "pricing.html")


@router.get("/docs", name="room.docs")
def docs_page(request: Request):
    return render_template(request, "docs.html")


@router.get("/about", name="room.about")
def about(request: Request):
    return render_template(request, "about.html")
