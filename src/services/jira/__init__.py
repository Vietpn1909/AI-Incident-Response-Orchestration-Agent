"""Lớp tích hợp Jira — quản lý vòng đời incident (xem ADR-0001).

Import từ đây, không import trực tiếp từ module con:

    from src.services.jira import FakeJiraClient   # phát triển, test
    from src.services.jira import RealJiraClient   # chạy thật

`JiraClient` là contract ③ giữa Đức và Việt. Hai bản cài đặt cùng thoả nó, nên
đổi từ Fake sang Real không phải sửa code Agent.

Cổng phê duyệt HITL không nằm trong package này mà ở `src.services.hitl` — nó
là quy tắc nghiệp vụ áp lên dữ liệu Jira, không phải một thao tác Jira.
"""

from src.services.jira.client import FakeJiraClient, JiraClient
from src.services.jira.mapping import (
    INCIDENT_LABEL,
    JIRA_STATUS,
    jira_status_for,
    jql_open_incidents,
    labels_for,
    service_from_labels,
    service_label,
    severity_from_labels,
    severity_label,
    state_from_jira_status,
)
from src.services.jira.real import JiraApiError, RealJiraClient

__all__ = [
    "INCIDENT_LABEL",
    "JIRA_STATUS",
    "FakeJiraClient",
    "JiraApiError",
    "JiraClient",
    "RealJiraClient",
    "jira_status_for",
    "jql_open_incidents",
    "labels_for",
    "service_from_labels",
    "service_label",
    "severity_from_labels",
    "severity_label",
    "state_from_jira_status",
]
