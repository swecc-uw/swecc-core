from fastapi import FastAPI, Response, status as APIStatus
from .config import settings
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .mq import initialize_rabbitmq, shutdown_rabbitmq
from .mq import consumers
from .mq import producers
import asyncio
import logging
from .llm.gemini import Gemini
from .llm.context import ContextManager
from .llm.message import Message
from pydantic import BaseModel
from datetime import datetime
from .polling import Status, PollingRequest, generate_request_id

client = Gemini()
ctx = ContextManager()

waiting_requests: dict[str, PollingRequest] = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform startup tasks here
    await initialize_rabbitmq(asyncio.get_event_loop())
    yield
    # Perform shutdown tasks here
    await shutdown_rabbitmq()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConfigRequest(BaseModel):
    max_context_length: int
    context_invalidation_time_seconds: int
    system_instruction: str

@app.get("/test")
async def test():
    await producers.finish_review({
        "feedback": "This is a test feedback",
        "key": "1-1-test.pdf"
    })
    return {"message": "Hello, World!"}

# Register an inference user with the given key
# If context already exists, it won't change at all
# Users should call this route before making any completions
@app.post("/inference/{key}/config")
def config(key: str, config: ConfigRequest):
    if not key in ctx.context_configs:
        ctx.add_context_config(key, **config.model_dump())
    return {"config": ctx.context_configs[key]}


class CompleteRequest(BaseModel):
    message: str
    metadata: dict
    needs_context: bool = True

def format_message(message: CompleteRequest) -> str:
    return "".join(f"{key}: {value}\n" for key, value in message.metadata.items()) + f"Message: {message.message}\n"

async def complete_task(request_id: str, key: str, message: CompleteRequest):
    waiting_requests[request_id].status = Status.IN_PROGRESS
    try:
        message_parsed = format_message(message)
        prompt = ctx.contextualize_prompt(key, message_parsed) if message.needs_context else message_parsed
        model_response = await client.prompt_model(
            prompt, ctx.context_configs[key].system_instruction
        )
        logger.info(f"\n{prompt}\n")

        ctx.add_message_to_context(
            key,
            Message(
                message=message.message,
                response=model_response,
                timestamp=datetime.now(),
                metadata=message.metadata,
            ),
        )
    except ValueError as e:
        waiting_requests[request_id].status = Status.ERROR
        waiting_requests[request_id].error = str(e)
        logger.error(f"Error processing request {request_id}: {str(e)}")
        return
    except Exception as e:
        waiting_requests[request_id].status = Status.ERROR
        waiting_requests[request_id].error = str(e)
        logger.error(f"Error processing request {request_id}: {str(e)}")
        return

    waiting_requests[request_id].status = Status.SUCCESS
    waiting_requests[request_id].result = model_response
    logger.info(
        f"Completed request {request_id} for key {key}. Response: {model_response}"
    )


# Get a completion for the given message
@app.post("/inference/{key}/complete", status_code=APIStatus.HTTP_202_ACCEPTED)
async def complete(key: str, message: CompleteRequest):
    request_id = generate_request_id()
    waiting_requests[request_id] = PollingRequest(
        request_id=request_id,
        status=Status.PENDING,
        result=None,
        error=None,
    )
    asyncio.create_task(
        complete_task(
            request_id,
            key,
            message,
        )
    )
    return {"request_id": request_id}


# Get the status of a request
@app.get("/inference/status/{request_id}")
async def status(request_id: str, response: Response):
    if request_id not in waiting_requests:
        response.status_code = APIStatus.HTTP_404_NOT_FOUND
        return {"error": "Request ID not found."}
    request = waiting_requests[request_id]

    if request.status == Status.PENDING:
        return {"status": "pending"}
    elif request.status == Status.IN_PROGRESS:
        return {"status": "in_progress"}
    elif request.status == Status.SUCCESS:
        result = request.result
        del waiting_requests[request_id]
        return {"status": "success", "result": result}
    elif request.status == Status.ERROR:
        error = request.error
        del waiting_requests[request_id]
        response.status_code = APIStatus.HTTP_500_INTERNAL_SERVER_ERROR
        return {"status": "error", "error": error}
    else:
        # Unreachable
        response.status_code = APIStatus.HTTP_500_INTERNAL_SERVER_ERROR
        return {"error": "Unknown status."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
