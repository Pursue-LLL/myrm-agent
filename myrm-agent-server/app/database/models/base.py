"""
[POS] ORM 模型基类。提供 SQLAlchemy DeclarativeBase 供所有模型继承。
[OUTPUT] Base: 所有数据库模型的声明式基类
"""

from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    pass
