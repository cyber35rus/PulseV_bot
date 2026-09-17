from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Integer, String, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

engine = create_async_engine("sqlite+aiosqlite:///bot.db")
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=True)
    first_name: Mapped[str] = mapped_column(String, nullable=True)
    subject: Mapped[str] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="free")
    daily_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reset: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String)
    topic: Mapped[str] = mapped_column(String, default="Общее")
    text: Mapped[str] = mapped_column(String)
    option_a: Mapped[str] = mapped_column(String)
    option_b: Mapped[str] = mapped_column(String)
    option_c: Mapped[str] = mapped_column(String)
    option_d: Mapped[str] = mapped_column(String)
    correct: Mapped[str] = mapped_column(String)
    explanation: Mapped[str] = mapped_column(String, default="")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_questions()


async def seed_questions():
    async with SessionLocal() as session:
        result = await session.execute(select(Question).limit(1))
        if result.scalar_one_or_none():
            return
        sample = [
            Question(
                subject="math", topic="Квадратные уравнения",
                text="Решите уравнение: x² − 5x + 6 = 0",
                option_a="x=1, x=6", option_b="x=2, x=3",
                option_c="x=−2, x=−3", option_d="x=0, x=5",
                correct="B",
                explanation="По теореме Виета: сумма корней 5, произведение 6. Корни: 2 и 3.",
            ),
            Question(
                subject="math", topic="Степени",
                text="Чему равно 2⁵?",
                option_a="10", option_b="25", option_c="32", option_d="64",
                correct="C",
                explanation="2⁵ = 2·2·2·2·2 = 32.",
            ),
            Question(
                subject="rus", topic="Орфография",
                text="В каком слове пишется НН?",
                option_a="ветре..ый", option_b="серебря..ый",
                option_c="кожа..ый", option_d="деревя..ый",
                correct="D",
                explanation="«Деревянный» — исключение, пишется с двумя Н.",
            ),
        ]
        session.add_all(sample)
        await session.commit()


async def get_or_create_user(tg_id, username, first_name):
    async with SessionLocal() as session:
        user = await session.get(User, tg_id)
        if not user:
            user = User(id=tg_id, username=username, first_name=first_name)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def set_subject(tg_id, subject):
    async with SessionLocal() as session:
        user = await session.get(User, tg_id)
        if user:
            user.subject = subject
            await session.commit()


async def get_user(tg_id):
    async with SessionLocal() as session:
        return await session.get(User, tg_id)


async def get_random_question(subject):
    async with SessionLocal() as session:
        result = await session.execute(
            select(Question).where(Question.subject == subject).order_by(func.random()).limit(1)
        )
        return result.scalar_one_or_none()


async def get_question(qid):
    async with SessionLocal() as session:
        return await session.get(Question, qid)
