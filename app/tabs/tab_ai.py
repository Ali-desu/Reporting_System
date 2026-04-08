"""
AI Assistant tab — conversational analytics agent.
"""
import streamlit as st

from agent import run_agent, check_api_key
from app.loaders import _engine


def render():
    st.markdown("#### AI Analytics Assistant")
    st.caption("Ask questions about your data in plain English. The assistant queries the live database to answer.")

    api_ready = check_api_key()
    if not api_ready:
        st.warning(
            "**API key not configured.** The assistant is ready but inactive.\n\n"
            "To activate:\n"
            "1. Get a key at [console.anthropic.com](https://console.anthropic.com)\n"
            "2. Add to your `.env` file:  `ANTHROPIC_API_KEY=sk-ant-...`\n"
            "3. Restart the app",
            icon="🔑",
        )

    if not api_ready:
        st.markdown('<p class="sec-title">Preview — Example Conversation</p>', unsafe_allow_html=True)
        st.caption("This is how the assistant will respond once your API key is configured.")
        DEMO = [
            ("user", "Give me an overall summary of the current state of the service desk."),
            ("assistant", (
                "Here's the current snapshot of your service desk:\n\n"
                "| Metric | Value |\n|---|---|\n"
                "| Total Issues | 7,750 |\n| Open | 3,214 |\n"
                "| Resolved | 4,536 |\n| Resolution Rate | 58.5% |\n"
                "| Critical Open | 47 |\n| SLA Compliance | 72.3% |\n"
                "| Avg Resolution Time | 8.4 days |\n\n"
                "**Key observations:**\n"
                "- SLA compliance is below the 80% target.\n"
                "- 47 critical issues remain open.\n"
                "- Resolution rate improved 4.2% vs last month.\n\n"
                "Would you like me to drill into SLA breaches by priority?"
            )),
        ]
        for role, content in DEMO:
            with st.chat_message(role):
                st.markdown(content)
        st.markdown("---")

    st.markdown('<p class="sec-title">Suggested Questions</p>', unsafe_allow_html=True)
    suggestions = [
        "Give me an overall summary of the current state of the service desk.",
        "What is our SLA compliance rate and how has it trended over the last 6 months?",
        "Which assignees have the highest and lowest resolution rates?",
        "How many critical issues are currently open and who owns them?",
        "Is sprint v22 R25 on track to complete on time?",
        "Which projects have the most unresolved issues right now?",
        "Show me the monthly trend of issues created vs resolved for this year.",
        "What are the most common root cause origins for our bugs?",
    ]
    cols = st.columns(2)
    for i, s in enumerate(suggestions):
        if cols[i % 2].button(s, key=f"suggestion_{i}", use_container_width=True):
            st.session_state["chat_prefill"] = s

    st.markdown("---")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_display" not in st.session_state:
        st.session_state.chat_display = []

    for msg in st.session_state.chat_display:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prefill = st.session_state.pop("chat_prefill", None)
    prompt  = st.chat_input("Ask anything about your service desk data…")
    if not prompt and prefill:
        prompt = prefill

    if prompt:
        st.session_state.chat_display.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Querying database…"):
                reply = run_agent(
                    user_message=prompt,
                    engine=_engine(),
                    history=st.session_state.chat_history,
                )
            st.markdown(reply)

        st.session_state.chat_display.append({"role": "assistant", "content": reply})
        st.session_state.chat_history.append({"role": "user",      "content": prompt})
        st.session_state.chat_history.append({"role": "assistant", "content": reply})

    if st.session_state.chat_display:
        if st.button("Clear conversation", key="clear_chat"):
            st.session_state.chat_history = []
            st.session_state.chat_display = []
            st.rerun()
