import streamlit as st
import streamlit.components.v1 as components
import requests
import os
import json
import io
import csv
from uuid import uuid4
from datetime import datetime
import plotly.express as px

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")


def post_to_backend(path, **kwargs):
    headers = kwargs.pop("headers", {})
    token = st.session_state.get("access_token")
    if token:
        headers = {**headers, "Authorization": f"Bearer {token}"}
    for attempt in range(3):
        try:
            return requests.post(f"{BACKEND_URL}{path}", headers=headers, **kwargs)
        except requests.ConnectionError:
            if attempt == 2:
                raise
            import time
            time.sleep(2)


def get_from_backend(path, **kwargs):
    headers = kwargs.pop("headers", {})
    token = st.session_state.get("access_token")
    if token:
        headers = {**headers, "Authorization": f"Bearer {token}"}
    for attempt in range(3):
        try:
            return requests.get(f"{BACKEND_URL}{path}", headers=headers, **kwargs)
        except requests.ConnectionError:
            if attempt == 2:
                raise
            import time
            time.sleep(2)


st.set_page_config(
    page_title="InfiSupport — Support Copilot & AI Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Styling (Retaining 100% of your dark theme & layout)
st.markdown("""
<style>
    .main { background-color: #0B0E14; color: #E2E8F0; }
    .header-bar {
        background: linear-gradient(135deg, #1E1E2E 0%, #0F172A 100%);
        padding: 14px 20px; border-radius: 12px; border: 1px solid #2A2D3D;
        display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
    }
    .badge-live {
        background-color: #065F46; color: #34D399; padding: 4px 10px;
        border-radius: 20px; font-size: 0.8rem; font-weight: bold; border: 1px solid #059669;
    }
    .vip-card {
        background: linear-gradient(145deg, #131822, #1A202C);
        padding: 14px; border-radius: 10px; border: 1px solid #2D3748; margin-bottom: 15px;
    }
    .risk-card {
        background: #181C28; padding: 12px; border-radius: 8px;
        border: 1px solid #2E3440; text-align: center;
    }
    .risk-title { font-size: 0.75rem; color: #94A3B8; text-transform: uppercase; font-weight: bold; }
    .risk-val { color: #EF4444; font-weight: 900; font-size: 1.05rem; }
    .chat-bubble-user {
        background: linear-gradient(135deg, #1E293B, #0F172A); color: #F8FAFC;
        padding: 12px 16px; border-radius: 12px 12px 12px 2px; margin-bottom: 10px;
        border-left: 4px solid #EF4444;
    }
    .chat-bubble-agent {
        background: linear-gradient(135deg, #1E1B4B, #311B92); color: #F1F5F9;
        padding: 12px 16px; border-radius: 12px 12px 2px 12px; margin-bottom: 10px;
        border-left: 4px solid #6366F1;
    }
    .ai-guidance-box {
        background: linear-gradient(180deg, #1E1B4B 0%, #111827 100%);
        border: 1px solid #4338CA; border-radius: 10px; padding: 14px; margin-bottom: 15px;
    }
    .coaching-box {
        background: linear-gradient(135deg, #271E05 0%, #171203 100%);
        border: 1px solid #D97706; border-radius: 8px; padding: 12px; color: #FDE68A;
    }
    .cbr-card {
        background: #111827; border: 1px solid #1F2937; border-radius: 10px;
        padding: 14px; margin-bottom: 12px;
    }
    .cbr-badge { background-color: #064E3B; color: #34D399; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# State Management
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "agent_draft" not in st.session_state: st.session_state.agent_draft = ""
if "customer_input_text" not in st.session_state:
    st.session_state.customer_input_text = "I am extremely disappointed. I paid over $1,200 for this laptop and it still hasn't arrived. I have already contacted support twice!"
if "customer_id" not in st.session_state: st.session_state.customer_id = None
if "case_id" not in st.session_state: st.session_state.case_id = None
if "active_case" not in st.session_state: st.session_state.active_case = None
if "priority_queue" not in st.session_state: st.session_state.priority_queue = []
if "priority_queue_error" not in st.session_state: st.session_state.priority_queue_error = ""
if "priority_queue_loaded" not in st.session_state: st.session_state.priority_queue_loaded = False
if "selected_queue_case" not in st.session_state: st.session_state.selected_queue_case = None
if "new_case_mode" not in st.session_state: st.session_state.new_case_mode = False
if "access_token" not in st.session_state: st.session_state.access_token = ""
if "current_user" not in st.session_state: st.session_state.current_user = None
if "case_brief" not in st.session_state: st.session_state.case_brief = None
if "case_brief_case_id" not in st.session_state: st.session_state.case_brief_case_id = None
if "admin_escalation_case" not in st.session_state: st.session_state.admin_escalation_case = None
if "admin_agent_detail" not in st.session_state: st.session_state.admin_agent_detail = None


def generate_new_case_ids():
    suffix = uuid4().hex[:12].upper()
    return f"CUST-{suffix}", f"CASE-{suffix}"


def has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in ("", "Unavailable", "Unassigned", "N/A", "--", "None", "null")
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def format_similarity(value):
    if not has_value(value):
        return None
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return None


if not st.session_state.current_user:
    def attempt_login(username, password, role):
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/auth/login",
                json={"username": username, "password": password, "role": role},
                timeout=15,
            )
            if response.status_code == 200:
                login_data = response.json()
                st.session_state.access_token = login_data["access_token"]
                st.session_state.current_user = login_data["user"]
                st.rerun()
            try:
                detail = response.json().get("detail", "Unable to sign in.")
            except ValueError:
                detail = "Unable to sign in."
            st.error(detail)
        except requests.RequestException as error:
            st.error(f"Unable to reach the backend: {error}")

    st.title("⚡ InfiSupport")
    st.subheader("Demo Login — Enter any email and password")

    with st.form("login_form"):
        username = st.text_input("Email", placeholder="your.name@example.com")
        password = st.text_input("Password", type="password", autocomplete="new-password")
        role = st.selectbox("Role", ["Human Agent", "Administrator"])
        role = "admin" if role == "Administrator" else "human_agent"
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if submitted:
        attempt_login(username, password, role)
    st.stop()

current_user = st.session_state.current_user

if current_user["role"] == "admin":
    # Keep the existing administrator header unchanged.
    st.markdown(f"""
    <div class="header-bar">
        <div>
            <span style="font-size: 1.4rem; font-weight: bold; color: #6366F1;">⚡ InfiSupport</span>
            <span style="color: #64748B; margin-left: 10px;">| Real-Time AI Assistant</span>
        </div>
        <div>
            <span class="badge-live">● AI Service Connected</span>
            <span style="color: #94A3B8; margin-left: 15px; font-size: 0.85rem;">{current_user['role'].replace('_', ' ').title()}: <b>{current_user['display_name']}</b></span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    logout_col, identity_col = st.columns([1, 5])
    with logout_col:
        if st.button("Sign out", use_container_width=True):
            st.session_state.access_token = ""
            st.session_state.current_user = None
            st.rerun()
    with identity_col:
        st.caption(f"Signed in as {current_user['username']} ({current_user['role']}).")

if current_user["role"] == "admin":
    st.subheader("Administrator Overview")
    try:
        analytics_response = get_from_backend("/api/admin/analytics", timeout=30)
        if analytics_response.status_code == 200:
            analytics = analytics_response.json()
            metric_1, metric_2, metric_3, metric_4, metric_5 = st.columns(5)
            metric_1.metric("Total Cases", analytics.get("total_cases", 0))
            metric_2.metric("Open Cases", analytics.get("open_cases", 0))
            metric_3.metric("Resolved Cases", analytics.get("resolved_cases", 0))
            metric_4.metric("Escalated Cases", analytics.get("escalated_cases", 0))

            resolution_seconds = analytics.get("average_resolution_time_seconds")
            resolution_display = "No resolved cases" if resolution_seconds is None else f"{resolution_seconds / 60:.1f} min"
            metric_5.metric("Average Resolution Time", resolution_display)

            st.markdown("### Department Distribution")
            department_counts = analytics.get("cases_by_department", [])
            if department_counts:
                department_figure = px.pie(
                    department_counts,
                    names="department",
                    values="count",
                    hole=0.52,
                    color_discrete_sequence=["#6366F1", "#F59E0B", "#14B8A6", "#EF4444"],
                )
                department_figure.update_layout(margin=dict(t=20, b=20, l=20, r=20), legend_title_text="Department")
                st.plotly_chart(department_figure, use_container_width=True)
            else:
                st.info("No department data available.")

            st.markdown("### Department Performance")
            department_performance = analytics.get("department_performance", [])
            if department_performance:
                performance_figure = px.bar(
                    department_performance,
                    x="successfully_resolved",
                    y="department",
                    orientation="h",
                    barmode="group",
                    labels={"successfully_resolved": "Cases", "department": "Department"},
                    color_discrete_sequence=["#14B8A6"],
                )
                performance_figure.add_bar(
                    x=[item.get("escalated", 0) for item in department_performance],
                    y=[item.get("department", "Unspecified") for item in department_performance],
                    name="Escalated",
                    orientation="h",
                    marker_color="#EF4444",
                )
                performance_figure.data[0].name = "Successfully Resolved"
                performance_figure.update_layout(margin=dict(t=20, b=20, l=20, r=20), legend_title_text="Outcome")
                st.plotly_chart(performance_figure, use_container_width=True)
            else:
                st.info("No department performance data available.")

            st.markdown("### Agent Performance")
            performance_response = get_from_backend("/api/admin/agent-performance", timeout=90)
            agent_rows = performance_response.json().get("agents", []) if performance_response.status_code == 200 else []
            if performance_response.status_code != 200:
                st.error(f"Unable to load agent performance: {performance_response.text}")
            agent_table = [
                {
                    "Agent": row.get("agent_name", "—"),
                    "Cases Handled": row.get("cases_handled", "—"),
                    "Cases Resolved": row.get("cases_resolved", "—"),
                    "Cases Escalated": row.get("cases_escalated", "—"),
                    "Cases Pending": row.get("cases_pending", "—"),
                    "Avg. Resolution Time": row.get("avg_resolution_time", "—"),
                }
                for row in agent_rows
            ]
            if agent_table:
                header = st.columns([1.4, 1, 1, 1, 1, 1.2, .6])
                for cell, label in zip(header, ["Agent", "Cases Handled", "Cases Resolved", "Cases Escalated", "Cases Pending", "Avg. Resolution Time", ""]):
                    cell.markdown(f"**{label}**")
                for agent, row in zip(agent_rows, agent_table):
                    cells = st.columns([1.4, 1, 1, 1, 1, 1.2, .6])
                    for cell, label in zip(cells[:-1], ["Agent", "Cases Handled", "Cases Resolved", "Cases Escalated", "Cases Pending", "Avg. Resolution Time"]):
                        cell.write(row[label])
                    if cells[-1].button("Open", key=f"admin_agent_open_{agent.get('agent_id')}"):
                        detail_response = get_from_backend(f"/api/admin/agents/{agent.get('agent_id')}/cases", timeout=90)
                        if detail_response.status_code == 200:
                            st.session_state.admin_agent_detail = detail_response.json()
                        else:
                            st.error(f"Unable to load agent cases: {detail_response.text}")
                        st.rerun()
                if st.session_state.get("admin_agent_detail"):
                    agent_detail = st.session_state.admin_agent_detail
                    st.markdown(f"#### Agent Case Sheet · {agent_detail.get('agent_id', '—')}")
                    cases = agent_detail.get("cases", [])
                    case_columns = [
                        "case_id", "customer", "issue_type", "intent", "key_issue", "department", "priority",
                        "priority_score", "sentiment", "urgency", "escalation_risk", "status", "escalated",
                        "escalation_reason", "created_at", "resolved_at", "resolution_time", "resolution_summary",
                    ]
                    st.dataframe(
                        [{column: case.get(column, "—") for column in case_columns} for case in cases],
                        use_container_width=True,
                        hide_index=True,
                    )
                    csv_buffer = io.StringIO()
                    csv_writer = csv.DictWriter(csv_buffer, fieldnames=case_columns)
                    csv_writer.writeheader()
                    csv_writer.writerows([{column: case.get(column, "") for column in case_columns} for case in cases])
                    st.download_button(
                        "Download CSV",
                        data=csv_buffer.getvalue(),
                        file_name=f"{agent_detail.get('agent_id', 'agent')}_cases.csv",
                        mime="text/csv",
                        key="admin_agent_cases_csv",
                    )
                    if st.button("Close Agent Case Sheet", key="admin_agent_detail_close"):
                        st.session_state.admin_agent_detail = None
                        st.rerun()
            report_buffer = io.StringIO()
            writer = csv.DictWriter(report_buffer, fieldnames=list(agent_table[0].keys()) if agent_table else [
                "Agent", "Cases Handled", "Cases Resolved", "Cases Escalated", "Cases Pending", "Avg. Resolution Time",
            ])
            writer.writeheader()
            writer.writerows(agent_table)
            st.download_button(
                "Download Agent Performance CSV",
                data=report_buffer.getvalue(),
                file_name="agent_performance.csv",
                mime="text/csv",
            )

            st.markdown("### Notifications")
            for notification in analytics.get("complaint_trends", ["No significant complaint trends detected."]):
                st.info(notification)
            try:
                notification_response = get_from_backend("/api/admin/notifications", timeout=90)
                if notification_response.status_code == 200:
                    escalation_notifications = notification_response.json().get("notifications", [])
                    if escalation_notifications:
                        for notification in escalation_notifications:
                            st.warning(
                                f"{notification.get('message', 'Escalation received.')} "
                                f"Priority: {notification.get('priority', 'Not available')} | "
                                f"Reason: {notification.get('reason', 'Not available')}"
                            )
                    else:
                        st.caption("No new unresolved escalation notifications.")
                else:
                    st.error(f"Unable to load escalation notifications: {notification_response.text}")
            except requests.RequestException as error:
                st.error(f"Unable to reach the escalation notification service: {error}")

            st.markdown("### Escalation Queue")
            escalation_response = get_from_backend("/api/admin/escalations", timeout=30)
            if escalation_response.status_code == 200:
                escalation_cases = escalation_response.json().get("cases", [])
                if escalation_cases:
                    header = st.columns([0.7, 1.2, 1.2, 1.2, 1.1, 1.1, 1.8, 0.7])
                    for cell, label in zip(header, ["Priority", "Case ID", "Customer", "Intent", "Sentiment", "Urgency", "Reason", ""]):
                        cell.markdown(f"**{label}**")
                    for escalation_case in escalation_cases:
                        row = st.columns([0.7, 1.2, 1.2, 1.2, 1.1, 1.1, 1.8, 0.7])
                        row[0].write(escalation_case.get("priority_label", "Not available"))
                        row[1].write(escalation_case.get("case_id", "Not available"))
                        customer = escalation_case.get("customer") or {}
                        row[2].write(customer.get("name") or escalation_case.get("customer_id", "Not available"))
                        row[3].write(escalation_case.get("intent") or "Not available")
                        row[4].write(escalation_case.get("sentiment") or "Not available")
                        row[5].write(escalation_case.get("urgency") or "Not available")
                        row[6].write(escalation_case.get("escalation_reason") or "Not available")
                        if row[7].button("Open", key=f"admin_open_{escalation_case['case_id']}"):
                            detail_response = get_from_backend(
                                f"/api/cases/{escalation_case['customer_id']}/{escalation_case['case_id']}/analysis",
                                timeout=30,
                            )
                            if detail_response.status_code == 200:
                                st.session_state.admin_escalation_case = {
                                    "queue": escalation_case,
                                    "analysis": detail_response.json(),
                                }
                            else:
                                st.error(f"Unable to load stored case analysis: {detail_response.text}")
                            st.rerun()
                else:
                    st.info("No unresolved escalated cases.")
            else:
                st.error(f"Unable to load escalation queue: {escalation_response.text}")

            if st.session_state.admin_escalation_case:
                detail = st.session_state.admin_escalation_case
                queue_case = detail["queue"]
                stored = detail["analysis"]
                stored_analysis = stored.get("analysis") or {}
                st.markdown("### Escalated Case Detail")
                st.caption(
                    f"{queue_case.get('case_id')} | Escalated by: "
                    f"{queue_case.get('escalated_by') or 'Not available'} | "
                    f"{queue_case.get('escalated_at') or 'Not available'}"
                )
                detail_rows = {
                    "Intent": stored_analysis.get("intent"),
                    "Sentiment": stored_analysis.get("sentiment"),
                    "Urgency": stored_analysis.get("urgency"),
                    "Escalation Risk": stored_analysis.get("escalation_risk"),
                    "Key Issue": stored_analysis.get("key_issue"),
                    "Related Policy": stored_analysis.get("related_policy"),
                    "Conversation Context": stored_analysis.get("conversation_context"),
                    "Recommended Next Action": stored_analysis.get("recommended_next_action"),
                }
                st.dataframe(
                    [{"Field": field, "Stored value": value or "Not available"} for field, value in detail_rows.items()],
                    use_container_width=True,
                    hide_index=True,
                )
                st.markdown("**CBR metadata**")
                st.json(stored.get("cbr_metadata") or {})
                st.markdown("**Persisted conversation history**")
                for message in stored.get("messages", []):
                    st.write(f"{message.get('speaker', 'unknown')}: {message.get('text', '')}")
                if st.button("Close Escalated Case Detail", key="close_admin_escalation"):
                    st.session_state.admin_escalation_case = None
                    st.rerun()
            st.success("Administrator analytics loaded from PostgreSQL.")
        else:
            st.error(f"Unable to load administrator analytics: {analytics_response.text}")
    except requests.RequestException as error:
        st.error(f"Unable to reach the analytics service: {error}")
    st.stop()

def render_human_agent_console():
    """Render the compact operations console while reusing existing API contracts."""
    for key, default in {
        "agent_page": "Priority Queue",
        "queue_search": "",
        "queue_priority_filter": "All priorities",
        "queue_status_filter": "All statuses",
        "queue_department_filter": "All departments",
        "case_summary": "",
        "case_summary_case_id": None,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { background: #071426; border-right: 1px solid #123a68; }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.1rem; }
        .ops-brand { color: #e6f4ff; font-size: 1.25rem; font-weight: 800; letter-spacing: .02em; }
        .ops-subtitle { color: #64b9ec; font-size: .68rem; margin-top: -.25rem; }
        .ops-header { background: #0a172b; border: 1px solid #123a68; border-radius: 8px; padding: 13px 16px; }
        .ops-kicker { color: #74c7ff; font-size: .68rem; text-transform: uppercase; letter-spacing: .12em; font-weight: 700; }
        .ops-title { color: #f4f9ff; font-size: 1.35rem; font-weight: 800; margin-top: 2px; }
        .ops-caption { color: #84a1bd; font-size: .76rem; }
        .ops-card { background: #0b1a30; border: 1px solid #123a68; border-radius: 8px; padding: 12px; }
        .ops-card h4 { color: #dff2ff; margin: 0 0 8px 0; font-size: .82rem; }
        .ops-label { color: #81a4c6; font-size: .64rem; text-transform: uppercase; letter-spacing: .08em; }
        .ops-value { color: #edf7ff; font-size: .86rem; font-weight: 700; }
        .ops-chip { display: inline-block; border-radius: 4px; padding: 3px 7px; color: #fff; font-size: .66rem; font-weight: 800; }
        .ops-chip-critical { background: #a73550; }
        .ops-chip-high { background: #a45d1b; }
        .ops-chip-medium { background: #217a87; }
        .ops-chip-low { background: #236b55; }
        .ops-badge { display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: .68rem; font-weight: 700; letter-spacing: .02em; }
        .ops-badge-status { background: rgba(48, 214, 161, .12); color: #7ae8c4; border: 1px solid rgba(48, 214, 161, .4); }
        .ops-badge-priority { background: rgba(96, 165, 250, .12); color: #a8d4ff; border: 1px solid rgba(96, 165, 250, .4); }
        .ops-badge-department { background: rgba(167, 139, 250, .12); color: #d7c5ff; border: 1px solid rgba(167, 139, 250, .4); }
        .ops-badge-sentiment { background: rgba(251, 191, 36, .12); color: #f8d66b; border: 1px solid rgba(251, 191, 36, .35); }
        .ops-badge-risk { background: rgba(248, 113, 113, .12); color: #fca5a5; border: 1px solid rgba(248, 113, 113, .35); }
        .ops-badge-urgency { background: rgba(251, 146, 60, .12); color: #fdba74; border: 1px solid rgba(251, 146, 60, .35); }
        .ops-case { background: #0b1a30; border: 1px solid #174777; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
        .ops-case strong { color: #83cfff; }
        .ops-muted { color: #8ba5bf; font-size: .74rem; }
        .ops-message-customer { background: #0d2038; border-left: 3px solid #38a9e8; padding: 9px 11px; border-radius: 6px; margin: 6px 0; }
        .ops-message-agent { background: #102b39; border-left: 3px solid #35d0a4; padding: 9px 11px; border-radius: 6px; margin: 6px 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown('<div class="ops-brand">⚡ InfiSupport</div><div class="ops-subtitle">AI-Powered Customer Support</div>', unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("### 👥 Human Agent")
        page = st.radio(
            "Workspace",
            ["Priority Queue", "My Cases", "Knowledge Base"],
            index=["Priority Queue", "My Cases", "Knowledge Base"].index(st.session_state.agent_page),
            label_visibility="collapsed",
        )
        st.session_state.agent_page = page
        st.markdown("<div style='color:#30d6a1;font-size:.75rem;margin-top:2rem;'>● System Online</div>", unsafe_allow_html=True)
        if st.button("Sign out", key="agent_sidebar_logout", use_container_width=True):
            st.session_state.access_token = ""
            st.session_state.current_user = None
            st.rerun()

    if page == "Knowledge Base":
        st.markdown('<div class="ops-header"><div class="ops-kicker">Human Agent</div><div class="ops-title">Knowledge Base</div><div class="ops-caption">Policy references appear here after a customer message is analyzed.</div></div>', unsafe_allow_html=True)
        policy = (st.session_state.get("backend_data", {}).get("final_cbr_output", {}) or {}).get("related_policy")
        if policy:
            st.markdown(f"### {policy.get('topic', 'Policy')} <span class='ops-muted'>{policy.get('policy_id', '')}</span>", unsafe_allow_html=True)
            st.info(policy.get("text", "No policy text available."))
            st.caption(f"{policy.get('source', 'Policy source unavailable')} · Semantic similarity {float(policy.get('similarity_score', 0)):.1%}")
        else:
            st.info("No policy reference is available yet. Open a case and submit a customer message.")
        return

    queue = st.session_state.priority_queue
    if not st.session_state.priority_queue_loaded or st.button("Refresh", key="agent_refresh_queue"):
        try:
            queue_response = get_from_backend("/api/cases/active", timeout=180)
            if queue_response.status_code == 200:
                queue = queue_response.json().get("cases", [])
                st.session_state.priority_queue = queue
                st.session_state.priority_queue_error = ""
                st.session_state.priority_queue_loaded = True
            else:
                st.session_state.priority_queue_error = f"Backend returned {queue_response.status_code}: {queue_response.text}"
        except requests.RequestException as error:
            st.session_state.priority_queue_error = f"Unable to reach the priority queue service: {error}"

    if page == "My Cases":
        assigned_id = None
        with st.spinner("Loading assigned cases..."):
            queue = [case for case in queue if case.get("assigned_agent_id") == assigned_id] if assigned_id else queue

    st.markdown('<div class="ops-header"><div class="ops-kicker">Human Agent</div><div class="ops-title">Human Agent Priority Queue</div><div class="ops-caption">View and manage cases ordered by the existing backend priority score.</div></div>', unsafe_allow_html=True)
    action_left, action_right = st.columns([1, 1])
    with action_left:
        if st.button("＋ Create New Case", key="agent_create_case", use_container_width=True):
            st.session_state.new_case_mode = True
            st.session_state.active_case = None
            st.session_state.selected_queue_case = None
            st.session_state.backend_data = {}
            st.session_state.chat_history = []
            st.session_state.agent_draft = ""
            st.rerun()
    with action_right:
        st.caption(f"{len(queue)} active cases from the existing backend")

    search_col, priority_col, status_col, department_col = st.columns([2.2, 1, 1, 1])
    with search_col:
        st.session_state.queue_search = st.text_input("Search", value=st.session_state.queue_search, placeholder="Search case ID, customer, or issue", label_visibility="collapsed")
    priorities = ["All priorities"] + sorted({str(case.get("priority_label", "LOW")).title() for case in queue})
    statuses = ["All statuses"] + sorted({str(case.get("status", "UNKNOWN")).replace("_", " ").title() for case in queue})
    departments = ["All departments"] + sorted({str(case.get("department", "Unassigned")) for case in queue})
    with priority_col:
        st.session_state.queue_priority_filter = st.selectbox("Priority", priorities, index=min(priorities.index(st.session_state.queue_priority_filter) if st.session_state.queue_priority_filter in priorities else 0, len(priorities)-1), label_visibility="collapsed")
    with status_col:
        st.session_state.queue_status_filter = st.selectbox("Status", statuses, index=min(statuses.index(st.session_state.queue_status_filter) if st.session_state.queue_status_filter in statuses else 0, len(statuses)-1), label_visibility="collapsed")
    with department_col:
        st.session_state.queue_department_filter = st.selectbox("Department", departments, index=min(departments.index(st.session_state.queue_department_filter) if st.session_state.queue_department_filter in departments else 0, len(departments)-1), label_visibility="collapsed")

    search_value = st.session_state.queue_search.lower().strip()
    filtered_queue = []
    for case in queue:
        analysis = case.get("latest_analysis") or {}
        haystack = " ".join(str(value or "") for value in (case.get("case_id"), case.get("customer_id"), case.get("key_issue"), analysis.get("customer_intent"))).lower()
        if search_value and search_value not in haystack:
            continue
        if st.session_state.queue_priority_filter != "All priorities" and str(case.get("priority_label", "")).title() != st.session_state.queue_priority_filter:
            continue
        if st.session_state.queue_status_filter != "All statuses" and str(case.get("status", "")).replace("_", " ").title() != st.session_state.queue_status_filter:
            continue
        if st.session_state.queue_department_filter != "All departments" and str(case.get("department", "Unassigned")) != st.session_state.queue_department_filter:
            continue
        filtered_queue.append(case)

    if st.session_state.priority_queue_error:
        st.error(st.session_state.priority_queue_error)
    elif not filtered_queue:
        st.info("No active cases match the current filters.")
    else:
        rows = []
        for rank, case in enumerate(filtered_queue, 1):
            analysis = case.get("latest_analysis") or {}
            factors = case.get("priority_factors") or {}
            waiting_minutes = float(factors.get("waiting_minutes", 0) or 0)
            priority = str(case.get("priority_label", "LOW")).lower()
            rows.append({
                "#": rank,
                "Customer": case.get("customer_id", "Unavailable"),
                "Case ID": case.get("case_id", "Unavailable"),
                "Priority": priority.upper(),
                "Priority Score": case.get("priority_score", "Unavailable"),
                "Sentiment": analysis.get("sentiment", "Unavailable"),
                "Risk": str(analysis.get("escalation_risk", "Unavailable")).upper(),
                "Urgency": str(analysis.get("urgency", "Unavailable")).upper(),
                "Intent": analysis.get("customer_intent", "Unavailable"),
                "Waiting": f"{int(waiting_minutes // 60)}h {int(waiting_minutes % 60)}m",
                "Status": str(case.get("status", "Unavailable")).replace("_", " "),
                "Department": case.get("department", "Unassigned"),
            })
            with st.container(border=True):
                cells = st.columns([.25, 1.1, 1.3, .65, .65, .8, .65, .65, 1.2, .7, .85, .8, .5])
                values = list(rows[-1].values())
                for cell, value in zip(cells[:-1], values):
                    cell.caption(str(value))
                if cells[-1].button("Open", key=f"agent_open_{case.get('case_id')}"):
                    full_case_response = get_from_backend(f"/api/cases/{case.get('customer_id')}/{case.get('case_id')}", timeout=120)
                    if full_case_response.status_code == 200:
                        full_case = full_case_response.json()
                        analysis_response = get_from_backend(f"/api/cases/{case.get('customer_id')}/{case.get('case_id')}/analysis", timeout=120)
                        stored = analysis_response.json() if analysis_response.status_code == 200 else {}
                        st.session_state.active_case = full_case
                        st.session_state.selected_queue_case = full_case
                        st.session_state.customer_id = full_case.get("customer_id")
                        st.session_state.case_id = full_case.get("case_id")
                        st.session_state.backend_data = {
                            "support_case": full_case,
                            "final_cbr_output": stored.get("analysis", {}),
                            "retrieved_cases": stored.get("cbr_metadata", {}).get("matched_case_ids", []),
                            "retrieved_policies": [],
                            "cbr_metadata": stored.get("cbr_metadata", {}),
                        }
                        st.session_state.chat_history = [{"speaker": "Customer" if message.get("speaker") == "customer" else "Agent", "text": message.get("text", ""), "time": message.get("timestamp", "")[-8:-3]} for message in full_case.get("messages", [])]
                        st.session_state.case_summary = ""
                        st.rerun()
                    else:
                        st.error(f"Unable to open case: {full_case_response.text}")

    if st.session_state.new_case_mode and not st.session_state.active_case:
        st.markdown('<div class="ops-header"><div class="ops-kicker">New Customer Case</div><div class="ops-title">Create New Case</div><div class="ops-caption">Enter the customer details, then run the existing AI analysis workflow.</div></div>', unsafe_allow_html=True)
        with st.form("new_customer_case_form"):
            customer_name = st.text_input("Customer Name", key="new_customer_name")
            customer_email = st.text_input("Customer Email", key="new_customer_email")
            customer_language = st.selectbox("Customer Language", ["en", "hi", "ta"], key="new_customer_language")
            customer_message = st.text_area("Customer Message", height=180, key="new_customer_message")
            analyze_submitted = st.form_submit_button("Analyze Customer Message", type="primary")
        if analyze_submitted:
            if not customer_message.strip():
                st.error("Enter a customer message before analyzing.")
            else:
                customer_id, case_id = generate_new_case_ids()
                response = post_to_backend(
                    "/api/tickets/process-text",
                    json={
                        "query": customer_message,
                        "customer_id": customer_id,
                        "case_id": case_id,
                        "language": customer_language,
                    },
                    timeout=180,
                )
                if response.status_code == 200:
                    data = response.json()
                    support_case = data.get("support_case") or {}
                    support_case["customer_name"] = customer_name or "—"
                    support_case["customer_email"] = customer_email or "—"
                    st.session_state.customer_id = customer_id
                    st.session_state.case_id = case_id
                    st.session_state.active_case = support_case
                    st.session_state.selected_queue_case = support_case
                    st.session_state.backend_data = data
                    st.session_state.chat_history = [{"speaker": "Customer", "text": customer_message, "time": datetime.now().strftime("%H:%M")}]
                    st.session_state.customer_input_text = customer_message
                    st.session_state.agent_draft = (data.get("final_cbr_output") or {}).get("drafted_response", "")
                    st.session_state.new_case_mode = False
                    st.rerun()
                else:
                    st.error(f"Unable to analyze customer message: {response.text}")
        return

    if not st.session_state.active_case:
        return

    selected_case = st.session_state.active_case
    if st.button("← Back to Queue", key="agent_back_queue"):
        st.session_state.active_case = None
        st.session_state.selected_queue_case = None
        st.session_state.backend_data = {}
        st.rerun()
    analysis = ((st.session_state.backend_data.get("final_cbr_output") or {}) if st.session_state.get("backend_data") else {})
    cbr_metadata = (st.session_state.backend_data.get("cbr_metadata") or {}) if st.session_state.get("backend_data") else {}
    fallback_retrieved_cases = st.session_state.backend_data.get("retrieved_cases", []) if st.session_state.get("backend_data") else []
    retrieved_cases = []
    if isinstance(fallback_retrieved_cases, list):
        retrieved_cases = [case for case in fallback_retrieved_cases if case]
    if not retrieved_cases and cbr_metadata.get("matched_case_ids"):
        retrieved_cases = [
            {"case_id": case_id, "match_type": cbr_metadata.get("cbr_match_type", "matched")}
            for case_id in cbr_metadata.get("matched_case_ids", [])
            if has_value(case_id)
        ]
    policy = analysis.get("related_policy") or (st.session_state.backend_data.get("retrieved_policies") or [None])[0]
    st.markdown('<div class="ops-header"><div class="ops-kicker">Case Workspace</div><div class="ops-title">{}</div><div class="ops-caption">{} · {} · Created {}</div></div>'.format(selected_case.get("case_id", "Case"), selected_case.get("department", "Unassigned"), selected_case.get("status", "Unknown"), selected_case.get("created_at", "Unavailable")), unsafe_allow_html=True)
    left_col, center_col, right_col = st.columns([1.1, 1.8, 1.2], gap="medium")
    with left_col:
        st.markdown("### Case Overview")
        overview_values = [
            ("Case ID", selected_case.get("case_id")),
            ("Customer", selected_case.get("customer_name") or selected_case.get("customer_id")),
            ("Email", selected_case.get("customer_email")),
            ("Category", analysis.get("selected_category") or analysis.get("intent")),
            ("Intent", analysis.get("customer_intent") or analysis.get("intent")),
            ("Department", selected_case.get("department")),
            ("Status", selected_case.get("status")),
            ("Priority", selected_case.get("priority_label")),
            ("Priority Score", selected_case.get("priority_score")),
            ("Assigned Agent", selected_case.get("assigned_agent")),
            ("Created", selected_case.get("created_at")),
            ("Waiting", (selected_case.get("priority_factors") or {}).get("waiting_minutes")),
        ]
        for label, value in overview_values:
            if has_value(value):
                badge_classes = {
                    "Status": "ops-badge ops-badge-status",
                    "Priority": "ops-badge ops-badge-priority",
                    "Department": "ops-badge ops-badge-department",
                }
                value_html = value
                if label in badge_classes:
                    value_html = f'<span class="{badge_classes[label]}">{value}</span>'
                st.markdown(f'<div class="ops-label">{label}</div><div class="ops-value">{value_html}</div>', unsafe_allow_html=True)

        quality_rows = []
        feedback = (st.session_state.get("feedback") or analysis.get("feedback") or {})
        for label, value_key in (("Tone", "tone_score"), ("Empathy", "empathy_score"), ("Clarity", "clarity_score")):
            if has_value(feedback.get(value_key)):
                quality_rows.append((label, feedback.get(value_key)))
        if quality_rows:
            st.markdown("### AI Response Score")
            score_cols = st.columns(min(3, len(quality_rows)))
            for idx, (label, value) in enumerate(quality_rows):
                value_text = f"{value}/10"
                score_cols[idx % len(score_cols)].metric(label, value_text)

        coaching_tip = ((st.session_state.get("feedback") or analysis.get("feedback") or {}).get("coaching_tip"))
        if coaching_tip:
            st.markdown(
                f"<div class='coaching-box'><b>💡 AI Coaching Tip:</b><br>{coaching_tip}</div>",
                unsafe_allow_html=True,
            )

    with center_col:
        st.markdown("### AI Case Analysis")
        analysis_rows = [
            ("Intent", analysis.get("customer_intent") or analysis.get("intent")),
            ("Sentiment", analysis.get("sentiment")),
            ("Risk", analysis.get("escalation_risk")),
            ("Urgency", analysis.get("urgency")),
            ("Key Issue", analysis.get("key_issue")),
            ("Extracted Context", analysis.get("conversation_context")),
            ("Suggested Next Step", analysis.get("recommended_next_step") or analysis.get("recommended_next_action")),
        ]
        for label, value in analysis_rows:
            if has_value(value):
                badge_classes = {
                    "Sentiment": "ops-badge ops-badge-sentiment",
                    "Risk": "ops-badge ops-badge-risk",
                    "Urgency": "ops-badge ops-badge-urgency",
                }
                value_html = value
                if label in badge_classes:
                    value_html = f'<span class="{badge_classes[label]}">{value}</span>'
                st.markdown(f'<div class="ops-label">{label}</div><div class="ops-value">{value_html}</div>', unsafe_allow_html=True)

        if analysis.get("synthesized_strategy"):
            st.markdown("### Resolution Strategy")
            st.info(analysis.get("synthesized_strategy"))

        st.markdown("### Customer Conversation")
        messages = selected_case.get("messages", []) or []
        for message in messages:
            speaker = message.get("speaker", "unknown")
            css_class = "ops-message-customer" if speaker == "customer" else "ops-message-agent"
            text = message.get("text", "")
            if has_value(text):
                st.markdown(f'<div class="{css_class}"><b>{speaker.replace("_", " ").title()}</b><br>{text}</div>', unsafe_allow_html=True)

        draft = st.text_area("Suggested Response", value=st.session_state.agent_draft or "", height=120, key="agent_workspace_draft")
        st.session_state.agent_draft = draft
        send_col, resolve_col = st.columns(2)
        with send_col:
            if st.button("Send", key="agent_send", use_container_width=True) and draft.strip():
                response = post_to_backend(f"/api/cases/{selected_case.get('customer_id')}/{selected_case.get('case_id')}/messages", json={"message": draft}, timeout=60)
                if response.status_code == 200:
                    st.session_state.agent_draft = ""
                    st.rerun()
                else:
                    st.error(response.text)
        with resolve_col:
            if st.button("Resolve", key="agent_resolve", use_container_width=True):
                response = requests.patch(f"{BACKEND_URL}/api/cases/{selected_case.get('customer_id')}/{selected_case.get('case_id')}/status", headers={"Authorization": f"Bearer {st.session_state.access_token}"}, json={"status": "RESOLVED", "resolution_summary": draft or None}, timeout=120)
                if response.status_code == 200:
                    st.session_state.active_case = response.json()
                    st.rerun()
                else:
                    st.error(response.text)

    with right_col:
        st.markdown("### CBR Recommendations")
        if retrieved_cases:
            for historical in retrieved_cases[:3]:
                if isinstance(historical, dict):
                    case_id = historical.get("case_id")
                    issue = historical.get("issue_description") or historical.get("key_issue")
                    resolution = historical.get("resolution_strategy") or historical.get("agent_action")
                    suggested_reply = historical.get("recommended_reply")
                    similarity = historical.get("normalized_similarity")
                    match_type = historical.get("match_type") or cbr_metadata.get("cbr_match_type")
                else:
                    case_id = historical
                    issue = None
                    resolution = None
                    suggested_reply = None
                    similarity = cbr_metadata.get("cbr_similarity_score")
                    match_type = cbr_metadata.get("cbr_match_type")
                if not has_value(case_id):
                    continue
                similarity_text = format_similarity(similarity)
                st.markdown(
                    f'<div class="ops-case"><strong>{case_id}</strong>{"<br><span class=\"ops-muted\">" + (match_type or "Matched") + (" · Similarity " + similarity_text if similarity_text else "") + "</span>" if has_value(match_type) or similarity_text else ""}{"<p>" + (issue or "Stored historical case reference") + "</p>" if has_value(issue) else ""}{"<p class=\"ops-muted\">Resolution: " + (resolution or "Stored historical resolution") + "</p>" if has_value(resolution) else ""}{"<p class=\"ops-muted\">Suggested response: " + suggested_reply + "</p>" if has_value(suggested_reply) else ""}</div>',
                    unsafe_allow_html=True,
                )
                if has_value(case_id) and st.button("Use", key=f"workspace_use_{case_id}"):
                    response = post_to_backend(f"/api/cases/{selected_case.get('customer_id')}/{selected_case.get('case_id')}/use-historical-case", json={"historical_case_id": case_id}, timeout=180)
                    if response.status_code == 200:
                        generated = response.json()
                        generated["retrieved_cases"] = retrieved_cases
                        generated["cbr_metadata"] = cbr_metadata
                        st.session_state.backend_data = generated
                        st.session_state.agent_draft = (generated.get("final_cbr_output") or {}).get("drafted_response", "")
                        st.rerun()
                    else:
                        st.error(response.text)
        else:
            st.info("No strong similar resolved cases found.")

        st.markdown("### Policy References")
        if policy:
            policy_topic = policy.get("topic") or "Policy"
            policy_id = policy.get("policy_id")
            st.markdown(f"**{policy_topic}**" + (f" · {policy_id}" if has_value(policy_id) else ""))
            if has_value(policy.get("source")):
                st.caption(policy.get("source"))
            similarity_text = format_similarity(policy.get("similarity_score"))
            if similarity_text:
                st.caption(f"Semantic similarity {similarity_text}")
            if has_value(policy.get("text")):
                st.write(policy.get("text"))
        else:
            st.info("No policy reference available.")

    action_col, escalate_col = st.columns(2)
    with action_col:
        if st.button("Summarise Case", key="workspace_summarise"):
            response = post_to_backend(f"/api/cases/{selected_case.get('customer_id')}/{selected_case.get('case_id')}/summary", timeout=180)
            if response.status_code == 200:
                st.session_state.case_summary = response.json().get("summary", "")
                st.session_state.case_summary_case_id = selected_case.get("case_id")
                st.rerun()
            else:
                st.error(response.text)
        if st.session_state.get("case_summary") and st.session_state.get("case_summary_case_id") == selected_case.get("case_id"):
            st.info(st.session_state.case_summary)
            summary_text = json.dumps(st.session_state.case_summary)
            components.html(f"<button onclick='navigator.clipboard.writeText({summary_text})'>Copy summary</button>", height=40)
    with escalate_col:
        if selected_case.get("escalation_status") == "ESCALATED":
            st.warning(f"Escalated: {selected_case.get('escalation_reason') or 'Reason unavailable'}")
        else:
            with st.form("workspace_escalation_form"):
                department_options = ["Accounts", "Support"]
                current_department = selected_case.get("department") or "Support"
                department_index = department_options.index(current_department) if current_department in department_options else 0
                department = st.selectbox("Escalate to department", department_options, index=department_index)
                reason = st.selectbox("Escalation reason", ["Customer frustration / unresolved issue", "Repeated failed resolution", "Requires manager intervention", "Policy exception required", "Other"])
                details = st.text_input("Details")
                if st.form_submit_button("Escalate Case"):
                    try:
                        if department != (selected_case.get("department") or "Support"):
                            transfer_response = post_to_backend(
                                f"/api/cases/{selected_case.get('customer_id')}/{selected_case.get('case_id')}/transfer",
                                json={"department": department},
                                timeout=120,
                            )
                            if transfer_response.status_code != 200:
                                st.error(f"Unable to transfer case to {department}: {transfer_response.text}")
                                st.stop()
                        response = post_to_backend(
                            f"/api/cases/{selected_case.get('customer_id')}/{selected_case.get('case_id')}/escalate",
                            json={"reason": reason, "details": details or None},
                            timeout=120,
                        )
                        if response.status_code == 200:
                            st.session_state.active_case = response.json()
                            st.rerun()
                        else:
                            st.error(response.text)
                    except requests.RequestException as error:
                        st.error(f"Unable to reach the escalation service: {error}")


render_human_agent_console()
st.stop()


def render_priority_queue():
    st.subheader("👥 Human Agent Priority Queue")
    queue_col, status_col = st.columns([1, 4])
    with queue_col:
        refresh_queue = st.button("🔄 Refresh Queue", use_container_width=True)

    if refresh_queue or not st.session_state.priority_queue_loaded:
        try:
            queue_response = get_from_backend("/api/cases/active", timeout=180)
            if queue_response.status_code == 200:
                st.session_state.priority_queue = [
                    case for case in queue_response.json().get("cases", [])
                    if case.get("status") != "RESOLVED"
                ]
                st.session_state.priority_queue_error = ""
                st.session_state.priority_queue_loaded = True
            else:
                st.session_state.priority_queue = []
                st.session_state.priority_queue_error = f"Backend returned {queue_response.status_code}: {queue_response.text}"
                st.session_state.priority_queue_loaded = True
        except requests.RequestException as error:
            st.session_state.priority_queue = []
            st.session_state.priority_queue_error = f"Unable to reach the priority queue service: {error}"
            st.session_state.priority_queue_loaded = True

    with status_col:
        st.caption("Active unresolved cases ordered by the backend priority score.")

    if st.session_state.priority_queue_error:
        st.error(f"Unable to load priority queue: {st.session_state.priority_queue_error}")
    elif st.session_state.priority_queue:
        table_widths = [0.35, 0.9, 0.9, 0.65, 0.6, 0.7, 0.75, 0.8, 1.5, 0.75, 0.65, 0.7]
        table_header = st.columns(table_widths)
        for header, column in zip(
            table_header,
            ["#", "Customer", "Case", "Priority", "Score", "Sentiment", "Risk", "Urgency", "Intent", "Waiting", "Status", "Action"],
        ):
            header.markdown(f"**{column}**")

        for rank, case in enumerate(st.session_state.priority_queue, start=1):
            analysis = case.get("latest_analysis") or {}
            factors = case.get("priority_factors") or {}
            waiting_minutes = factors.get("waiting_minutes", 0)
            waiting_hours = int(waiting_minutes // 60)
            waiting_remaining_minutes = int(waiting_minutes % 60)
            waiting_time = f"{waiting_hours}h {waiting_remaining_minutes}m"
            row = st.columns(table_widths)
            row[0].write(rank)
            row[1].write(case.get("customer_id", "Unknown"))
            row[2].write(case.get("case_id", "Unknown"))
            row[3].write(case.get("priority_label", "LOW"))
            row[4].write(case.get("priority_score", 0))
            row[5].write(analysis.get("sentiment", "--"))
            row[6].write(str(analysis.get("escalation_risk", "--")).upper())
            row[7].write(str(analysis.get("urgency", "--")).upper())
            row[8].write(analysis.get("customer_intent", "--"))
            row[9].write(waiting_time)
            row[10].write(case.get("status", "--"))
            if row[11].button("Open", key=f"open_case_{case.get('customer_id')}_{case.get('case_id')}"):
                st.session_state.selected_queue_case = case
                st.session_state.active_case = case
                st.session_state.new_case_mode = False
                selected_messages = case.get("messages") or []
                selected_query = selected_messages[-1].get("text", "") if selected_messages else "Review this customer case."
                selected_output = dict(analysis)
                selected_output.setdefault("selected_category", "General Support")
                selected_output.setdefault("synthesized_strategy", selected_output.get("recommended_next_step", "Review the case and provide the next resolution step."))
                selected_output.setdefault("drafted_response", "I understand your concern and will review this case immediately, then provide a clear next step.")
                selected_output.setdefault("sentiment_score", 2 if str(selected_output.get("sentiment", "")).lower() == "negative" else 4)
                selected_output.setdefault("urgency_score", {"critical": 5, "high": 4, "medium": 3, "low": 1}.get(str(selected_output.get("urgency", "")).lower(), 3))
                st.session_state.backend_data = {
                    "query": selected_query,
                    "customer_id": case.get("customer_id"),
                    "case_id": case.get("case_id"),
                    "final_cbr_output": selected_output,
                    "retrieved_cases": [],
                    "retrieved_policies": [],
                    "cbr_metadata": {},
                }
                st.session_state.customer_id = case.get("customer_id", st.session_state.customer_id)
                st.session_state.case_id = case.get("case_id", st.session_state.case_id)
                st.session_state.customer_input_text = selected_query
                st.session_state.case_brief = None
                st.session_state.case_brief_case_id = None
                st.session_state.chat_history = [
                    {
                        "speaker": "Customer" if message.get("speaker") == "customer" else "Agent",
                        "text": message.get("text", ""),
                        "time": message.get("timestamp", "")[-8:-3],
                    }
                    for message in selected_messages
                ]
                st.session_state.feedback = {
                    "tone_score": selected_output.get("tone_score"),
                    "empathy_score": selected_output.get("empathy_score"),
                    "clarity_score": selected_output.get("clarity_score"),
                    "coaching_tip": selected_output.get("coaching_tip"),
                }
                st.rerun()
        st.caption("Click Open in any row to view that customer's complete case detail.")
    else:
        st.info("No active unresolved customers are currently in the priority queue.")


if st.session_state.active_case:
    if st.button("← Back to Priority Queue", use_container_width=False):
        st.session_state.active_case = None
        st.session_state.selected_queue_case = None
        st.session_state.new_case_mode = False
        st.session_state.customer_id = None
        st.session_state.case_id = None
        st.rerun()
    selected_case = st.session_state.active_case
else:
    render_priority_queue()
    if not st.session_state.selected_queue_case:
        st.info("Select an existing case from the priority queue, or start a new customer case.")
        if st.button("Start New Customer Case", type="primary"):
            customer_id, case_id = generate_new_case_ids()
            st.session_state.customer_id = customer_id
            st.session_state.case_id = case_id
            st.session_state.new_case_mode = True
            st.session_state.active_case = {
                "customer_id": customer_id,
                "case_id": case_id,
                "status": "NEW",
                "latest_analysis": {},
                "messages": [],
            }
            st.session_state.backend_data = {}
            st.session_state.chat_history = []
            st.session_state.agent_draft = ""
            st.session_state.case_summary = ""
            st.session_state.case_brief = None
            st.session_state.case_brief_case_id = None
            st.rerun()
        st.stop()
    selected_case = st.session_state.selected_queue_case

selected_analysis = selected_case.get("latest_analysis") or {}

if st.session_state.case_brief_case_id != st.session_state.case_id:
    try:
        brief_response = get_from_backend(
            f"/api/cases/{st.session_state.customer_id}/{st.session_state.case_id}/brief",
            timeout=60,
        )
        if brief_response.status_code == 200:
            st.session_state.case_brief = brief_response.json()
            st.session_state.case_brief_case_id = st.session_state.case_id
    except requests.RequestException:
        pass

st.markdown("---")
st.subheader("🗂️ Case Workspace")
workspace_customer, workspace_case, workspace_priority, workspace_status = st.columns(4)
workspace_customer.metric("Customer", selected_case.get("customer_id", "Unknown"))
workspace_case.metric("Case", selected_case.get("case_id", "Unknown"))
workspace_priority.metric("Priority", selected_case.get("priority_label", "LOW"))
workspace_status.metric("Status", selected_case.get("status", "UNKNOWN"))
st.caption(
    f"Reviewing {selected_case.get('customer_id', 'this customer')}: "
    f"{selected_analysis.get('selected_category', 'Support case')}"
)
if selected_case.get("assigned_agent"):
    st.caption(f"Assigned agent: {selected_case['assigned_agent']['name']} ({selected_case['assigned_agent']['email']})")
if selected_case.get("department"):
    st.caption(f"Department: {selected_case['department']}")

if st.session_state.case_brief:
    st.markdown("### Agent Briefing")
    st.caption(f"Detected customer language: {st.session_state.case_brief['detected_language']}")
    st.caption("Short English brief: customer request and generated response")
    st.info(st.session_state.case_brief["briefing"])
    briefing_text = json.dumps(st.session_state.case_brief["briefing"])
    components.html(
        f"""
        <button onclick='speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance({briefing_text}))'>
            🔊 Listen to Case Brief
        </button>
        """,
        height=42,
    )

case_risk = str(selected_analysis.get("escalation_risk", "")).lower()
if case_risk in {"high", "critical"} or selected_case.get("ai_escalation"):
    if st.button("📝 Summarise Case", use_container_width=False):
        try:
            summary_response = post_to_backend(
                f"/api/cases/{st.session_state.customer_id}/{st.session_state.case_id}/summarize",
                timeout=120,
            )
            if summary_response.status_code == 200:
                st.session_state.case_summary = summary_response.json().get("summary", "")
            else:
                st.error(f"Unable to summarise case: {summary_response.text}")
        except requests.RequestException as error:
            st.error(f"Unable to reach the summary service: {error}")
    if st.session_state.get("case_summary"):
        st.markdown("### Escalation Summary")
        st.info(st.session_state.case_summary)

col1, col2, col3 = st.columns([1.1, 1.2, 1.1], gap="medium")

# ==================== COLUMN 1 ====================
with col1:
    st.subheader("👤 Customer Signal Feed")
    st.markdown("""
    <div class="vip-card">
        <b>John Doe <span style="color: #F59E0B; font-size: 0.8rem;">(VIP Tier)</span></b><br>
        <span style="color: #94A3B8; font-size: 0.8rem;">Order #ORD-98231 • Pro Laptop 16"</span>
    </div>
    """, unsafe_allow_html=True)

    customer_id = st.session_state.customer_id
    case_id = st.session_state.case_id
    if st.session_state.new_case_mode:
        st.info("New customer case. IDs were generated automatically.")
    else:
        st.caption("Existing selected case. New messages stay on this case.")
    st.text(f"Customer ID: {customer_id}")
    st.text(f"Case ID: {case_id}")
    st.caption("Customer can type in English, Hindi, or Tamil. The response language is detected automatically.")

    st.caption("Quick Scenario Triggers:")
    s1, s2, s3, s4 = st.columns(4)
    if s1.button("🚚 Delay", use_container_width=True):
        st.session_state.customer_input_text = "I am extremely disappointed. I paid over $1,200 for this high-performance laptop and it still hasn't arrived. I have already contacted support twice!"
        st.rerun()
    if s2.button("💸 Refund", use_container_width=True):
        st.session_state.customer_input_text = "My order was canceled three days ago but I still do not see the $1,200 refund in my bank account. Where is my money?"
        st.rerun()
    if s3.button("⚙️ Tech", use_container_width=True):
        st.session_state.customer_input_text = "The laptop arrived today, but it won't connect to my Wi-Fi network and keeps freezing on setup."
        st.rerun()
    if s4.button("😡 Complaint", use_container_width=True):
        st.session_state.customer_input_text = "This customer service experience is completely unacceptable. Connect me to a manager right now!"
        st.rerun()

    customer_input = st.text_area("Inbound Message Feed", value=st.session_state.customer_input_text, height=90)
    st.session_state.customer_input_text = customer_input

    if st.button("Get Response", type="primary", use_container_width=True):
        with st.status("Checking previous resolved cases...", expanded=True) as processing_status:
            st.write("Checking previous resolved cases...")
            try:
                # Target exact FastAPI text processing endpoint
                res = post_to_backend(
                    "/api/tickets/process-text",
                    json={
                        "query": customer_input,
                        "customer_id": customer_id or None,
                        "case_id": case_id or None,
                    },
                    timeout=120
                )
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.backend_data = data
                    st.session_state.active_case = data.get("support_case")
                    st.session_state.new_case_mode = False
                    queue_response = get_from_backend("/api/cases/active", timeout=180)
                    if queue_response.status_code == 200:
                        st.session_state.priority_queue = [
                            case for case in queue_response.json().get("cases", [])
                            if case.get("status") != "RESOLVED"
                        ]
                        st.session_state.priority_queue_error = ""
                        st.session_state.priority_queue_loaded = True
                    else:
                        st.session_state.priority_queue_loaded = False
                    
                    st.session_state.chat_history.append({
                        "speaker": "Customer", 
                        "text": customer_input, 
                        "time": datetime.now().strftime("%H:%M")
                    })
                    
                    cbr_out = data.get("final_cbr_output", {})
                    if cbr_out.get("drafted_response"):
                        st.session_state.agent_draft = cbr_out["drafted_response"]
                    
                    processing_status.update(label="Response ready", state="complete", expanded=False)
                    st.rerun()
                else:
                    processing_status.update(label="Unable to generate response", state="error")
                    st.error(f"Backend API Error: {res.text}")
            except Exception as e:
                processing_status.update(label="Unable to reach response service", state="error")
                st.error(f"Failed to reach FastAPI backend: {e}")

    st.markdown("### 💬 Live Transcript")
    chat_box = st.container(height=220)
    with chat_box:
        for item in st.session_state.chat_history:
            if item["speaker"] == "Customer":
                st.markdown(f'<div class="chat-bubble-user"><b>John Doe</b> <span style="font-size:0.7rem; color:#94A3B8;">• {item["time"]}</span><br>{item["text"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-bubble-agent"><b>Sarah Connor (Agent)</b> <span style="font-size:0.7rem; color:#94A3B8;">• {item["time"]}</span><br>{item["text"]}</div>', unsafe_allow_html=True)

# ==================== COLUMN 2 ====================
with col2:
    tab1, tab2 = st.tabs(["🚀 Copilot", "🔍 Policy Search"])

    with tab1:
        st.subheader("Real-Time Risk Matrix")
        if "backend_data" in st.session_state:
            cbr_out = st.session_state.backend_data.get("final_cbr_output", {})

            cbr_match_type = cbr_out.get("cbr_match_type", "none")
            cbr_similarity = float(cbr_out.get("cbr_similarity_score", 0) or 0)
            cbr_source_case = cbr_out.get("cbr_source_case_id")
            cbr_response_reused = bool(cbr_out.get("cbr_response_reused", False))
            cbr_ai_avoided = bool(cbr_out.get("ai_call_avoided", False))
            st.markdown("### Response Path")
            st.caption("Previous resolved cases are checked automatically before response generation.")
            if cbr_match_type in {"strong", "similar"}:
                st.success("Similar resolved case found")
                st.write(f"Similarity: {cbr_similarity:.0%}")
                if cbr_source_case:
                    st.caption(f"Source case: {cbr_source_case}")
                st.write("Historical response shown as supporting context")
                st.write("Existing AI analysis and response generation remain active")
            else:
                st.info("No sufficiently similar resolved case found")
                st.write("Generating a response from the existing AI analysis...")
            if cbr_match_type in {"strong", "similar"}:
                st.caption("Response source: existing AI generation with CBR support")
            else:
                st.caption("Response source: New AI generation")
            
            category = cbr_out.get("selected_category", "General Support")
            risk = cbr_out.get("escalation_risk", "low").upper()
            sentiment = cbr_out.get("sentiment", "--")
            urgency = cbr_out.get("urgency", "--")
            customer_intent = cbr_out.get("customer_intent", "--")
            next_step = cbr_out.get("recommended_next_step", "--")
            sentiment_emoji = {"Negative": "😟", "Neutral": "😐", "Positive": "😊"}.get(sentiment, "❔")
            risk_score = {"CRITICAL": 1.0, "HIGH": 0.75, "MEDIUM": 0.5, "LOW": 0.25}.get(risk, 0.25)
            urgency_score = cbr_out.get("urgency_score", {"Critical": 5, "High": 4, "Medium": 3, "Low": 1}.get(urgency, 1))
            
            r1, r2, r3, r4 = st.columns(4)
            r1.markdown(f'<div class="risk-card"><div class="risk-title">Category</div><div class="risk-val" style="color:#818CF8;">{category}</div></div>', unsafe_allow_html=True)
            r2.markdown(f'<div class="risk-card"><div class="risk-title">Escalation Risk</div><div class="risk-val">{risk}</div></div>', unsafe_allow_html=True)
            r3.markdown(f'<div class="risk-card"><div class="risk-title">Sentiment</div><div class="risk-val" style="color:#F59E0B;">{sentiment_emoji} {sentiment}</div></div>', unsafe_allow_html=True)
            r4.markdown(f'<div class="risk-card"><div class="risk-title">Urgency</div><div class="risk-val" style="color:#FB7185;">{urgency}</div></div>', unsafe_allow_html=True)

            visual_col_1, visual_col_2 = st.columns(2)
            with visual_col_1:
                st.caption(f"Escalation risk level: {risk}")
                st.progress(risk_score)
            with visual_col_2:
                st.caption(f"Urgency level: {urgency} ({urgency_score}/5)")
                st.progress(min(float(urgency_score) / 5, 1.0))

            st.markdown(f'<div class="ai-guidance-box"><b style="color:#A5B4FC;">CUSTOMER SIGNAL</b><p style="margin:6px 0 0; font-size:0.85rem;"><b>Intent:</b> {customer_intent}<br><b>Recommended next step:</b> {next_step}</p></div>', unsafe_allow_html=True)

            st.markdown("**Intent analysis**")
            st.info(f"{sentiment_emoji} The customer is **{customer_intent.lower()}**. Recommended action: {next_step}")

            strategy = cbr_out.get("synthesized_strategy", "")
            sug = cbr_out.get("drafted_response", "")
            related_policy = cbr_out.get("related_policy")

            if related_policy:
                st.markdown(
                    f"**Related policy: {related_policy.get('topic', 'Not available')}**  \n"
                    f"{related_policy.get('text', 'Not available')}  \n"
                    f"Source: {related_policy.get('source', 'Not available')} "
                    f"({float(related_policy.get('similarity_score', 0)):.0%})"
                )

            st.markdown("<br>", unsafe_allow_html=True)
            if strategy:
                st.markdown(f'<div class="ai-guidance-box"><b style="color:#A5B4FC;">CBR STRATEGY SYNTHESIS</b><p style="margin-top:4px; font-size:0.85rem; color:#E2E8F0;">{strategy}</p></div>', unsafe_allow_html=True)

            if sug:
                st.markdown(f'<div class="ai-guidance-box"><b style="color:#A5B4FC;">CUSTOMER RESPONSE</b><p style="margin-top:6px; color:#F1F5F9;">"{sug}"</p></div>', unsafe_allow_html=True)
                if st.button("➡️ Insert AI Suggestion to Workspace", use_container_width=True):
                    try:
                        post_to_backend(
                            f"/api/cases/{st.session_state.customer_id}/{st.session_state.case_id}/events",
                            json={
                                "event_type": "AI_RECOMMENDATION_USED",
                                "event_details": {"recommendation": sug},
                            },
                            timeout=30,
                        )
                    except requests.RequestException:
                        pass
                    st.session_state.agent_draft = sug
                    st.rerun()

        st.markdown("---")
        st.markdown("### ✍️ Agent Workspace")
        agent_draft_input = st.text_area("Agent Response Draft", value=st.session_state.agent_draft, height=90)
        st.session_state.agent_draft = agent_draft_input

        if st.button("Send Response & Update Transcript", type="primary", use_container_width=True):
            if agent_draft_input.strip():
                try:
                    response = post_to_backend(
                        f"/api/cases/{st.session_state.customer_id}/{st.session_state.case_id}/messages",
                        json={"message": agent_draft_input},
                        timeout=30,
                    )
                    if response.status_code == 200:
                        st.session_state.chat_history.append({
                            "speaker": "Agent",
                            "text": agent_draft_input,
                            "time": datetime.now().strftime("%H:%M"),
                        })
                        st.session_state.agent_draft = ""
                        st.session_state.feedback = st.session_state.get("feedback") or {
                            "tone_score": None,
                            "empathy_score": None,
                            "clarity_score": None,
                            "coaching_tip": None,
                        }
                        st.success("Draft submitted to customer!")
                        st.rerun()
                    else:
                        st.error(f"Backend API Error: {response.text}")
                except Exception as error:
                    st.error(f"Failed to save agent response: {error}")

    with tab2:
        st.subheader("🔍 Policy Search")
        policy = (st.session_state.get("backend_data", {}).get("final_cbr_output", {}) or {}).get("related_policy")
        if policy:
            st.markdown(
                f"**{policy.get('topic', 'Related policy')}**  "
                f"`{policy.get('policy_id', 'Policy ID unavailable')}`"
            )
            st.write(policy.get("text", "No related policy found."))
            st.caption(
                f"Source: {policy.get('source', 'Not available')} | "
                f"Semantic similarity: {float(policy.get('similarity_score', 0)):.1%}"
            )
        else:
            st.info("No related policy found.")

# ==================== COLUMN 3 ====================
with col3:
    st.subheader("📚 Relevant Resolved Cases")
    if "backend_data" in st.session_state:
        # Maps vector_db.py schema (ComplaintRecord: issue_description, resolution_strategy)
        cases = st.session_state.backend_data.get("retrieved_cases", [])
        if cases:
            unique_cases = []
            seen_case_content = set()
            for case in cases:
                content_key = (
                    case.get("issue_description") or case.get("key_issue", ""),
                    case.get("resolution_strategy") or case.get("agent_action", ""),
                    case.get("recommended_reply") or "",
                )
                if content_key not in seen_case_content:
                    seen_case_content.add(content_key)
                    unique_cases.append(case)
            if len(unique_cases) < len(cases):
                st.caption(
                    f"Showing {len(unique_cases)} unique historical case(s); "
                    f"{len(cases) - len(unique_cases)} duplicate record(s) were grouped."
                )
            for c in unique_cases:
                score_val = c.get("normalized_similarity")
                score_pct = f"{float(score_val) * 100:.2f}%" if isinstance(score_val, (int, float)) else "Score unavailable"
                case_id = c.get("case_id", "CASE")
                issue = c.get("issue_description") or c.get("key_issue", "N/A")
                strategy = c.get("resolution_strategy") or c.get("agent_action", "N/A")
                historical_reply = c.get("recommended_reply") or ""
                category = c.get("category") or c.get("intent") or "N/A"

                st.markdown(f"""
                <div class="cbr-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="color:#818CF8;">{case_id}</b>
                        <span class="cbr-badge">{score_pct} Similarity ({c.get('match_type', 'unknown')})</span>
                    </div>
                    <p style="font-size:0.8rem; color:#CBD5E1;"><b>Category:</b> {category}</p>
                    <p style="font-size:0.85rem; margin-top:6px;"><b>Issue:</b> {issue}</p>
                    <p style="font-size:0.8rem; color:#9CA3AF;">✓ <b>Resolution:</b> {strategy}</p>
                    <p style="font-size:0.8rem; color:#D1FAE5;"><b>Suggested response:</b> {historical_reply}</p>
                </div>
                """, unsafe_allow_html=True)
                if historical_reply and st.button("Use", key=f"use_cbr_{case_id}"):
                    try:
                        response = post_to_backend(
                            f"/api/cases/{st.session_state.customer_id}/{st.session_state.case_id}/use-historical-case",
                            json={"historical_case_id": case_id},
                            timeout=120,
                        )
                        if response.status_code != 200:
                            st.error(f"Unable to adapt historical case: {response.text}")
                        else:
                            generated = response.json()
                            generated_output = generated.get("final_cbr_output", {})
                            generated_response = generated_output.get("drafted_response", "")
                            if generated_response:
                                generated["retrieved_cases"] = st.session_state.backend_data.get("retrieved_cases", [])
                                st.session_state.backend_data = generated
                                st.session_state.agent_draft = generated_response
                                event_response = post_to_backend(
                                    f"/api/cases/{st.session_state.customer_id}/{st.session_state.case_id}/events",
                                    json={
                                        "event_type": "AI_RECOMMENDATION_USED",
                                        "event_details": {
                                            "recommendation": generated_response,
                                            "source": "CBR",
                                            "source_case_id": case_id,
                                        },
                                    },
                                    timeout=30,
                                )
                                if event_response.status_code != 200:
                                    st.error(f"Response generated, but usage tracking failed: {event_response.text}")
                                st.rerun()
                    except requests.RequestException:
                        st.error("Unable to reach the response synthesis service.")
        else:
            st.caption("No matching historical cases retrieved from Vector DB.")

    st.markdown("---")
    st.subheader("🎯 AI Response Scorecard")
    fb = st.session_state.get("feedback") or (st.session_state.get("backend_data", {}).get("final_cbr_output", {}) or {}).get("feedback") or {}
    m1, m2, m3 = st.columns(3)
    m1.metric("Tone", f"{fb.get('tone_score', '--')}/10")
    m2.metric("Empathy", f"{fb.get('empathy_score', '--')}/10")
    m3.metric("Clarity", f"{fb.get('clarity_score', '--')}/10")
    score_values = {
        "Tone": fb.get("tone_score", 0),
        "Empathy": fb.get("empathy_score", 0),
        "Clarity": fb.get("clarity_score", 0),
    }
    if any(score_values.values()):
        st.caption("Agent response quality")
        st.bar_chart(score_values, height=180)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class="coaching-box">
        <b>💡 Real-Time AI Coaching:</b><br>
        {fb.get('coaching_tip', 'Ingest customer signal or submit an agent draft to receive AI feedback.')}
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
st.subheader("Case Escalation")
if selected_case.get("escalation_status") == "ESCALATED":
    st.info(f"Escalated: {selected_case.get('escalation_reason') or 'Not available'}")
else:
    with st.form(f"escalate_case_form_{st.session_state.case_id}"):
        escalation_department_options = ["Accounts", "Support"]
        current_department = selected_case.get("department") or "Support"
        escalation_department_index = escalation_department_options.index(current_department) if current_department in escalation_department_options else 0
        escalation_department = st.selectbox("Escalate to department", escalation_department_options, index=escalation_department_index)
        escalation_reason = st.selectbox(
            "Escalation reason",
            [
                "Customer frustration / unresolved issue",
                "Repeated failed resolution",
                "Requires manager intervention",
                "Policy exception required",
                "Other",
            ],
        )
        escalation_details = st.text_input("Additional details (optional)")
        escalation_submitted = st.form_submit_button("Escalate Case")
    if escalation_submitted:
        try:
            if escalation_department != (selected_case.get("department") or "Support"):
                transfer_response = post_to_backend(
                    f"/api/cases/{st.session_state.customer_id}/{st.session_state.case_id}/transfer",
                    json={"department": escalation_department},
                    timeout=30,
                )
                if transfer_response.status_code != 200:
                    st.error(f"Unable to transfer case to {escalation_department}: {transfer_response.text}")
                else:
                    st.session_state.active_case = transfer_response.json()
            escalation_response = post_to_backend(
                f"/api/cases/{st.session_state.customer_id}/{st.session_state.case_id}/escalate",
                json={"reason": escalation_reason, "details": escalation_details or None},
                timeout=30,
            )
            if escalation_response.status_code == 200:
                st.session_state.active_case = escalation_response.json()
                st.session_state.selected_queue_case = escalation_response.json()
                st.success("Case escalated.")
                st.rerun()
            else:
                st.error(f"Unable to escalate case: {escalation_response.text}")
        except requests.RequestException as error:
            st.error(f"Unable to reach escalation service: {error}")