from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import json
from pathlib import Path
import asyncio

from .mq import initialize_rabbitmq, shutdown_rabbitmq
from .mq.consumers import *
from .config import settings
from .auth import Auth
from .events import Event, EventType
from .connection_manager import ConnectionManager
from .event_emitter import EventEmitter
from .handlers.echo_handler import EchoHandler
from .handlers.logs_handler import ContainerLogsHandler
from contextlib import asynccontextmanager
from .handlers import HandlerKind
from .handlers.resume_handler import ResumeHandler

EVENT_EMITTERS: dict[HandlerKind, EventEmitter] = {
    HandlerKind.Echo: EventEmitter(),
    HandlerKind.Logs: EventEmitter(),
    HandlerKind.Resume: EventEmitter(),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def authenticate_and_connect(
    kind: HandlerKind, websocket: WebSocket, token: str
) -> tuple[dict, WebSocket]:
    user = await Auth.authenticate_ws(websocket, token)
    if not user:
        logger.warning("Authentication failed for WebSocket connection")
        return None, None

    user_id = user["user_id"]
    username = user["username"]

    connection_manager = ConnectionManager()
    websocket = await connection_manager.register_connection(kind, user_id, websocket)

    connection_event = Event(
        type=EventType.CONNECTION,
        user_id=user_id,
        username=username,
        websocket=websocket,
    )
    await EVENT_EMITTERS[kind].emit(connection_event)

    return user, websocket


async def cleanup_websocket(kind: HandlerKind, user: dict):
    connection_manager = ConnectionManager()
    event_emitter = EVENT_EMITTERS[kind]
    try:
        connection_manager.disconnect(kind, user["user_id"])
        disconnect_event = Event(
            type=EventType.DISCONNECT,
            user_id=user["user_id"],
            username=user["username"],
        )
        await event_emitter.emit(disconnect_event)
        logger.info(
            f"Echo client disconnected: {user['username']} (ID: {user['user_id']})"
        )
    except Exception as e:
        logger.error(f"Error during WebSocket cleanup: {str(e)}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize RabbitMQ connection
    await initialize_rabbitmq(asyncio.get_event_loop())
    yield
    # Cleanup RabbitMQ connection if needed
    await shutdown_rabbitmq()


app = FastAPI(title="SWECC Sockets", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up static files
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")


# Basic endpoints
@app.get("/")
async def root():
    return {"status": "online", "message": "WebSocket server is running"}


@app.get("/ping")
async def ping():
    return Response(content="pong", media_type="text/plain")


# Echo endpoint
@app.websocket("/ws/echo/{token}")
async def echo_endpoint(websocket: WebSocket, token: str):
    # Create endpoint-specific instances
    connection_manager = ConnectionManager()
    event_emitter = EVENT_EMITTERS[HandlerKind.Echo]
    echo_handler = EchoHandler(event_emitter)

    user = None

    try:
        user, websocket = await authenticate_and_connect(
            HandlerKind.Echo, websocket, token
        )
        user_id = user["user_id"]
        username = user["username"]
        # Message loop
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    message_data = json.loads(data)

                    message_event = Event(
                        type=EventType.MESSAGE,
                        user_id=user_id,
                        username=username,
                        data=message_data,
                        websocket=websocket,
                    )
                    await event_emitter.emit(message_event)
                except json.JSONDecodeError:
                    if not connection_manager.is_connection_closing(websocket):
                        await echo_handler.safe_send(
                            websocket,
                            {"type": "error", "message": "Invalid JSON message format"},
                        )
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(
                    f"Error handling WebSocket message: {str(e)}", exc_info=True
                )
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error handling WebSocket connection: {str(e)}", exc_info=True)
    finally:
        if user:
            await cleanup_websocket(HandlerKind.Echo, user)


# Logs endpoint
@app.websocket("/ws/logs/{token}")
async def logs_endpoint(websocket: WebSocket, token: str):
    # Create endpoint-specific instances
    connection_manager = ConnectionManager()
    event_emitter = EVENT_EMITTERS[HandlerKind.Logs]
    logs_handler = ContainerLogsHandler(event_emitter)

    user = None

    try:
        # Authenticate and check for admin rights
        user, websocket = await authenticate_and_connect(
            HandlerKind.Logs, websocket, token
        )
        user_id = user["user_id"]
        username = user["username"]
        # Message loop
        while True:
            try:
                data = await websocket.receive_text()
                try:
                    message_data = json.loads(data)
                    message_data["groups"] = user.get("groups", [])

                    message_event = Event(
                        type=EventType.MESSAGE,
                        user_id=user_id,
                        username=username,
                        data=message_data,
                        websocket=websocket,
                    )
                    await event_emitter.emit(message_event)
                except json.JSONDecodeError:
                    if not connection_manager.is_connection_closing(websocket):
                        await logs_handler.safe_send(
                            websocket,
                            {"type": "error", "message": "Invalid JSON message format"},
                        )
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(
                    f"Error handling WebSocket message: {str(e)}", exc_info=True
                )
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error handling WebSocket connection: {str(e)}", exc_info=True)
    finally:
        if user:
            await cleanup_websocket(HandlerKind.Logs, user)


@app.websocket("/ws/resume/{token}")
async def resume_endpoint(websocket: WebSocket, token: str):
    event_emitter = EVENT_EMITTERS[HandlerKind.Resume]
    # Unused, but necessary so events are subscribed to
    resume_handler = ResumeHandler(event_emitter)

    user = None

    try:
        user, websocket = await authenticate_and_connect(
            HandlerKind.Resume, websocket, token
        )
        user_id = user["user_id"]
        username = user["username"]
        # Message loop
        while True:
            try:
                # Dummy event loop to keep the connection alive
                data = await websocket.receive_text()
                message_event = Event(
                    type=EventType.MESSAGE,
                    user_id=user_id,
                    username=username,
                    data={"data": data},
                    websocket=websocket,
                )
                await event_emitter.emit(message_event)
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(
                    f"Error handling WebSocket message: {str(e)}", exc_info=True
                )
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error handling WebSocket connection: {str(e)}", exc_info=True)
    finally:
        if user:
            await cleanup_websocket(HandlerKind.Resume, user)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
