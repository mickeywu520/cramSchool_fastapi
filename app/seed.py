"""Database seed data initializer.

Usage:
    python -m app.seed

Or call seed_database() from within the app context.
"""

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, init_db
from app.models.about_card import AboutCard
from app.models.announcement import Announcement
from app.models.banner import Banner
from app.models.course import Course
from app.models.honor import Honor
from app.models.teacher import Teacher
from app.models.user import User
from app.utils.security import hash_password

TEACHERS_DATA = [
    {
        "name": "程昊",
        "subject": "數學",
        "title": "資深數學講師",
        "motto": "數學不是背公式，是學邏輯",
        "description": "擁有20年教學經驗，擅長引導學生建立數學思維。",
        "display_order": 1,
    },
    {
        "name": "林宜靜",
        "subject": "英文",
        "title": "全美語教學主任",
        "motto": "讓英文成為孩子探索世界的工具",
        "description": "美國教育碩士，專精兒童全美語教學。",
        "display_order": 2,
    },
    {
        "name": "陳建宏",
        "subject": "理化",
        "title": "自然科學首席講師",
        "motto": "實驗是最好的老師",
        "description": "帶領學生透過動手實驗愛上自然科學。",
        "display_order": 3,
    },
    {
        "name": "張雅文",
        "subject": "國文",
        "title": "國語文教學組長",
        "motto": "閱讀，是通往世界的窗",
        "description": "擅長用故事引導孩子愛上閱讀與寫作。",
        "display_order": 4,
    },
]

COURSES_DATA = [
    {
        "name": "資優數學",
        "category": "elementary",
        "subject": "數學",
        "description": "培養邏輯思考與解題能力，奠定數學基礎",
        "schedule": "每週三 18:30-20:30",
        "price": 4500,
        "max_students": 20,
        "is_early_bird": True,
        "early_bird_discount": "5/31前報名享85折優惠",
        "display_order": 1,
    },
    {
        "name": "全美語",
        "category": "elementary",
        "subject": "英文",
        "description": "全美語沉浸式教學，培養英語溝通能力",
        "schedule": "每週一、四 18:30-20:00",
        "price": 6000,
        "max_students": 15,
        "is_early_bird": True,
        "early_bird_discount": "5/31前報名享9折優惠",
        "display_order": 2,
    },
    {
        "name": "自然實驗",
        "category": "elementary",
        "subject": "理化",
        "description": "動手做實驗，啟發科學探索精神",
        "schedule": "每週二 18:30-20:30",
        "price": 5000,
        "max_students": 18,
        "is_early_bird": False,
        "display_order": 3,
    },
    {
        "name": "國中數學菁英班",
        "category": "junior_high",
        "subject": "數學",
        "description": "針對國中生設計的進階數學課程",
        "schedule": "每週六 09:00-12:00",
        "price": 6000,
        "max_students": 20,
        "is_early_bird": True,
        "early_bird_discount": "5/31前報名享85折優惠",
        "display_order": 4,
    },
    {
        "name": "國中英語加強班",
        "category": "junior_high",
        "subject": "英文",
        "description": "強化文法與閱讀理解，提升會考實力",
        "schedule": "每週六 13:30-16:30",
        "price": 5500,
        "max_students": 18,
        "is_early_bird": False,
        "display_order": 5,
    },
]

BANNERS_DATA = [
    {
        "title": "2026 暑期先修班熱烈報名中",
        "image_url": "/banners/banner1.jpg",
        "link_url": "/courses",
        "display_order": 1,
    },
    {
        "title": "全美語夏令營",
        "image_url": "/banners/banner2.jpg",
        "link_url": "/courses?category=summer",
        "display_order": 2,
    },
    {
        "title": "國小資優數學成果展",
        "image_url": "/banners/banner3.jpg",
        "link_url": "/honors",
        "display_order": 3,
    },
]

