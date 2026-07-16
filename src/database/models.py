from typing import List, Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Relationship

class User(SQLModel, table=True):
    """Represents a client organization or internal developer account."""
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, nullable=False)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relational link back to associated keys
    api_keys: List["ApiKey"] = Relationship(back_populates="user")


class ApiKey(SQLModel, table=True):
    """Represents a secure credential token used to access the proxy gateways."""
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True, nullable=False)
    user_id: int = Field(foreign_key="user.id", nullable=False)
    is_active: bool = Field(default=True)
    
    # Traffic Control limits mapped directly to the key for low-latency handshakes
    rate_limit_rpm: int = Field(default=60, description="Requests Per Minute allowed for this key")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relational link back to the owning User
    user: User = Relationship(back_populates="api_keys")