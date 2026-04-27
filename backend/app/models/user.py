from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.db import Base
import uuid
import secrets

class User(Base):
    """
    系统用户/租户模型
    """
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: f"user-{uuid.uuid4().hex[:8]}")
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    
    bio = Column(Text, nullable=True) # 个人简介，供智能体理解用户背景
    avatar = Column(String, nullable=True) # 头像 URL
    preferences = Column(JSON, nullable=True, default={}) # 智能体协作首选项
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 一个用户可以有多个 API 秘钥
    api_keys = relationship("UserApiKey", back_populates="user", cascade="all, delete-orphan")
    organization_memberships = relationship("UserOrganizationMembership", back_populates="user", cascade="all, delete-orphan")

class UserApiKey(Base):
    """
    用户 API 秘钥，用于外部应用（如 Dify/LobeChat）接入鉴权
    """
    __tablename__ = "user_api_keys"

    id = Column(String, primary_key=True, default=lambda: f"ak-{uuid.uuid4().hex[:8]}")
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # 秘钥本身（实际存储的是带盐的哈希值或掩码，这里简化存储加盐原始值在演示中，生产请哈希）
    key = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True, default="Default Key")
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")


class Organization(Base):
    """
    组织模型（组织级租户隔离基础设施）
    """
    __tablename__ = "organizations"

    id = Column(String, primary_key=True, default=lambda: f"org-{uuid.uuid4().hex[:8]}")
    code = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    memberships = relationship("UserOrganizationMembership", back_populates="organization", cascade="all, delete-orphan")


class UserOrganizationMembership(Base):
    """
    用户-组织成员关系
    """
    __tablename__ = "user_organization_memberships"

    id = Column(String, primary_key=True, default=lambda: f"orgm-{uuid.uuid4().hex[:8]}")
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String, nullable=False, default="member")  # owner/admin/member/viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User", back_populates="organization_memberships")

    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uix_org_user_membership"),
    )
