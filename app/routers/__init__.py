"""API routers."""

from app.routers.auth import router as auth_router
from app.routers.student import router as student_router
from app.routers.teacher import router as teacher_router
from app.routers.course import router as course_router
from app.routers.leave import router as leave_router
from app.routers.communication import router as communication_router
from app.routers.honor import router as honor_router
from app.routers.announcement import router as announcement_router
from app.routers.banner import router as banner_router
from app.routers.homepage import router as homepage_router
from app.routers.about_card import router as about_card_router
from app.routers.upload import router as upload_router

routers = [
    auth_router,
    student_router,
    teacher_router,
    course_router,
    leave_router,
    communication_router,
    honor_router,
    announcement_router,
    banner_router,
    homepage_router,
    about_card_router,
    upload_router,
]