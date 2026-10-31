from datetime import datetime
from sqlalchemy import JSON, BigInteger, Integer, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="engineer", server_default="engineer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="powercenter", server_default="powercenter")
    target_system: Mapped[str] = mapped_column(String(50), nullable=False, default="dbt_postgres", server_default="dbt_postgres")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    owner: Mapped[User] = relationship(back_populates="projects")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="project", passive_deletes=True)
    uploads: Mapped[list["Upload"]] = relationship(back_populates="project", passive_deletes=True)
    jobs: Mapped[list["Job"]] = relationship(back_populates="project", passive_deletes=True)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_xml: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded", server_default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project: Mapped[Project] = relationship(back_populates="uploads")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="upload")
    jobs: Mapped[list["Job"]] = relationship(back_populates="upload")


class Mapping(Base):
    __tablename__ = "mappings"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    upload_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("uploads.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description_ai: Mapped[str | None] = mapped_column(Text)
    complexity: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="parsed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project: Mapped[Project] = relationship(back_populates="mappings")
    upload: Mapped[Upload | None] = relationship(back_populates="mappings")
    transformations: Mapped[list["Transformation"]] = relationship(back_populates="mapping", cascade="all, delete-orphan", passive_deletes=True)
    lineage_edges: Mapped[list["LineageEdge"]] = relationship(back_populates="mapping", cascade="all, delete-orphan", passive_deletes=True)


class Transformation(Base):
    __tablename__ = "transformations"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    mapping_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    logic_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    seq_order: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping: Mapped[Mapping] = relationship(back_populates="transformations")
    ports: Mapped[list["Port"]] = relationship(back_populates="transformation", cascade="all, delete-orphan", passive_deletes=True)


class Port(Base):
    __tablename__ = "ports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    transformation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("transformations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    datatype: Mapped[str | None] = mapped_column(String(50))
    direction: Mapped[str | None] = mapped_column(String(10))
    expression: Mapped[str | None] = mapped_column(Text)
    transformation: Mapped[Transformation] = relationship(back_populates="ports")


class LineageEdge(Base):
    __tablename__ = "lineage_edges"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    mapping_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False)
    from_port_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ports.id", ondelete="CASCADE"), nullable=False)
    to_port_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ports.id", ondelete="CASCADE"), nullable=False)
    mapping: Mapped[Mapping] = relationship(back_populates="lineage_edges")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"))
    upload_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("uploads.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    progress: Mapped[int | None] = mapped_column(SmallInteger, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project: Mapped[Project | None] = relationship(back_populates="jobs")
    upload: Mapped[Upload | None] = relationship(back_populates="jobs")
