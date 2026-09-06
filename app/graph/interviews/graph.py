from langgraph.graph import END, START, StateGraph

from .nodes import (
    create_calendar_invite_node,
    create_meeting_node,
    persist_interview_node,
    schedule_interview_node,
    send_interview_email_node,
)
from .state import InterviewState


builder = StateGraph(InterviewState)
builder.add_node("schedule_interview", schedule_interview_node)
builder.add_node("create_meeting", create_meeting_node)
builder.add_node("create_calendar_invite", create_calendar_invite_node)
builder.add_node("persist_interview", persist_interview_node)
builder.add_node("send_interview_email", send_interview_email_node)

builder.add_edge(START, "schedule_interview")
builder.add_edge("schedule_interview", "create_meeting")
builder.add_edge("create_meeting", "create_calendar_invite")
builder.add_edge("create_calendar_invite", "send_interview_email")
builder.add_edge("send_interview_email", "persist_interview")
builder.add_edge("persist_interview", END)

interview_graph = builder.compile()
