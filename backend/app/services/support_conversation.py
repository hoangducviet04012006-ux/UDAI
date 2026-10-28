"""Ephemeral, bounded conversation and conservative grounding checks (no DB writes)."""
import json
import re
import threading
import time
from collections import OrderedDict
from app.services.ai_error_classifier import sanitize_pii

MEMORY = OrderedDict()
MUTEX = threading.Lock()


def state(key):
    now = time.monotonic()
    with MUTEX:
        for old in list(MEMORY):
            if now - MEMORY[old]['at'] > 1800:
                del MEMORY[old]
        if key not in MEMORY:
            if len(MEMORY) >= 2000:
                MEMORY.popitem(last=False)
            MEMORY[key] = {'history': [], 'ticket': None, 'revision': 0, 'cancelled': [], 'at': now}
        MEMORY[key]['at'] = now
        MEMORY.move_to_end(key)
        return MEMORY[key]


def clear(key):
    with MUTEX:
        if key in MEMORY:
            MEMORY[key]['history'] = []
            MEMORY[key]['ticket'] = None
            MEMORY[key]['revision'] += 1


def cancel(key, request_id):
    current = state(key)
    with MUTEX:
        current['revision'] += 1
        current['cancelled'] = (current['cancelled'] + [request_id])[-20:]


def clean(text, private=()):
    text = sanitize_pii(str(text), private)
    text = re.sub(r'[A-Za-z0-9_\-.]{30,}', '[đã ẩn mã]', text)
    text = re.sub(r'(?i)(?:tôi tên|tên khách hàng|địa chỉ|mật khẩu|password|api[_ ]?key)\s*[:=]?\s*[^,.!?\n]+', '[đã ẩn thông tin]', text)
    text = re.sub(r'\b(?:Nguyễn|Trần|Lê|Phạm|Hoàng|Huỳnh|Nguyen|Tran|Pham|Hoang)(?:\s+[A-ZĐ][a-zà-ỹ]+){1,4}\b', '[đã ẩn tên]', text)
    return text[:1500]


def remember(key, question, answer, ticket):
    current = state(key)
    with MUTEX:
        current['ticket'] = ticket
        current['history'] = (current['history'] + [
            {'role': 'user', 'content': clean(question)[:700]},
            {'role': 'assistant', 'content': clean(answer)[:700]}])[-6:]
        while sum(len(m['content']) for m in current['history']) > 3000:
            current['history'].pop(0)


def basic_grounded(answer, evidence, sources):
    """Fail closed for numeric claims, markup, capabilities, and unsupported sources.
    A separate entailment pass checks semantic claims and negation afterward.
    """
    if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 1800:
        return False
    if answer.lstrip().startswith(('{','[','```')):
        return False
    if not isinstance(sources, list) or not sources or any(s not in evidence for s in sources if isinstance(s, str)) or any(not isinstance(s, str) for s in sources):
        return False
    if re.search(r'<[^>]+>|https?://|[\w.+-]+@[\w.-]+\.[a-z]{2,}|[A-Za-z0-9_-]{30,}|(?:[A-Z]:[\\/])', answer, re.I):
        return False
    # Number/date/cost claims must already occur in selected facts, never in the question alone.
    current = evidence.get('current', '')
    if current and 'history' not in evidence:
        if 'đã sửa xong' not in current and re.search(r'(?:đã|vừa) (?:sửa xong|hoàn tất sửa chữa)', answer, re.I):
            return False
        if 'đã được bàn giao' not in current and re.search(r'(?:đã|vừa) (?:trả máy|bàn giao)', answer, re.I):
            return False
        if 'đang được kiểm tra' not in current and re.search(r'(?:máy|thiết bị)(?: của bạn)? đang (?:được )?kiểm tra', answer, re.I):
            return False
    warranty = evidence.get('warranty', '')
    if 'đã hết hạn' in warranty and re.search(r'(?:vẫn |đang |máy .* )còn hạn', answer, re.I):
        return False
    if re.search(r'(?:mang|xuất trình|cung cấp)(?: theo)? (?:giấy|hóa đơn|căn cước)|(?:sẽ|được|hoàn toàn) miễn phí', answer, re.I):
        return False
    approved = json.dumps(evidence, ensure_ascii=False)
    for name in re.findall(r'\b(?:[A-ZĐ][a-zà-ỹ]+\s+){1,4}[A-ZĐ][a-zà-ỹ]+\b|\b[A-Z]{3,}(?:\s+[A-Z]{3,})+\b', answer):
        if name not in approved:
            return False
    if not set(re.findall(r'\d+', answer)).issubset(set(re.findall(r'\d+', approved))):
        return False
    if re.search(r'system prompt|api[_ ]?key|mật khẩu|password|SELECT\s|DROP\s', answer, re.I):
        return False
    return True
