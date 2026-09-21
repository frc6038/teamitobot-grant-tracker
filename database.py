"""
Database models and operations
"""

from sqlalchemy import (
    create_engine,
    text,
    Column,
    Integer,
    BigInteger,
    String,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    UniqueConstraint
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import pytz

from config import config


TURKEY_TZ = pytz.timezone("Europe/Istanbul")
Base = declarative_base()


# ==========================================
# DATABASE MODELS
# ==========================================

class User(Base):
    """User model - stores Telegram users"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_subscribed = Column(Boolean, default=False)
    total_scrapes = Column(Integer, default=0, nullable=False)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(TURKEY_TZ)
    )

    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User chat_id={self.chat_id}>"


class Grant(Base):
    """Grant model - stores detected grants"""

    __tablename__ = "grants"

    id = Column(Integer, primary_key=True)

    # Eski alanı migration tamamlanana kadar koruyoruz.
    text = Column(String(1000), nullable=True)

    # Yeni yapı
    title = Column(String(1000), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    url = Column(String(2000), nullable=True)

    detected_at = Column(
        DateTime,
        default=lambda: datetime.now(TURKEY_TZ),
        index=True
    )

    notifications = relationship(
        "Notification",
        back_populates="grant",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Grant id={self.id} title={self.title!r}>"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    grant_id = Column(Integer, ForeignKey("grants.id"), nullable=False)
    sent_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "grant_id",
            name="uq_notification_user_grant"
        ),
    )

    user = relationship("User", back_populates="notifications")
    grant = relationship("Grant", back_populates="notifications")


class Stats(Base):
    """Stats model - bot statistics"""

    __tablename__ = "stats"

    id = Column(Integer, primary_key=True)
    total_scrapes = Column(Integer, default=0)
    total_notifications = Column(Integer, default=0)
    total_users = Column(Integer, default=0)
    started_at = Column(
        DateTime,
        default=lambda: datetime.now(TURKEY_TZ)
    )
    last_scrape_at = Column(DateTime, nullable=True)


# ==========================================
# DATABASE SETUP
# ==========================================

engine = create_engine(
    config.DATABASE_URL,
    connect_args={
        "check_same_thread": False
    } if "sqlite" in config.DATABASE_URL else {}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def init_db():
    """Verify the schema is at the expected Alembic head(s); does not create tables.

    Şema yönetimi artık Alembic'e ait (bkz. alembic/). Bu fonksiyon sadece
    alembic_version tablosunun VARLIĞINA değil, veritabanının gerçekten
    BEKLENEN head revizyon(lar)ında olduğuna bakar. Eksik, eski, bilinmeyen
    veya birden fazla/farklı head durumunda net bir hatayla durur — DB
    URL'i veya kimlik bilgisi hiçbir zaman hata mesajına yazılmaz.
    """

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    repo_root = os.path.dirname(os.path.abspath(__file__))
    alembic_cfg = Config(os.path.join(repo_root, "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", os.path.join(repo_root, "alembic")
    )
    expected_heads = set(ScriptDirectory.from_config(alembic_cfg).get_heads())

    with engine.connect() as connection:
        version_table_exists = connection.execute(
            text("SELECT to_regclass('public.alembic_version')")
        ).scalar()

        current_heads = set()
        if version_table_exists is not None:
            current_heads = set(
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                )
                .scalars()
                .all()
            )

    if current_heads != expected_heads:
        raise RuntimeError(
            "Veritabanı şeması beklenen Alembic revizyonunda değil "
            f"(mevcut: {sorted(current_heads) or 'yok'}, "
            f"beklenen: {sorted(expected_heads)}). "
            "'alembic upgrade head' çalıştırın."
        )

    print("✅ Database schema verified (Alembic)")


def get_db():
    """Get database session"""

    session = SessionLocal()

    try:
        yield session

    finally:
        session.close()


# ==========================================
# DATABASE OPERATIONS
# ==========================================

class DB:
    """Database operations - static methods"""

    # ==========================================
    # USER OPERATIONS
    # ==========================================

    @staticmethod
    def add_or_get_user(
        chat_id: int,
        username: str = None
    ) -> User:
        """Add new user or get existing"""

        session = SessionLocal()

        try:
            user = session.query(User).filter(
                User.chat_id == chat_id
            ).first()

            if user:
                return user

            user = User(
                chat_id=chat_id,
                username=username
            )

            session.add(user)
            session.commit()

            print(f"✅ New user added: {chat_id}")

            return user

        finally:
            session.close()

    @staticmethod
    def get_user(chat_id: int) -> User:
        """Get user by chat_id"""

        session = SessionLocal()

        try:
            return session.query(User).filter(
                User.chat_id == chat_id
            ).first()

        finally:
            session.close()

    @staticmethod
    def subscribe_user(chat_id: int) -> str:
        """Subscribe user and return the result state."""

        session = SessionLocal()

        try:
            user = session.query(User).filter(
                User.chat_id == chat_id
            ).first()

            if not user:
                return "not_found"

            if user.is_subscribed:
                return "already_subscribed"

            user.is_subscribed = True
            session.commit()

            return "subscribed"

        finally:
            session.close()

    @staticmethod
    def unsubscribe_user(chat_id: int) -> str:
        """Unsubscribe user and return the result state."""

        session = SessionLocal()

        try:
            user = session.query(User).filter(
                User.chat_id == chat_id
            ).first()

            if not user:
                return "not_found"

            if not user.is_subscribed:
                return "already_unsubscribed"

            session.query(Notification).filter(
                Notification.user_id == user.id,
                Notification.sent_at.is_(None)
            ).delete(
                synchronize_session=False
            )

            user.is_subscribed = False
            session.commit()

            return "unsubscribed"

        finally:
            session.close()

    @staticmethod
    def get_subscribed_users() -> list:
        """Get all subscribed users."""

        session = SessionLocal()

        try:
            users = session.query(User).filter(
                User.is_subscribed.is_(True),
                User.is_active.is_(True)
            ).all()

            return [
                user.chat_id
                for user in users
            ]

        finally:
            session.close()

    @staticmethod
    def is_subscribed(chat_id: int) -> bool:
        """Check if user is subscribed."""

        session = SessionLocal()

        try:
            user = session.query(User).filter(
                User.chat_id == chat_id
            ).first()

            return user.is_subscribed if user else False

        finally:
            session.close()

    # ==========================================
    # GRANT OPERATIONS
    # ==========================================

    @staticmethod
    def add_grant(
        title: str,
        start_date=None,
        end_date=None,
        url: str = None
    ) -> int:
        """Add a grant to database or update an existing grant."""

        session = SessionLocal()

        try:
            existing = session.query(Grant).filter(
                (Grant.title == title) |
                (Grant.text == title)
            ).first()

            if existing:
                existing.text = title
                existing.title = title
                existing.start_date = start_date
                existing.end_date = end_date
                existing.url = url

                session.commit()

                return existing.id

            grant = Grant(
                text=title,
                title=title,
                start_date=start_date,
                end_date=end_date,
                url=url
            )

            session.add(grant)
            session.commit()

            return grant.id

        except IntegrityError:

            session.rollback()

            existing = session.query(Grant).filter(
                (Grant.title == title) |
                (Grant.text == title)
            ).first()

            if existing:
                existing.text = title
                existing.title = title
                existing.start_date = start_date
                existing.end_date = end_date
                existing.url = url

                session.commit()

                return existing.id

            raise

        finally:
            session.close()

    @staticmethod
    def get_all_grants() -> list:
        """Get all grants."""

        session = SessionLocal()

        try:
            return session.query(Grant).all()

        finally:
            session.close()

    @staticmethod
    def delete_grant(grant_id: int) -> bool:
        """
        Delete a grant and all related notifications.

        SQLAlchemy cascade on the Grant.notifications relationship
        removes associated notification records automatically.
        """

        session = SessionLocal()

        try:
            grant = session.query(Grant).filter(
                Grant.id == grant_id
            ).first()

            if not grant:
                return False

            title = grant.title or grant.text

            session.delete(grant)
            session.commit()

            print(
                f"🗑️ Grant silindi: "
                f"{grant_id} - {title}"
            )

            return True

        except Exception:
            session.rollback()
            raise

        finally:
            session.close()

    @staticmethod
    def delete_grants_before_id(max_id: int) -> int:
        """
        Delete grants with IDs lower than max_id
        and their related notifications.
        """

        session = SessionLocal()

        try:
            grants = session.query(Grant).filter(
                Grant.id < max_id
            ).all()

            deleted_count = len(grants)

            if not grants:
                return 0

            for grant in grants:
                session.delete(grant)

            session.commit()

            print(
                f"🗑️ {deleted_count} eski grant ve "
                f"bağlı bildirimleri silindi."
            )

            return deleted_count

        except Exception:
            session.rollback()
            raise

        finally:
            session.close()

    # ==========================================
    # NOTIFICATION OPERATIONS
    # ==========================================

    @staticmethod
    def get_user_notification_count(chat_id: int) -> int:
        """Get notification count for user."""

        session = SessionLocal()

        try:
            user = session.query(User).filter(
                User.chat_id == chat_id
            ).first()

            if not user:
                return 0

            return session.query(Notification).filter(
                Notification.user_id == user.id,
                Notification.sent_at.is_not(None)
            ).count()

        finally:
            session.close()

    @staticmethod
    def increment_user_scrape(chat_id: int):
        """Increment scrape count for a specific user."""

        session = SessionLocal()

        try:
            user = session.query(User).filter(
                User.chat_id == chat_id
            ).first()

            if not user:
                return

            user.total_scrapes += 1
            session.commit()

        finally:
            session.close()

    @staticmethod
    def get_active_users() -> list:
        """Get chat IDs of all active users."""

        session = SessionLocal()

        try:
            users = session.query(User).filter(
                User.is_active.is_(True)
            ).all()

            return [
                user.chat_id
                for user in users
            ]

        finally:
            session.close()

    @staticmethod
    def get_user_stats(chat_id: int) -> dict:
        """Get statistics for a specific user."""

        session = SessionLocal()

        try:
            user = session.query(User).filter(
                User.chat_id == chat_id
            ).first()

            if not user:
                return {
                    "scrapes": 0,
                    "notifications": 0,
                    "subscribed": False,
                }

            notification_count = session.query(
                Notification
            ).filter(
                Notification.user_id == user.id,
                Notification.sent_at.is_not(None)
            ).count()

            return {
                "scrapes": user.total_scrapes,
                "notifications": notification_count,
                "subscribed": user.is_subscribed,
            }

        finally:
            session.close()

    @staticmethod
    def create_pending_notification(
        chat_id: int,
        grant_id: int
    ) -> bool:
        """Create a pending notification if one does not already exist."""

        session = SessionLocal()

        try:
            user = session.query(User).filter(
                User.chat_id == chat_id
            ).first()

            if not user:
                return False

            existing = session.query(Notification).filter(
                Notification.user_id == user.id,
                Notification.grant_id == grant_id
            ).first()

            if existing:
                return False

            notification = Notification(
                user_id=user.id,
                grant_id=grant_id,
                sent_at=None
            )

            session.add(notification)

            try:
                session.commit()

            except IntegrityError:
                session.rollback()
                return False

            return True

        finally:
            session.close()

    @staticmethod
    def get_pending_notifications() -> list:
        """Get all pending notifications for active subscribed users."""

        session = SessionLocal()

        try:
            rows = (
                session.query(
                    Notification.id,
                    Notification.grant_id,
                    User.chat_id,
                    Grant.title,
                    Grant.start_date,
                    Grant.end_date,
                    Grant.url
                )
                .join(
                    User,
                    Notification.user_id == User.id
                )
                .join(
                    Grant,
                    Notification.grant_id == Grant.id
                )
                .filter(
                    Notification.sent_at.is_(None),
                    User.is_active.is_(True),
                    User.is_subscribed.is_(True)
                )
                .all()
            )

            return [
                {
                    "notification_id": notification_id,
                    "grant_id": grant_id,
                    "chat_id": chat_id,
                    "grant_title": grant_title,
                    "start_date": start_date,
                    "end_date": end_date,
                    "grant_url": grant_url,
                }
                for (
                    notification_id,
                    grant_id,
                    chat_id,
                    grant_title,
                    start_date,
                    end_date,
                    grant_url
                ) in rows
            ]

        finally:
            session.close()

    @staticmethod
    def mark_notification_sent(
        notification_id: int
    ) -> bool:
        """Mark a notification as successfully sent."""

        session = SessionLocal()

        try:
            notification = session.query(
                Notification
            ).filter(
                Notification.id == notification_id
            ).first()

            if not notification:
                return False

            if notification.sent_at is not None:
                return False

            notification.sent_at = datetime.now(TURKEY_TZ)
            session.commit()

            return True

        finally:
            session.close()

    # ==========================================
    # STATS OPERATIONS
    # ==========================================

    @staticmethod
    def get_or_create_stats() -> Stats:
        """Get or create stats."""

        session = SessionLocal()

        try:
            stats = session.query(Stats).first()

            if not stats:
                stats = Stats()
                session.add(stats)
                session.commit()

            return stats

        finally:
            session.close()

    @staticmethod
    def reset_started_at():
        """Reset bot start time for the current process."""

        session = SessionLocal()

        try:
            stats = session.query(Stats).first()

            if stats:
                stats.started_at = datetime.now(TURKEY_TZ)
                session.commit()

        finally:
            session.close()

    @staticmethod
    def increment_scrapes():
        """Increment scrape counter and record the time of this scrape."""

        session = SessionLocal()

        try:
            stats = session.query(Stats).first()

            if stats:
                stats.total_scrapes += 1
                stats.last_scrape_at = datetime.now(TURKEY_TZ)
                session.commit()

        finally:
            session.close()

    @staticmethod
    def increment_notifications():
        """Increment notification counter."""

        session = SessionLocal()

        try:
            stats = session.query(Stats).first()

            if stats:
                stats.total_notifications += 1
                session.commit()

        finally:
            session.close()

    @staticmethod
    def update_user_count():
        """Update user count."""

        session = SessionLocal()

        try:
            stats = session.query(Stats).first()

            count = session.query(User).filter(
                User.is_active.is_(True)
            ).count()

            if stats:
                stats.total_users = count
                session.commit()

        finally:
            session.close()

    @staticmethod
    def get_stats_dict() -> dict:
        """Get stats as dictionary."""

        session = SessionLocal()

        try:
            stats = session.query(Stats).first()

            if not stats:
                return {
                    "scrapes": 0,
                    "notifications": 0,
                    "users": 0,
                    "started": None,
                    "last_scrape": None,
                }

            return {
                "scrapes": stats.total_scrapes,
                "notifications": stats.total_notifications,
                "users": stats.total_users,
                "started": stats.started_at,
                "last_scrape": stats.last_scrape_at,
            }

        finally:
            session.close()

