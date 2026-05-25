from typing import List, Optional, Union

from fastapi import WebSocket, status
from swecc_jwt import validate_member_token

from .config import settings


class Auth:
    @staticmethod
    async def validate_token(token: str) -> Optional[dict]:
        return validate_member_token(
            token,
            secret=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

    @staticmethod
    async def authenticate_ws(
        websocket: WebSocket, token: str, required_groups: Union[List[str], None] = None
    ) -> Optional[dict]:
        user = await Auth.validate_token(token)

        if not user:
            await websocket.accept()
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None

        if required_groups:
            has_permission = any(group in user.get("groups", []) for group in required_groups)
            if not has_permission:
                await websocket.accept()
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return None

        return user
