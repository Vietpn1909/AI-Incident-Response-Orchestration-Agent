"""Chạy Agent: poll Prometheus, tự mở Jira issue khi phát hiện sự cố.

    # Dùng FakeJiraClient — không cần token Jira, in ra console
    python scripts/run_agent.py --fake

    # Dùng Jira thật, đọc cấu hình từ .env
    python scripts/run_agent.py

    # Đang chỉnh sửa và chạy đi chạy lại — đừng làm phiền hộp thư người trực
    python scripts/run_agent.py --fake --no-mail

Phòng họp và mail cảnh báo KHÔNG phụ thuộc `--fake`: có `DAILY_API_KEY` là phòng
tạo thật, có `SMTP_EMAIL` là mail gửi thật. Thiếu biến nào thì phần đó tự tắt
kèm một dòng warning, Agent vẫn chạy bình thường.

Dừng bằng Ctrl+C.

Cần Prometheus đang chạy:
    docker compose -f docker-compose.demo.yml up -d
    python demo/seed.py
    python demo/loadtest.py        # terminal khác, để tạo sự cố
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import pathlib
import sys
import time
from datetime import UTC, datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.agents.detection_loop import run_cycle  # noqa: E402
from src.agents.nodes.verify import verify  # noqa: E402
from src.agents.war_room_registry import WarRoomRegistry  # noqa: E402
from src.config import configure_logging, force_utf8_console, get_settings  # noqa: E402
from src.models.incident import IncidentState  # noqa: E402
from src.services import executors  # noqa: E402
from src.services.auto_remediation import (  # noqa: E402
    NGUONG_CHO_DO_LAI_PHUT,
    AutoFixRecord,
    execute_auto_remediation,
    execute_fallback_rollback,
    ready_to_remeasure,
    should_auto_remediate,
    should_fallback_rollback,
)
from src.services.email_client import Attachment, GmailClient  # noqa: E402
from src.services.hitl import ApprovalError, assert_human_approved  # noqa: E402
from src.services.incident_alert import IncidentAlerter, build_alerter  # noqa: E402
from src.services.jira import FakeJiraClient, JiraClient, RealJiraClient  # noqa: E402
from src.services.jira.mapping import FIXED_BY_HUMAN_LABEL  # noqa: E402
from src.services.meeting_room import DailyRoomClient, build_room_client  # noqa: E402
from src.services.postmortem_generator import generate_postmortem  # noqa: E402
from src.services.postmortem_report import build_detailed_report, build_email_body  # noqa: E402
from src.services.prometheus import PrometheusClient  # noqa: E402
from src.services.remediation import UnsupportedActionError, execute, is_already_remediated  # noqa: E402
from src.services.status_updater import status_approved  # noqa: E402

logger = logging.getLogger("agent")

DEFAULT_PROMETHEUS = "http://localhost:9090"
DEFAULT_INTERVAL = 10.0


def build_jira(use_fake: bool) -> JiraClient:
    if use_fake:
        logger.info("Dùng FakeJiraClient — không gọi Jira thật")
        return FakeJiraClient()

    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("JIRA_BASE_URL", settings.jira_base_url),
            ("JIRA_EMAIL", settings.jira_email),
            ("JIRA_API_TOKEN", settings.jira_api_token),
            ("JIRA_PROJECT_KEY", settings.jira_project_key),
        )
        if not value
    ]
    if missing:
        sys.exit(f"❌ Thiếu {', '.join(missing)} trong .env. Chạy với --fake nếu chưa có token Jira.")

    logger.info("Dùng RealJiraClient — %s project %s", settings.jira_base_url, settings.jira_project_key)
    return RealJiraClient(
        base_url=settings.jira_base_url,
        email=settings.jira_email,
        api_token=settings.jira_api_token,
        project_key=settings.jira_project_key,
    )


def build_room() -> DailyRoomClient | None:
    """Dựng client mở phòng họp, hoặc `None` khi chưa có `DAILY_API_KEY`.

    Thiếu key thì **không** `sys.exit` như `build_jira()` làm: phòng họp là tính
    năng phụ bám bên cạnh war room. Thiếu Jira thì Agent không có chỗ nào để ghi
    sự cố nên chạy tiếp là vô nghĩa; thiếu Daily thì nó chỉ mất cái link họp.

    ⚠️ KHÔNG xét `--fake`. Cờ đó chỉ thay `FakeJiraClient`, và đây là đường chạy
    end-to-end **duy nhất** khi đội chưa được cấp Jira API — tắt luôn phòng họp
    theo `--fake` thì tính năng này không nghiệm thu được cho tới tận Mức C.
    """
    return build_room_client()


def build_alert(no_mail: bool) -> IncidentAlerter | None:
    """Dựng client gửi mail cảnh báo, hoặc `None` khi tắt / chưa cấu hình SMTP.

    ⚠️ KHÔNG xét `--fake`, cùng lý do với `build_room()`: cờ đó chỉ thay
    `FakeJiraClient`, và `--fake` là đường chạy end-to-end **duy nhất** khi đội
    chưa được cấp Jira API. Tắt mail theo `--fake` thì tính năng này không
    nghiệm thu được cho tới tận Mức C.

    Cờ tắt riêng là `--no-mail`, vì việc cần tắt là **gửi mail**, không phải
    "đang dùng Jira giả" — trộn hai thứ đó vào một cờ là cách để về sau không ai
    đoán được `--fake` thật ra tắt những gì.

    Không cần `--no-mail` mà vẫn im: chưa đặt `SMTP_EMAIL`/`SMTP_APP_PASSWORD`
    thì `build_alerter()` tự trả `None`. Và `WarRoomRegistry` chặn gửi lặp, nên
    một lần ép tải chỉ ra đúng một mail cho mỗi war room, không phải một mail
    mỗi 10 giây.
    """
    if no_mail:
        logger.info("--no-mail: KHÔNG gửi mail cảnh báo")
        return None
    return build_alerter()


# ---------------------------------------------------------------------------
# Poll Jira: tự phát hiện khi người duyệt chuyển ticket sang Remediating
# ---------------------------------------------------------------------------

def _verify_da_thi_hanh(
    prometheus_client: PrometheusClient,
    jira: JiraClient,
    da_thi_hanh: set[str],
    da_verify: set[str],
    auto_da_thi_hanh: dict[str, AutoFixRecord] | None = None,
    da_rollback_du_phong: set[str] | None = None,
    luc_thi_hanh: dict[str, datetime] | None = None,
) -> None:
    """Đo lại các war room đã thi hành khắc phục, post kết luận lên Jira.

    Chỉ kết luận MỘT LẦN cho mỗi issue. Không đo được (Prometheus lỗi) thì không
    thêm vào `da_verify`, để vòng sau thử lại — khác với "đã kết luận là chưa đỡ".

    Nuốt lỗi từng issue, cùng lý do như `_xet_nang_muc()`: một lần Jira đáp 429
    không được giết cả tiến trình Agent, kể cả khi những issue khác vẫn xử lý
    bình thường được.

    Args:
        auto_da_thi_hanh: các issue **Agent tự thi hành** (auto-fix), key → dấu
            vết lần thi hành đó. Chỉ những issue nằm trong đây mới được xét
            rollback dự phòng.
        da_rollback_du_phong: các issue đã qua bước rollback dự phòng — đã
            rollback, hoặc đã kết luận là không rollback được và nói ra rồi. Cả
            hai đều không lặp lại.
        luc_thi_hanh: key → thời điểm Agent/người thi hành xong. Dùng để bắt
            MỌI issue (kể cả do người duyệt) chờ ít nhất
            `NGUONG_CHO_DO_LAI_PHUT` trước khi đo lại. Trước đây chỉ auto-fix
            mới chờ, issue do người duyệt bị đo ngay 10 giây sau — quá sớm vì
            cửa sổ PromQL `[1m]` còn nguyên dữ liệu lúc đang hỏng.
    """
    now = datetime.now(UTC)
    nguong = timedelta(minutes=NGUONG_CHO_DO_LAI_PHUT)

    for jira_key in sorted(da_thi_hanh - da_verify):
        try:
            incident = jira.get_incident(jira_key)
        except Exception as loi:
            logger.debug("%s: chưa đọc được để verify (%s)", jira_key, loi)
            continue
        if incident is None or not incident.affected_services:
            da_verify.add(jira_key)  # không có service để đo, đừng thử lại mãi
            continue

        # Chờ số đo chín cho MỌI issue — không chỉ auto-fix.
        #
        # Cửa sổ PromQL `[1m]` còn nguyên phần dữ liệu lúc đang hỏng, nên đo
        # ngay sau khi thi hành thì gần như luôn ra "chưa đỡ". Trước đây chỉ
        # auto-fix mới chờ `NGUONG_CHO_DO_LAI_PHUT`, issue do người duyệt bị
        # verify ngay vòng sau (10 giây) — gây kết luận sai.
        auto_fix = (auto_da_thi_hanh or {}).get(jira_key)
        if auto_fix is not None and not ready_to_remeasure(auto_fix):
            logger.debug(
                "%s: mới auto-fix, chờ đủ %d phút rồi mới đo lại",
                jira_key,
                NGUONG_CHO_DO_LAI_PHUT,
            )
            continue
        elif auto_fix is None and luc_thi_hanh is not None:
            # Issue do NGƯỜI duyệt — cũng phải chờ số đo chín.
            moc = luc_thi_hanh.get(jira_key)
            if moc is not None and (now - moc) < nguong:
                logger.debug(
                    "%s: mới thi hành (người duyệt), chờ đủ %d phút rồi mới đo lại",
                    jira_key,
                    NGUONG_CHO_DO_LAI_PHUT,
                )
                continue

        service = incident.affected_services[0]
        ket_qua = verify(
            prometheus_client, service, muc_luc_phat_hien=incident.severity
        )
        if ket_qua is None:
            continue  # chưa đo được — vòng sau thử lại

        logger.info(
            "%s: verify %s → %s",
            jira_key, service,
            "ĐÃ HỒI PHỤC" if ket_qua.hoi_phuc else ("TỆ HƠN" if ket_qua.te_hon else "CHƯA ĐỠ"),
        )
        try:
            jira.add_comment(jira_key, ket_qua.ket_luan)
        except Exception as loi:
            logger.warning("%s: không post được kết luận verify (%s)", jira_key, loi)

        # Vế 3: Agent tự thi hành mà đo lại vẫn chưa đỡ → tự lùi lại phần nó vừa
        # làm. Chỉ chạm vào những issue chính Agent quyết định, và chỉ một lần.
        if auto_fix is not None and _rollback_du_phong(
            jira, auto_fix, ket_qua, auto_da_thi_hanh, da_rollback_du_phong
        ):
            # Đã rollback thật → cho `verify()` chạy lại ĐÚNG một lần nữa, nên
            # không đánh dấu đã kết luận. Vòng sau `should_fallback_rollback()`
            # tự từ chối rollback lần hai, nên không có vòng lặp vô hạn.
            continue

        # KHÔNG tự chuyển sang Resolved dù đã hồi phục.
        #
        # Đóng issue là một quyết định của người trực: họ có thể còn muốn điều tra
        # nguyên nhân, mở việc cần làm, hoặc viết postmortem trước khi đóng. Agent
        # tự đóng là lấy đi bước đó, và cùng tinh thần với cổng HITL — nó báo cáo,
        # người quyết định.
        da_verify.add(jira_key)


def _rollback_du_phong(
    jira: JiraClient,
    auto_fix: AutoFixRecord,
    ket_qua,  # VerifyResult
    auto_da_thi_hanh: dict[str, AutoFixRecord] | None,
    da_rollback_du_phong: set[str] | None,
) -> bool:
    """Xét và thi hành rollback dự phòng cho MỘT issue Agent đã tự thi hành.

    Tách khỏi `_verify_da_thi_hanh()` để test gọi thẳng được, cùng lý do với
    `_xet_nang_muc()` trong `incident_graph.py` — và cũng nuốt lỗi cùng lý do:
    `main()` chỉ bắt `KeyboardInterrupt`, nên một lần Jira đáp 429 ở đây là giết
    cả tiến trình Agent giữa lúc đang có sự cố.

    Returns:
        `True` khi **đã rollback thật** — người gọi cần cho đo lại một lần nữa.
        `False` khi không rollback (chưa đủ điều kiện, đã rollback rồi, tệ hơn,
        không biết lùi về đâu, hoặc có lỗi) — khi đó kết luận vừa post là kết
        luận cuối.
    """
    jira_key = auto_fix.jira_key
    try:
        quyet_dinh = should_fallback_rollback(
            auto_fix,
            hoi_phuc=ket_qua.hoi_phuc,
            te_hon=ket_qua.te_hon,
            con_lai=ket_qua.con_lai,
            da_rollback_du_phong=jira_key in (da_rollback_du_phong or set()),
        )
        if quyet_dinh is None:
            return False

        ket_qua_rollback = execute_fallback_rollback(jira, quyet_dinh)
        # Đánh dấu kể cả khi không rollback được: comment giải thích đã post rồi,
        # post lại mỗi vòng quét chỉ làm ngập war room.
        if da_rollback_du_phong is not None:
            da_rollback_du_phong.add(jira_key)

        if ket_qua_rollback is None:
            return False

        logger.warning(
            "🔁 %s: rollback dự phòng %s → %s — %s",
            jira_key,
            auto_fix.target,
            quyet_dinh.to_version,
            "thành công" if ket_qua_rollback.succeeded else "THẤT BẠI",
        )
        # Dời mốc đếm sang lúc rollback: lần đo tới cũng phải chờ số đo chín,
        # đúng như lần đầu. Ghi `action="rollback"` để chính bản ghi này chặn
        # rollback lần hai, không chỉ dựa vào một cái set.
        if auto_da_thi_hanh is not None:
            auto_da_thi_hanh[jira_key] = dataclasses.replace(
                auto_fix, action="rollback", at=datetime.now(UTC)
            )
        return True
    except Exception as loi:
        logger.error("%s: lỗi khi xét rollback dự phòng (%s)", jira_key, loi)
        return False


def _kiem_tra_auto_remediation(
    jira: JiraClient,
    awaiting_keys: set[str],
    already_executed: set[str],
    auto_da_thi_hanh: dict[str, AutoFixRecord] | None = None,
    luc_thi_hanh: dict[str, datetime] | None = None,
) -> None:
    """Kiểm tra timeout và tự thi hành nếu không ai phản hồi.

    Module `auto_remediation` quyết định có nên auto-fix không dựa trên:
    - Feature có bật không (`AUTO_REMEDIATION_ENABLED`)
    - Issue đã chờ quá thời gian timeout chưa
    - Đã có human phản hồi chưa

    Chạy SAU `poll_jira_approvals()` trong loop: human luôn được ưu tiên trước.
    Nếu human đã duyệt ở `poll_jira_approvals()` thì `already_executed` đã có
    key đó và vòng này không xét nữa.

    Nuốt lỗi từng issue — cùng lý do với `_verify_da_thi_hanh()`.
    """
    for jira_key in sorted(awaiting_keys - already_executed):
        try:
            incident = jira.get_incident(jira_key)
        except Exception as loi:
            logger.debug("%s: chưa đọc được để kiểm auto-remediation (%s)", jira_key, loi)
            continue
        if incident is None or incident.proposal is None:
            continue

        # Bọc lỗi vì `should_auto_remediate()` đi hỏi Jira (changelog) và đọc
        # `deploy_history` — hai đường ra ngoài, hai chỗ ném được. `main()` chỉ
        # bắt `KeyboardInterrupt` nên một exception lọt tới đây là giết cả tiến
        # trình Agent giữa lúc đang có sự cố. Cùng lập luận với `_xet_nang_muc()`
        # trong `incident_graph.py`.
        # Dùng severity LÚC PHÁT HIỆN (từ signal gốc), KHÔNG phải severity
        # hiện tại. Lý do: `escalate` nâng P3 → P2 → P1 sau mỗi 10 phút treo,
        # nên ở phút 30 mọi P3/P4 đều đã là P1 — nhánh P3/P4 "dùng đề xuất gốc"
        # không bao giờ chạy, và Agent ép rollback thay vì thi hành hành động đã
        # đề xuất (restart, scale_up, ...).
        #
        # `signal.severity` là mức Rule Engine phân loại ban đầu, TRƯỚC bất kỳ
        # lần escalate nào — chính xác là thứ chính sách auto-remediation cần.
        severity_goc = (
            incident.signal.severity
            if incident.signal is not None
            else incident.severity
        )
        try:
            decision = should_auto_remediate(
                jira,
                jira_key,
                severity=severity_goc,
                proposal_action=incident.proposal.action,
                proposal_target=incident.proposal.target,
                proposal_params=incident.proposal.params,
                deploy_service=incident.affected_services[0] if incident.affected_services else None,
            )
        except Exception as loi:
            logger.error("%s: lỗi khi xét auto-remediation (%s)", jira_key, loi)
            continue
        if decision is None:
            continue

        logger.warning(
            "⏰ AUTO-REMEDIATION: %s — %s → %s (%s)",
            decision.jira_key,
            decision.action,
            decision.target,
            decision.reason,
        )

        try:
            result = execute_auto_remediation(jira, decision)
            logger.info(
                "⏰ %s: auto-remediation %s — %s",
                jira_key,
                "thành công" if result.succeeded else "THẤT BẠI",
                result.detail,
            )
        except Exception as loi:
            logger.error("%s: lỗi khi auto-remediation (%s)", jira_key, loi)
            continue

        # Ghi lại HÀNH ĐỘNG ĐÃ CHẠY, không phải hành động đã đề xuất: với P1/P2
        # hai thứ đó khác nhau, và `_rollback_du_phong()` dựa vào đây để không
        # rollback lần hai một issue vừa rollback xong.
        if auto_da_thi_hanh is not None:
            auto_da_thi_hanh[jira_key] = AutoFixRecord(
                jira_key=jira_key,
                action=decision.action,
                target=decision.target,
                at=datetime.now(UTC),
            )
        if luc_thi_hanh is not None:
            luc_thi_hanh[jira_key] = datetime.now(UTC)

        already_executed.add(jira_key)
        awaiting_keys.discard(jira_key)


def poll_jira_approvals(
    jira: JiraClient,
    awaiting_keys: set[str],
    already_executed: set[str],
    luc_thi_hanh: dict[str, datetime] | None = None,
) -> None:
    """Kiểm tra các ticket đang Awaiting Approval, nếu có người chuyển sang
    Remediating → verify HITL → execute → postmortem → email.

    Đây là thay thế cho webhook pattern: Agent TỰ phát hiện approval mỗi vòng
    quét, không cần Jira Automation hay script tay.

    Args:
        jira: Client Jira (thật hoặc giả).
        awaiting_keys: Tập Jira key đang chờ duyệt (được cập nhật bên ngoài).
        already_executed: Tập Jira key đã execute rồi, tránh chạy lại.
    """
    settings = get_settings()
    agent_id = settings.jira_agent_account_id

    if not agent_id:
        return  # Thiếu agent account ID thì không kiểm tra được HITL

    for jira_key in list(awaiting_keys):
        if jira_key in already_executed:
            continue

        try:
            # Hỏi Jira: ai đã chuyển ticket sang Remediating?
            approved_by = assert_human_approved(
                jira, jira_key, agent_account_id=agent_id,
            )
        except ApprovalError:
            # Chưa có ai duyệt, hoặc Agent tự duyệt → bỏ qua, vòng sau hỏi lại
            continue
        except Exception as error:
            logger.debug("%s: lỗi khi kiểm tra approval (%s)", jira_key, error)
            continue

        # ĐÃ ĐƯỢC DUYỆT bởi người thật
        # Kiểm idempotency: bên webhook có thể đã chạy trước rồi.
        # Agent local có Docker nên nó LÀ đường thi hành thật được. Cho phép nó
        # ghi đè bản ghi chỉ-mô-phỏng do webhook trên Render tạo ra.
        if is_already_remediated(
            jira, jira_key, cho_phep_nang_cap=executors.co_bat_thi_hanh_that()
        ):
            logger.info("⚠️ %s: đã được thi hành bởi webhook — bỏ qua", jira_key)
            already_executed.add(jira_key)
            awaiting_keys.discard(jira_key)
            continue

        logger.info("🟢 %s: NGƯỜI DUYỆT %s — bắt đầu thực thi", jira_key, approved_by)
        _execute_approved(jira, jira_key, approved_by)
        already_executed.add(jira_key)
        if luc_thi_hanh is not None:
            luc_thi_hanh[jira_key] = datetime.now(UTC)
        awaiting_keys.discard(jira_key)


def _execute_approved(jira: JiraClient, jira_key: str, approved_by: str) -> None:
    """Thực thi remediation + sinh postmortem + gửi email cho 1 ticket đã duyệt.

    Luồng giống hệt `POST /webhooks/jira` nhưng chạy bên trong agent loop thay
    vì qua HTTP.
    """
    # 1. Đọc incident và proposal
    try:
        incident = jira.get_incident(jira_key)
    except Exception as error:
        logger.error("%s: không đọc được incident (%s)", jira_key, error)
        return

    proposal = incident.proposal if incident else None
    if proposal is None:
        logger.warning("%s: không có đề xuất khắc phục — bỏ qua", jira_key)
        return

    # 2. Comment: PHÊ DUYỆT
    try:
        jira.add_comment(jira_key, status_approved(approved_by))
    except Exception:
        logger.warning("%s: không post được comment phê duyệt", jira_key)

    # 3. Execute remediation
    try:
        result = execute(
            proposal.action, proposal.target,
            approved_by=approved_by, params=proposal.params,
        )
    except UnsupportedActionError as error:
        try:
            jira.add_comment(jira_key, f"⚠️ Không thi hành được: {error}")
        except Exception:
            pass
        logger.error("%s: hành động không được phép (%s)", jira_key, error)
        return

    # 4. Comment: kết quả thực thi
    try:
        jira.add_comment(jira_key, result.as_comment())
    except Exception:
        logger.warning("%s: không post được kết quả thực thi", jira_key)

    logger.info(
        "✅ %s: %s → %s — %s%s",
        jira_key, result.action, result.target,
        "thành công" if result.succeeded else "THẤT BẠI",
        " (mô phỏng)" if result.simulated else "",
    )

    # 5. Sinh postmortem + gửi email
    if result.succeeded:
        # Nhãn NGƯỜI: đường này chỉ tới được sau `assert_human_approved()`, tức
        # đã có người thật chuyển trạng thái. `approved_by` là bằng chứng sẵn có
        # tại đây — không phải suy đoán lại từ comment hay từ changelog.
        _gan_nhan_da_fix(jira, jira_key, FIXED_BY_HUMAN_LABEL)

        _try_send_postmortem(jira, jira_key)

        # 6. Chuyển sang Resolved
        try:
            jira.transition(jira_key, IncidentState.RESOLVED)
            logger.info("✅ %s: chuyển sang Resolved", jira_key)
        except Exception:
            logger.warning("%s: không chuyển được sang Resolved — kéo tay trên Jira", jira_key)


def _gan_nhan_da_fix(jira: JiraClient, jira_key: str, nhan: str) -> None:
    """Gắn nhãn "ai đã khắc phục", nuốt lỗi nếu Jira không nhận.

    Nhãn chỉ để **đếm bằng JQL** — comment war room đã kể đủ chuyện cho người
    đọc. Nên mất nhãn là mất một dòng thống kê, còn ném exception ra giữa
    `_execute_approved()` là bỏ dở postmortem và bước chuyển sang Resolved của
    một sự cố vừa được khắc phục xong. Cùng cách xử lý với `add_comment()` và
    `transition()` trong `auto_remediation.py`.
    """
    try:
        jira.add_label(jira_key, nhan)
    except Exception as loi:
        logger.warning("%s: không gắn được nhãn %s (%s)", jira_key, nhan, loi)


def _try_send_postmortem(jira: JiraClient, jira_key: str) -> bool:
    """Sinh postmortem từ dữ liệu thật và gửi email."""
    settings = get_settings()

    if not settings.smtp_email or not settings.smtp_app_password:
        logger.info("%s: bỏ qua postmortem email — SMTP chưa cấu hình", jira_key)
        return False

    recipients = [r.strip() for r in settings.postmortem_recipients.split(",") if r.strip()]
    if not recipients:
        logger.info("%s: bỏ qua postmortem email — POSTMORTEM_RECIPIENTS trống", jira_key)
        return False

    try:
        incident = jira.get_incident(jira_key)
        if incident is None:
            logger.warning("%s: không đọc được incident — bỏ qua postmortem", jira_key)
            return False

        # Sinh postmortem
        postmortem = generate_postmortem(incident, jira=jira)
        incident.postmortem = postmortem

        # Attach lên Jira
        try:
            jira.attach_postmortem(jira_key, postmortem)
        except Exception:
            logger.warning("%s: không attach được postmortem lên Jira", jira_key)

        # Render HTML
        jira_base_url = settings.jira_base_url
        email_body = build_email_body(incident, jira_base_url=jira_base_url)
        report_html = build_detailed_report(incident, jira_base_url=jira_base_url)

        # Gửi email
        gmail = GmailClient(settings.smtp_email, settings.smtp_app_password)
        services_str = ", ".join(incident.affected_services)
        result = gmail.send(
            to=recipients,
            subject=f"[Postmortem] {incident.severity.value} — {services_str} — {jira_key}",
            body_html=email_body,
            attachments=[
                Attachment(
                    filename=f"postmortem_{jira_key}.html",
                    content=report_html.encode("utf-8"),
                    mime_type="text/html",
                )
            ],
        )

        if result.success:
            logger.info("📧 %s: postmortem gửi tới %s", jira_key, ", ".join(recipients))
            try:
                jira.add_comment(jira_key, f"📧 Đã gửi báo cáo postmortem tới {', '.join(recipients)}")
            except Exception:
                pass
            return True

        logger.warning("%s: gửi postmortem thất bại — %s", jira_key, result.error)
        return False

    except Exception:
        logger.exception("%s: lỗi khi sinh/gửi postmortem", jira_key)
        return False


def main() -> int:
    # PHẢI đứng trước parse_args(): argparse in `--help` và thông báo lỗi tham
    # số thẳng ra stdout ngay trong parse_args(), tức trước cả configure_logging().
    # Trên Windows (3/4 thành viên) chưa ép UTF-8 thì `--help` chết bằng
    # UnicodeEncodeError chứ không phải in ra chữ xấu.
    force_utf8_console()

    parser = argparse.ArgumentParser(description="Agent phát hiện sự cố")
    parser.add_argument("--fake", action="store_true", help="dùng FakeJiraClient, không gọi Jira thật")
    parser.add_argument("--prometheus", default=DEFAULT_PROMETHEUS)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="giây giữa hai vòng quét")
    parser.add_argument("--once", action="store_true", help="chạy đúng một vòng rồi thoát")
    parser.add_argument("--no-mail", action="store_true", help="không gửi mail cảnh báo")
    args = parser.parse_args()

    configure_logging()
    jira = build_jira(args.fake)
    room = build_room()
    alerter = build_alert(args.no_mail)
    prometheus_client = PrometheusClient(args.prometheus)

    # Dựng MỘT lần cho cả đời tiến trình, không phải mỗi vòng. Đây chính là chỗ
    # duy nhất giữ trí nhớ giữa các vòng quét: thiếu nó thì mỗi 10 giây Agent
    # lại mở một phòng họp mới và gửi lại một mail cho cùng một sự cố.
    registry = WarRoomRegistry()

    # Trí nhớ cho bước poll Jira approval — giữ xuyên các vòng quét.
    # `awaiting_keys`: các ticket đang chờ duyệt, được thêm vào khi Agent đề xuất.
    # `already_executed`: các ticket đã execute rồi, tránh chạy lặp.
    awaiting_keys: set[str] = set()
    already_executed: set[str] = set()
    #: Đã đo lại và ĐÃ KẾT LUẬN — không đo nữa. Chưa đo được (Prometheus lỗi) thì
    #: không thêm vào, để vòng sau thử lại.
    da_verify: set[str] = set()
    #: Các issue chính Agent TỰ thi hành (auto-fix), key → dấu vết lần đó. Chỉ
    #: chúng mới được xét rollback dự phòng: hành động do người duyệt thì người
    #: đó theo tới cùng, Agent không tự lùi thay.
    auto_da_thi_hanh: dict[str, AutoFixRecord] = {}
    #: Đã qua bước rollback dự phòng — mỗi issue đúng MỘT lần.
    da_rollback_du_phong: set[str] = set()
    #: Thời điểm thi hành xong mỗi issue — dùng để chờ đủ
    #: `NGUONG_CHO_DO_LAI_PHUT` trước khi đo lại, kể cả issue do người duyệt.
    luc_thi_hanh: dict[str, datetime] = {}

    logger.info("Bắt đầu quét %s mỗi %.0fs. Ctrl+C để dừng.", args.prometheus, args.interval)
    cycles = 0
    try:
        while True:
            cycles += 1
            result = run_cycle(
                prometheus_client, jira, room=room, alerter=alerter, registry=registry
            )

            if result.error:
                pass  # đã log ở run_cycle
            elif result.quiet:
                logger.info("Vòng %d: bình thường", cycles)
            else:
                if result.opened:
                    logger.info("Vòng %d: MỞ war room %s", cycles, ", ".join(result.opened))
                # In lại URL ở đây dù `_tao_phong_hop()` đã log lúc tạo: dòng kia
                # nằm lẫn giữa log của LangGraph và Jira, còn dòng này đứng ngay
                # cạnh "MỞ war room" — chỗ người trực thật sự nhìn vào.
                for jira_key, url in result.meeting_rooms.items():
                    logger.info("%s: phòng họp %s", jira_key, url)
                if result.updated:
                    logger.info("Vòng %d: cập nhật %s (đã có incident mở)", cycles, ", ".join(result.updated))

            # Thu thập các ticket vừa đề xuất remediation ở vòng này
            for key in result.opened + result.updated:
                awaiting_keys.add(key)

            # Poll Jira: kiểm tra xem có ticket nào được người duyệt chưa
            if awaiting_keys - already_executed:
                poll_jira_approvals(jira, awaiting_keys, already_executed, luc_thi_hanh)

            # Auto-remediation: nếu đã chờ quá lâu mà không ai phản hồi thì Agent
            # tự sửa. Chạy SAU poll_jira_approvals để ưu tiên human trước.
            # Feature mặc định TẮT, bật bằng AUTO_REMEDIATION_ENABLED=1.
            if awaiting_keys - already_executed:
                _kiem_tra_auto_remediation(
                    jira, awaiting_keys, already_executed, auto_da_thi_hanh,
                    luc_thi_hanh,
                )

            # Đo lại những ticket đã thi hành khắc phục — xem có thật sự đỡ không.
            #
            # Chạy ở VÒNG SAU chứ không ngay sau khi thi hành: hệ thống cần thời
            # gian hồi phục, và cửa sổ PromQL `[1m]` còn chứa dữ liệu lúc đang
            # hỏng. Đo ngay là luôn ra "chưa đỡ".
            #
            # Cũng vì thế không đặt trong webhook: chờ 60 giây trong đó thì webhook
            # timeout, mà Jira Automation lại bỏ cuộc trước.
            #
            # Issue do Agent TỰ thi hành thì đo lại còn là căn cứ để nó rollback
            # dự phòng, nên chúng phải chờ thêm `NGUONG_CHO_DO_LAI_PHUT` — xem
            # `_verify_da_thi_hanh()`.
            if already_executed - da_verify:
                _verify_da_thi_hanh(
                    prometheus_client,
                    jira,
                    already_executed,
                    da_verify,
                    auto_da_thi_hanh,
                    da_rollback_du_phong,
                    luc_thi_hanh,
                )

            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Dừng sau %d vòng.", cycles)
    finally:
        prometheus_client.close()
        close = getattr(jira, "close", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
