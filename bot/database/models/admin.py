import datetime

from sqlalchemy import Column, Integer, DateTime

from ..base import Base, engine, session_scope


class Admin(Base):
    __tablename__ = 'admins'

    user_id = Column(Integer, primary_key=True)
    added_by = Column(Integer, nullable=True)
    added_date = Column(DateTime, default=datetime.datetime.utcnow)

    def __init__(self, user_id, added_by=None):
        self.user_id = user_id
        self.added_by = added_by

    @staticmethod
    def all_ids():
        with session_scope() as session:
            return [row.user_id for row in session.query(Admin).all()]

    @staticmethod
    def add(user_id, added_by=None):
        with session_scope() as session:
            if not session.query(Admin).filter(Admin.user_id == user_id).one_or_none():
                session.add(Admin(user_id, added_by))

    @staticmethod
    def remove(user_id):
        with session_scope() as session:
            admin = session.query(Admin).filter(Admin.user_id == user_id).one_or_none()
            if admin:
                session.delete(admin)


Base.metadata.create_all(engine)
