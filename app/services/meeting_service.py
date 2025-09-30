from datetime import datetime


def create_meeting_link(provider: str, when: datetime) -> str:
# TODO: integrate Google/Graph; MVP: return placeholder
return f"https://meet.example.com/{provider}/task-review"