from enum import Enum

class HandlerKind(str, Enum):
  Echo = "echo"
  Logs = "logs"
  Resume = "resume"