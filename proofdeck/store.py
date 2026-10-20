"""Storage: decks, per-recipient links, visits, card-level dwell, alerts."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class DeckRow(Base):
    __tablename__ = "decks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    mode: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)  # Deck.to_dict()
    facts: Mapped[dict] = mapped_column(JSON)  # facts snapshot: what it was grounded on
    brand: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    links: Mapped[list["Link"]] = relationship(back_populates="deck")


class Link(Base):
    __tablename__ = "links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id"))
    token: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: secrets.token_urlsafe(9))
    recipient: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255))
    email_gate: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deck: Mapped[DeckRow] = relationship(back_populates="links")
    visits: Mapped[list["Visit"]] = relationship(back_populates="link")


class Visit(Base):
    """One device/browser on one link. A second distinct one = probably forwarded."""

    __tablename__ = "visits"
    __table_args__ = (UniqueConstraint("link_id", "visitor_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id"))
    visitor_id: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))  # hash(ua family + /24)
    email: Mapped[str | None] = mapped_column(String(255))
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sessions: Mapped[int] = mapped_column(Integer, default=1)
    link: Mapped[Link] = relationship(back_populates="visits")


class CardTime(Base):
    __tablename__ = "card_time"
    __table_args__ = (UniqueConstraint("visit_id", "card"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"))
    card: Mapped[int] = mapped_column(Integer)
    ms: Mapped[int] = mapped_column(Integer, default=0)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("link_id", "kind", "key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id"))
    kind: Mapped[str] = mapped_column(String(32))  # opened | forwarded | hot_card | returned
    key: Mapped[str] = mapped_column(String(64), default="")  # dedupe key
    message: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


def make_session_factory(url: str | None = None):
    url = url or os.getenv("DATABASE_URL", "sqlite:///proofdeck.db")
    kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    engine = create_engine(url, **kw)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
