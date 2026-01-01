from ..event_emitter import EventEmitter
from .base_handler import BaseHandler

class ResumeHandler(BaseHandler):
    def __init__(self, event_emitter: EventEmitter):
        super().__init__(event_emitter, "Resume")
