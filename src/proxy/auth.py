import asyncio
from fastapi import Security, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select
from src.database.connection import get_session
from src.database.models import ApiKey

security = HTTPBearer()

async def authenticate_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    session: Session = Depends(get_session)
) -> ApiKey:
    """
    Dependency injection guardian that extracts the bearer token,
    executes an O(1) indexed database lookup, and validates tenant state.
    """
    raw_key = credentials.credentials

    # Step 1: Query the indexed key table for an active token match
    statement = select(ApiKey).where(ApiKey.key == raw_key, ApiKey.is_active == True)
    api_key_record = await asyncio.to_thread(lambda: session.exec(statement).first())

    if not api_key_record:
        raise HTTPException(
            status_code=401,
            detail="Access Denied: Invalid or revoked Aegis Guard API Key."
        )

    # Step 2: Leverage the Relationship ORM mapping to check the owner account state
    if not api_key_record.user or not api_key_record.user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Access Denied: The associated user account has been deactivated."
        )

    # Return the full database record (gives downstream endpoints access to rate limits & user info)
    return api_key_record