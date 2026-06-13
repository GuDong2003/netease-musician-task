import logging
import json
from datetime import datetime

import requests

try:
    from config import (
        CUSTOM_WEBHOOK_HEADERS,
        CUSTOM_WEBHOOK_METHOD,
        CUSTOM_WEBHOOK_URL,
        WECOM_WEBHOOK_KEY,
    )
except Exception:
    CUSTOM_WEBHOOK_HEADERS = ""
    CUSTOM_WEBHOOK_METHOD = "POST"
    CUSTOM_WEBHOOK_URL = ""
    WECOM_WEBHOOK_KEY = ""


# 运行日志收集（按你的参考实现的形状）
LOGS: list[str] = []


def log(msg):
    print(msg)
    LOGS.append(str(msg))


class InMemoryLogHandler(logging.Handler):
    """
    把 logging 输出收集到 LOGS，便于任务完成后统一通知。
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            LOGS.append(str(msg))
        except Exception:
            # 避免日志收集影响主流程
            pass


def install_log_collector(target_logger: logging.Logger) -> InMemoryLogHandler:
    """
    给指定 logger 安装一个内存收集 handler。
    重复安装时会复用已有的同类 handler。
    """
    for h in target_logger.handlers:
        if isinstance(h, InMemoryLogHandler):
            return h

    handler = InMemoryLogHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    target_logger.addHandler(handler)
    return handler


def _truncate_wecom_text(content: str, limit: int = 3800) -> str:
    # 企业微信消息 content 有长度限制；留一点余量给前后缀
    if content is None:
        return ""
    content = str(content)
    if len(content) <= limit:
        return content
    tail = content[-800:]
    head = content[: max(0, limit - 900)]
    return f"{head}\n\n...(内容过长已截断)...\n\n{tail}"


def send_wecom_webhook(webhook_key: str, content: str, *, title: str | None = None, timeout: int = 10) -> bool:
    """通过企业微信自定义机器人 webhook 发送文本消息。

    这里的入参是机器人的 key（WECOM_WEBHOOK_KEY），函数内部拼接完整 URL。
    """
    if not webhook_key:
        return False

    # 按企业微信文档要求拼接完整 webhook URL
    webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"

    title_text = title or "网易云运行日志"
    body = _truncate_wecom_text(content or "")

    text = f"{title_text}\n\n{body}".strip()
    payload = {"msgtype": "text", "text": {"content": text}}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=timeout)
        if resp.status_code != 200:
            return False
        data = resp.json() if resp.content else {}
        # 企业微信成功一般是 errcode=0
        return isinstance(data, dict) and data.get("errcode", 0) == 0
    except Exception:
        return False


def _parse_custom_headers(headers_text: str) -> dict[str, str]:
    """解析自定义 Webhook 请求头配置。"""
    if not headers_text:
        return {}
    try:
        headers = json.loads(headers_text)
        if isinstance(headers, dict):
            return {str(k): str(v) for k, v in headers.items()}
    except Exception:
        pass

    headers: dict[str, str] = {}
    for item in headers_text.split(";"):
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        key = key.strip()
        if key:
            headers[key] = value.strip()
    return headers


def send_custom_webhook(
    webhook_url: str,
    content: str,
    *,
    title: str | None = None,
    timeout: int = 10,
    event: str = "notification",
    extra: dict | None = None,
) -> bool:
    """向自定义 Webhook 推送通用 JSON 消息。"""
    if not webhook_url:
        return False

    payload = {
        "event": event,
        "title": title or "网易音乐人任务",
        "content": content or "",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    if extra:
        payload["extra"] = extra

    headers = _parse_custom_headers(CUSTOM_WEBHOOK_HEADERS)
    headers.setdefault("Content-Type", "application/json")

    try:
        if CUSTOM_WEBHOOK_METHOD == "GET":
            resp = requests.get(webhook_url, params=payload, headers=headers, timeout=timeout)
        else:
            resp = requests.request(
                CUSTOM_WEBHOOK_METHOD or "POST",
                webhook_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        return 200 <= resp.status_code < 300
    except Exception:
        return False


def send_configured_notification(
    content: str,
    *,
    title: str | None = None,
    timeout: int = 10,
    event: str = "notification",
    extra: dict | None = None,
) -> bool:
    """优先推送自定义 Webhook；未配置时再推送企业微信。"""
    if CUSTOM_WEBHOOK_URL:
        return send_custom_webhook(
            CUSTOM_WEBHOOK_URL,
            content,
            title=title,
            timeout=timeout,
            event=event,
            extra=extra,
        )
    if WECOM_WEBHOOK_KEY:
        return send_wecom_webhook(WECOM_WEBHOOK_KEY, content, title=title, timeout=timeout)
    return False

