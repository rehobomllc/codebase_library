import logging
from typing import Dict, Any

logger = logging.getLogger("treatment_navigator.debug")

# Simple debug tracker for development
class DebugTracker:
    def __init__(self):
        self.events = []
    
    def log_event(self, event_type: str, data: Dict[str, Any]):
        self.events.append({"type": event_type, "data": data})
        logger.debug(f"Debug event: {event_type} - {data}")

tracker = DebugTracker()

async def get_debug_dashboard_data():
    """Get debug dashboard data for the treatment navigator."""
    return {
        "status": "active",
        "events_count": len(tracker.events),
        "recent_events": tracker.events[-10:] if tracker.events else []
    }

def inject_debug_script(content: str) -> str:
    """Inject debug script into HTML content."""
    debug_script = """
    <script>
    // Treatment Navigator Debug Script
    window.treatmentDebug = {
        log: function(msg) {
            console.log('[Treatment Debug]', msg);
        }
    };
    </script>
    """
    return content.replace('</head>', f'{debug_script}</head>')

def debug_endpoint(func):
    """Decorator for debug endpoints."""
    def wrapper(*args, **kwargs):
        tracker.log_event("debug_endpoint_access", {"function": func.__name__})
        return func(*args, **kwargs)
    return wrapper 