HONORS_DATA = [
    {"student_name": "王小明", "school": "建國中學", "department": "普通科", "year": 114, "exam_type": "會考"},
    {"student_name": "林小華", "school": "北一女中", "department": "普通科", "year": 114, "exam_type": "會考"},
    {"student_name": "陳小美", "school": "師大附中", "department": "普通科", "year": 114, "exam_type": "會考"},
    {"student_name": "張小恩", "school": "成功高中", "department": "普通科", "year": 114, "exam_type": "會考"},
    {"student_name": "李小偉", "school": "中山女中", "department": "普通科", "year": 114, "exam_type": "會考"},
    {"student_name": "黃小婷", "school": "松山高中", "department": "普通科", "year": 113, "exam_type": "會考"},
    {"student_name": "吳小倫", "school": "大同高中", "department": "普通科", "year": 113, "exam_type": "會考"},
    {"student_name": "劉小德", "school": "板橋高中", "department": "普通科", "year": 113, "exam_type": "會考"},
]

ABOUT_CARDS_DATA = [
    {
        "title": "專業師資",
        "content": "我們的教師團隊擁有豐富的教學經驗與專業背景，用心陪伴每一位學生的成長",
        "icon": "star",
        "display_order": 1,
    },
    {
        "title": "優良環境",
        "content": "提供明亮寬敞的學習空間，配備現代化教學設備，讓學生在舒適的環境中專注學習",
        "icon": "home",
        "display_order": 2,
    },
    {
        "title": "多元課程",
        "content": "從數學、英文到自然科學，提供多元化的課程選擇，滿足不同學生的學習需求",
        "icon": "book",
        "display_order": 3,
    },
    {
        "title": "成果卓越",
        "content": "歷年來培育無數學生考取頂尖高中，升學率屢創佳績",
        "icon": "trophy",
        "display_order": 4,
    },
]

ANNOUNCEMENTS_DATA = [
    {
        "title": "114學年度暑期先修班開始報名",
        "content": "暑期先修班已開放報名，早鳥優惠至5/31截止，歡迎踴躍報名！",
        "priority": "urgent",
        "target_role": "all",
    },
    {
        "title": "全美語課程說明會",
        "content": "將於6/15舉辦全美語課程說明會，歡迎家長踴躍參加",
        "priority": "normal",
        "target_role": "all",
    },
    {
        "title": "期中考試通知",
        "content": "下週將舉行期中考試，請同學們提早準備",
        "priority": "normal",
        "target_role": "student",
    },
]


async def is_empty(db: AsyncSession, model) -> bool:
    result = await db.execute(select(model).limit(1))
    return result.scalar_one_or_none() is None


async def seed_database():
    await init_db()
    async with async_session() as db:
        try:
            if await is_empty(db, User):
                admin = User(
                    email="admin@cramschool.com",
                    password_hash=hash_password("admin123"),
                    role="admin",
                    auth_provider="email",
                    is_active=True,
                )
                db.add(admin)

            if await is_empty(db, Teacher):
                for data in TEACHERS_DATA:
                    db.add(Teacher(**data))

            if await is_empty(db, Course):
                for data in COURSES_DATA:
                    db.add(Course(**data))

            if await is_empty(db, Banner):
                for data in BANNERS_DATA:
                    db.add(Banner(**data))

            if await is_empty(db, Honor):
                for i, data in enumerate(HONORS_DATA):
                    db.add(Honor(**data, display_order=i + 1))

            if await is_empty(db, AboutCard):
                for data in ABOUT_CARDS_DATA:
                    db.add(AboutCard(**data))

            if await is_empty(db, Announcement):
                for data in ANNOUNCEMENTS_DATA:
                    db.add(Announcement(**data, is_published=True, published_at=datetime.now()))

            await db.commit()
            print("Seed data inserted successfully!")
        except Exception as e:
            await db.rollback()
            print(f"Seed failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(seed_database())
