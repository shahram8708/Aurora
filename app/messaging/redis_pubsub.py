from flask import current_app


def publish_event(channel: str, payload: dict):
    # Broadcast through Redis so multiple Socket.IO workers pick up the event
    client = getattr(current_app, "redis_client", None)
    if not client:
        return
    client.publish(channel, current_app.json.dumps(payload))


def channel_for_conversation(conversation_id: str) -> str:
    return f"conversation:{conversation_id}"


def channel_for_user(user_id: str) -> str:
    return f"user:{user_id}"
