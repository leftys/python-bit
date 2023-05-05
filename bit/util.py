def get_message_topic(message):
    if "channel" in message:
        topic = message["channel"]
    elif "type" in message:
        topic = message["type"]
    else:
        topic = None
    return topic
