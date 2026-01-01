# SWECC Sockets

Event-driven WebSocket server

## Authentication

The server expects a JWT token in the URL path. The token should contain the user's ID and username, signed with swecc-server's secret key.

## Adding New Functionality

### 1. Define New Event Type (if needed)

Add to `events.py`:

```python
class EventType(str, Enum):
    # Existing types...
    NEW_FEATURE = "new_feature"
```

### 2. Create a New Handler

Create `handlers/new_feature_handler.py`:

```python
from ..events import Event, EventType
from ..event_emitter import EventEmitter

class NewFeatureHandler:
    def __init__(self):
        self.emitter = EventEmitter()
        # Subscribe to relevant events
        self.emitter.on(EventType.CONNECTION, self.handle_connect)
        self.emitter.on(EventType.NEW_FEATURE, self.handle_new_feature)

    async def handle_connect(self, event: Event) -> None:
        # Handle new connections
        pass

    async def handle_new_feature(self, event: Event) -> None:
        # Implement feature logic
        pass
```

### 3. Register the Handler

In `main.py`:

```python
from .handlers.new_feature_handler import NewFeatureHandler

# Add to existing registrations
service_registry.register("new_feature", NewFeatureHandler)
```

### 4. Emit Events (from other components)

```python
await event_emitter.emit(Event(
    type=EventType.NEW_FEATURE,
    user_id=user_id,
    username=username,
    data={"key": "value"}
))
```

## Testing

### Running with SWECC Server (Recommended)

Start the SWECC server:

```bash
cd /path/to/swecc-server
source your_venv_with_env_vars/bin/activate
docker-compose up --build -d
```

Run the server:

```bash
cd /path/to/swecc-sockets
source your_venv_with_env_vars/bin/activate
docker-compose up --build
```

### Running Locally

Start the server:

```bash
cd /path/to/swecc-sockets
source your_venv_with_env_vars/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8004
```