from . import producer as mq_producer
import json

@mq_producer(
    exchange='swecc-ai-exchange',
    routing_key='reviewed'
)
async def finish_review(data: dict):
  feedback = data['feedback']
  key = data['key']

  if not feedback or not key:
    raise ValueError("Feedback and key must be provided")

  message_body = {
    "feedback": feedback,
    "key": key
  }
  return json.dumps(message_body).encode('utf-8')