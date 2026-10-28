"""Read-only support: bounded semantic routing, reviewed knowledge, live scoped data.
Model prose is checked against approved evidence; no executable tools are exposed.
"""
import hashlib
import json
import re
import secrets
import threading
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.config import settings, BASE_DIR
from app.database import get_db
from app.models import ChatSession, ChatMessage, TicketLookupCredential, WarrantyTicket
from app.crud.warranty_tickets import apply_ticket_scope_filter
from app.services.auth_service import get_raw_token, load_user_from_token, require_permissions, PERM_TICKET_VIEW
from app.services.ai_error_classifier import OpenAICompatibleProvider, AIProviderError, sanitize_pii
from app.services.warranty_rules import TICKET_STATUS_LABELS
from app.services import support_conversation as conversation

router = APIRouter(prefix='/api/v1/chatbot', tags=['Trợ lý bảo hành'])
OUTSIDE = 'Mình hỗ trợ sử dụng BaoHanhAI và các vấn đề bảo hành thiết bị. Bạn muốn tra cứu phiếu, hỏi tiến độ hay tìm hiểu cách gửi bảo hành?'
LIMITS = defaultdict(deque)
LOCK = threading.Lock()
BUSY = set()
INTENTS = {'general', 'lookup', 'summary', 'draft', 'duration', 'outside', 'blocked'}
TOPICS = {'usage', 'intake', 'process', 'policy', 'symptoms'}

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Start(StrictModel):
    ticket_id: int | None = Field(default=None, gt=0)

class Question(StrictModel):
    message: str = Field(min_length=1, max_length=1500)
    request_id: str = Field(min_length=8, max_length=64, pattern=r'^[a-zA-Z0-9-]+$')
    ticket_code: str | None = Field(default=None, max_length=50)

class Cancel(StrictModel):
    request_id: str = Field(min_length=8, max_length=64, pattern=r'^[a-zA-Z0-9-]+$')

class Verify(StrictModel):
    ticket_code: str = Field(min_length=1, max_length=50)
    secret: str = Field(min_length=1, max_length=100, repr=False)

class Plan(StrictModel):
    intent: Literal['general','lookup','summary','draft','duration','outside','blocked']
    topic: Literal['usage','intake','process','policy','symptoms']
    focus: Literal['status','warranty','history','technician'] = 'status'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def limit(key, count=20, window=60):
    now = time.monotonic()
    with LOCK:
        # Bound memory without dropping active buckets.
        for old in list(LIMITS):
            if not LIMITS[old] or LIMITS[old][-1] < now - 600:
                del LIMITS[old]
        bucket = LIMITS[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= count:
            raise HTTPException(429, 'Bạn thao tác quá nhanh. Vui lòng thử lại sau ít phút.')
        bucket.append(now)


def guard(request, kind='chat', count=20, window=60):
    if not settings.chatbot_enabled:
        raise HTTPException(503, 'Chức năng hỗ trợ đang tạm tắt (CHATBOT_ENABLED).')
    limit((kind, request.client.host if request.client else 'local'), count, window)


def actor(db, token):
    return load_user_from_token(token, db) if token else None


def scoped_ticket(db, user, ticket_id=None, code=None):
    if not user or not user.service_center_id:
        raise HTTPException(404, 'Không tìm thấy phiếu trong phạm vi được phép.')
    query = apply_ticket_scope_filter(db.query(WarrantyTicket), current_user=user, scope='ALL')
    if user.role == 'TECHNICIAN':
        query = query.filter(WarrantyTicket.assigned_technician_id == user.id)
    elif user.role not in ('MANAGER', 'RECEPTIONIST'):
        raise HTTPException(403, 'Bạn không có quyền xem phiếu.')
    query = query.filter(WarrantyTicket.id == ticket_id) if ticket_id else query.filter(WarrantyTicket.ticket_code == code)
    ticket = query.first()
    if not ticket:
        raise HTTPException(404, 'Không tìm thấy phiếu trong phạm vi được phép.')
    return ticket


def session(db, capability, token):
    user = actor(db, token)  # Revalidate revocation, account lock and role on every call.
    row = db.query(ChatSession).filter(ChatSession.session_code == digest(capability or '')[:30]).first()
    if not row or row.status != 'ACTIVE' or datetime.utcnow() - row.started_at > timedelta(minutes=30):
        raise HTTPException(401, 'Hội thoại đã hết hiệu lực. Vui lòng bắt đầu hội thoại mới.')
    meta = json.loads(row.title)
    if row.user_id != (user.id if user else None) or meta['auth'] != digest(token or ''):
        raise HTTPException(401, 'Phiên hỗ trợ không thuộc tài khoản đang dùng.')
    return row, meta, user


@router.post('/sessions')
def start(payload: Start, request: Request, db: Session = Depends(get_db), token=Depends(get_raw_token)):
    guard(request)
    user = actor(db, token)
    ticket = scoped_ticket(db, user, ticket_id=payload.ticket_id) if payload.ticket_id else None
    capability = secrets.token_urlsafe(32)
    row = ChatSession(session_code=digest(capability)[:30], user_id=user.id if user else None,
                      ticket_id=ticket.id if ticket else None, channel='WEB',
                      title=json.dumps({'auth': digest(token or ''), 'grant': None}))
    db.add(row)
    db.commit()
    return {'session': capability, 'mode': mode(), 'ticket_code': ticket.ticket_code if ticket else None, 'ticket': ticket_card(ticket) if ticket else None}


@router.delete('/sessions')
def close(db: Session = Depends(get_db), token=Depends(get_raw_token), x_chat_session: str = Header(default='')):
    row, _, _ = session(db, x_chat_session, token)
    conversation.clear(row.session_code)
    row.status = 'CLOSED'
    row.closed_at = datetime.utcnow()
    db.commit()
    return {'closed': True}


@router.post('/verify')
def verify(payload: Verify, request: Request, db: Session = Depends(get_db), token=Depends(get_raw_token), x_chat_session: str = Header(default='')):
    guard(request, 'verify', 5, 300)
    row, meta, user = session(db, x_chat_session, token)
    conversation.clear(row.session_code)
    if user:
        raise HTTPException(400, 'Nhân viên dùng quyền đăng nhập để xem phiếu.')
    ticket = db.query(WarrantyTicket).filter(WarrantyTicket.ticket_code == payload.ticket_code.strip()).first()
    credential = db.get(TicketLookupCredential, ticket.id) if ticket else None
    valid = credential and credential.expires_at > datetime.utcnow() and secrets.compare_digest(credential.token_hash, digest(payload.secret))
    if not valid:
        # Uniform response; old verification cannot survive a failed attempt.
        row.ticket_id = None
        meta['grant'] = None
        row.title = json.dumps(meta)
        db.commit()
        raise HTTPException(403, 'Không xác minh được phiếu. Mã không đúng hoặc đã hết hiệu lực.')
    row.ticket_id = ticket.id
    meta['grant'] = credential.token_hash
    row.title = json.dumps(meta)
    db.commit()
    return {'verified': True, 'ticket_code': ticket.ticket_code, 'ticket': ticket_card(ticket)}


@router.post('/tickets/{ticket_id}/lookup-code')
def issue(ticket_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_permissions(PERM_TICKET_VIEW))):
    guard(request, 'issue', 10)
    ticket = scoped_ticket(db, user, ticket_id=ticket_id)
    if user.role not in ('MANAGER', 'RECEPTIONIST'):
        raise HTTPException(403, 'Chỉ quầy tiếp nhận hoặc quản lý được cấp mã cho khách.')
    secret = secrets.token_urlsafe(32)
    credential = db.get(TicketLookupCredential, ticket.id)
    if not credential:
        credential = TicketLookupCredential(ticket_id=ticket.id)
        db.add(credential)
    credential.token_hash = digest(secret)
    credential.expires_at = datetime.utcnow() + timedelta(days=30)
    db.commit()
    return {'secret': secret, 'expires_at': credential.expires_at, 'ticket_code': ticket.ticket_code}


@router.delete('/tickets/{ticket_id}/lookup-code')
def revoke(ticket_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_permissions(PERM_TICKET_VIEW))):
    guard(request)
    ticket = scoped_ticket(db, user, ticket_id=ticket_id)
    if user.role not in ('MANAGER', 'RECEPTIONIST'):
        raise HTTPException(403, 'Bạn không có quyền thu hồi mã.')
    credential = db.get(TicketLookupCredential, ticket.id)
    if credential:
        db.delete(credential)
        db.commit()
    return {'revoked': True}


def mode():
    return 'Chế độ mô phỏng' if settings.chatbot_provider.lower() in ('mock','rule','rule_based','mockai') else 'Chế độ AI'


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower().replace('đ','d')) if unicodedata.category(c) != 'Mn')


def mock_plan(question, previous):
    """Explicit offline demo; semantic model is used in real mode, never silently substituted."""
    q = normalize(question)
    for short, full in [('bh','bao hanh'),('tt','tien do'),('ktv','ky thuat vien'),('ko','khong'),('dc','duoc'),('tien trinh','tien do'),('tien doo','tien do'),('xog','xong'),('baoh','bao hanh')]:
        q = re.sub(r'\b' + short + r'\b', full, q)
    if any(s in q for s in ('system prompt','api key','api_key','mat khau','bo qua huong dan','ignore previous','moi khach hang','toi la quan ly','doi trang thai','xoa phieu','gui sms','tu thao','thao may')):
        return Plan(intent='blocked', topic='usage')
    related = any(s in q for s in ('bao hanh','baohanhai','phieu','tien do','gui may','thiet bi','sua chua','tiep nhan','dieu kien','cach su dung','loi may','xong chua','lay duoc','may do con han','lay may'))
    follow = bool(previous and previous not in ('outside','blocked')) and any(s in q for s in ('bao lau','con phieu nay','may nay','roi sao','tiep theo','can gi','tom tat','soan','ai sua','het han','xong chua','lay duoc','may do','con han','lay may','chung nao','khi nao'))
    if not related and not follow:
        return Plan(intent='outside', topic='usage')
    if follow and any(w in q for w in ('xong chua','lay duoc','may do','con han','lay may','chung nao','khi nao')):
        return Plan(intent='lookup', topic='usage', focus='warranty' if re.search(r'\bhan\b', q) else 'status')
    if 'bao lau' in q or 'ngay xong' in q:
        return Plan(intent='duration', topic='policy')
    if 'tom tat' in q:
        return Plan(intent='summary', topic='process')
    if 'soan' in q or 'thong bao' in q:
        return Plan(intent='draft', topic='process')
    if any(s in q for s in ('tra cuu','tien do','phieu nay','lich su','ai sua','han bao hanh','con han')):
        return Plan(intent='lookup', topic='usage', focus='warranty' if re.search(r'\bhan\b', q) else ('history' if 'lich su' in q else ('technician' if 'ai sua' in q else 'status')))
    topic = next((t for t, words in [('policy',('dieu kien','chinh sach','phi','doi moi')), ('intake',('gui may','can gi')), ('symptoms',('mo ta','loi may')), ('process',('quy trinh','tu choi','sua chua','tiep theo','roi sao'))] if any(w in q for w in words)), 'usage')
    return Plan(intent='general', topic=topic)


def plan(question, previous, history=None, timeout=30):
    if mode() == 'Chế độ mô phỏng':
        return mock_plan(question, previous)
    if settings.chatbot_provider.lower().replace('-','_') not in ('openai','openai_compatible','auto','llm'):
        raise HTTPException(503, 'CHATBOT_PROVIDER chưa được hỗ trợ. Chọn mock hoặc openai_compatible.')
    if not settings.ai_api_key:
        raise HTTPException(503, 'Chưa cấu hình AI_API_KEY (hoặc OPENAI_API_KEY).')
    try:
        result = OpenAICompatibleProvider(timeout=timeout).plan_support(question, previous or '', history=history or [])
        return Plan.model_validate(result)
    except AIProviderError as exc:
        if str(exc) == 'SUPPORT_TIMEOUT':
            raise HTTPException(504, 'AI phản hồi quá lâu. Vui lòng thử lại.') from None
        raise HTTPException(502, 'Không kết nối được AI. Vui lòng thử lại.') from None
    except Exception:
        raise HTTPException(502, 'AI trả lời không hợp lệ. Vui lòng thử lại.') from None


def knowledge(topic):
    # Explicit allowlist: never scan directories, .env, logs, backups or source code.
    content = (Path(BASE_DIR) / 'docs' / 'SUPPORT_KNOWLEDGE.md').read_text(encoding='utf-8-sig')
    match = re.search(r'^## ' + re.escape(topic) + r' \| ([^\n]+)\n(.*?)(?=\n## |\Z)', content, re.M | re.S)
    if not match:
        raise HTTPException(503, 'Hướng dẫn đang được cập nhật.')
    return match.group(1).strip(), match.group(2).strip()


def live_ticket(db, row, meta, user, code):
    if user:
        return scoped_ticket(db, user, ticket_id=None if code else row.ticket_id, code=code) if code or row.ticket_id else None
    if not row.ticket_id:
        return None
    credential = db.get(TicketLookupCredential, row.ticket_id)
    if not credential or credential.expires_at <= datetime.utcnow() or not secrets.compare_digest(credential.token_hash, meta.get('grant') or ''):
        raise HTTPException(403, 'Mã tra cứu đã hết hiệu lực. Vui lòng xác minh lại.')
    ticket = db.get(WarrantyTicket, row.ticket_id)
    if code and code != ticket.ticket_code:
        raise HTTPException(403, 'Vui lòng xác minh mã riêng cho phiếu này.')
    return ticket


def ticket_text(ticket, intent, user):
    # Only structured fields. Free-form issue/history notes are never instructions or output.
    device = ticket.product_instance
    name = sanitize_pii(device.product.name if device and device.product else 'Chưa xác định thiết bị')[:120]
    status = TICKET_STATUS_LABELS.get(ticket.status, 'Chưa xác định')
    text = f'Phiếu {ticket.ticket_code} — {name}: {status}.'
    if intent == 'draft':
        return f'Kính gửi quý khách, {text} Trung tâm sẽ cập nhật khi có thông tin mới. Đây là bản nháp để bạn xem lại và sao chép.'
    history = sorted(ticket.status_history or [], key=lambda x: x.id)
    lines = [f'{h.created_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7))):%d/%m/%Y %H:%M} (UTC+7): {TICKET_STATUS_LABELS.get(h.to_status, "Chưa xác định")}' for h in history if h.created_at]
    text += '\n' + ('\n'.join(lines[-12:]) if lines else 'Chưa có mốc xử lý được ghi nhận.')
    if device and device.warranty_end_date:
        text += f'\nHạn bảo hành đã lưu: {device.warranty_end_date:%d/%m/%Y}.'
    else:
        text += '\nChưa xác định hạn bảo hành.'
    if user:
        tech = ticket.assigned_technician
        text += '\nKỹ thuật viên: ' + (sanitize_pii(tech.full_name) if tech else 'Chưa phân công') + '.'
    return text


def ticket_card(ticket):
    return {'code': ticket.ticket_code, 'status': TICKET_STATUS_LABELS.get(ticket.status, 'Chưa xác định')}


def facts_for(ticket, selected):
    """Minimum structured facts. Names, serials, free-form notes and identifiers stay local."""
    status_text = {
        'RECEIVED': 'Máy của bạn đã được tiếp nhận và đang chờ kiểm tra.',
        'INSPECTING': 'Máy của bạn đang được kiểm tra.',
        'REPAIRING': 'Máy của bạn đang được sửa chữa.',
        'COMPLETED': 'Máy của bạn đã sửa xong và đang chờ bàn giao.',
        'REJECTED': 'Phiếu đã bị từ chối bảo hành và máy đang chờ bàn giao lại.',
        'RETURNED': 'Máy của bạn đã được bàn giao, phiếu đã đóng.',
    }.get(ticket.status, 'Mình chưa xác định được trạng thái máy.')
    evidence = {'current': status_text}
    fallback = status_text
    if selected.focus == 'warranty':
        end = ticket.product_instance.warranty_end_date if ticket.product_instance else None
        if end:
            today = datetime.now(timezone(timedelta(hours=7))).date()
            evidence = {'warranty': f'Hạn bảo hành đã lưu là {end:%d/%m/%Y}; ' + ('còn hạn theo ngày hiện tại.' if end >= today else 'đã hết hạn theo ngày hiện tại.')}
        else:
            evidence = {'warranty': 'Phiếu chưa có dữ liệu để xác định hạn bảo hành.'}
        fallback = evidence['warranty']
    elif selected.intent == 'summary' or selected.focus == 'history':
        history = sorted(ticket.status_history or [], key=lambda h: h.id)[-6:]
        evidence['history'] = [
            {'status': TICKET_STATUS_LABELS.get(h.to_status, 'Chưa xác định'),
             'at': h.created_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M') if h.created_at else None}
            for h in history]
        fallback += ' ' + ('Các mốc ghi nhận: ' + '; '.join(h['status'] for h in evidence['history']) + '.' if history else 'Chưa có mốc xử lý được ghi nhận.')
    elif selected.focus == 'technician':
        # Employee names are displayed by the backend only, never sent to the model.
        evidence['assignment'] = 'Phiếu đã được phân công kỹ thuật viên.' if ticket.assigned_technician_id else 'Phiếu chưa được phân công kỹ thuật viên.'
        fallback += ' ' + evidence['assignment']
    if selected.focus == 'status' and ticket.status not in ('COMPLETED','RETURNED','REJECTED'):
        evidence['appointment'] = 'Phiếu chưa có ngày hẹn trả được xác nhận; chưa thể xác nhận khi nào bạn nhận được máy.'
        fallback += ' ' + evidence['appointment']
    if selected.intent == 'draft':
        fallback = 'Mình soạn bản nháp để bạn xem lại và sao chép: ' + fallback
    return evidence, fallback


def provider_error(exc):
    if str(exc) == 'SUPPORT_TIMEOUT':
        raise HTTPException(504, 'AI phản hồi quá lâu. Bạn có thể thử lại.') from None
    raise HTTPException(502, 'Không kết nối được AI. Bạn có thể thử lại.') from None


@router.post('/cancel')
def cancel_message(payload: Cancel, db: Session = Depends(get_db), token=Depends(get_raw_token), x_chat_session: str = Header(default='')):
    row, _, _ = session(db, x_chat_session, token)
    conversation.cancel(row.session_code, digest(payload.request_id))
    return {'cancelled': True}


@router.post('/messages')
def message(payload: Question, request: Request, db: Session = Depends(get_db), token=Depends(get_raw_token), x_chat_session: str = Header(default='')):
    guard(request)
    context_key = digest(x_chat_session or '')[:30]
    try:
        row, meta, user = session(db, x_chat_session, token)
    except HTTPException:
        conversation.clear(context_key)
        raise
    key = row.id
    with LOCK:
        if key in BUSY:
            raise HTTPException(409, 'Đang trả lời. Bạn vui lòng chờ hoặc thử lại sau khi đã hủy.')
        BUSY.add(key)
    try:
        deadline = time.monotonic() + min(settings.ai_timeout_seconds, 30)
        request_hash = digest(payload.request_id)
        current = conversation.state(context_key)
        revision = current['revision']

        def check_active():
            if conversation.state(context_key) is not current or current['revision'] != revision or request_hash in current['cancelled']:
                raise HTTPException(409, 'Đã hủy chờ câu trả lời này.')
            db.expire_all()
            fresh, fresh_meta, fresh_user = session(db, x_chat_session, token)
            if fresh.ticket_id != initial_ticket_id or fresh_meta != meta:
                conversation.clear(context_key)
                raise HTTPException(409, 'Phiếu đang hỏi đã thay đổi. Bạn hãy gửi lại câu hỏi.')
            if fresh.ticket_id:
                live_ticket(db, fresh, fresh_meta, fresh_user, None)
            return fresh, fresh_meta, fresh_user

        initial_ticket_id = row.ticket_id
        if row.turn_count >= min(settings.chatbot_max_turns, 20):
            raise HTTPException(409, 'Hội thoại đã đủ số lượt. Bạn hãy bắt đầu hội thoại mới.')
        if db.query(ChatMessage).filter(ChatMessage.session_id == row.id, ChatMessage.content == request_hash).first():
            raise HTTPException(409, 'Tin nhắn này đã được xử lý. Bạn hãy gửi câu hỏi mới.')
        # Authorize current context BEFORE any provider call, including routing.
        ticket = live_ticket(db, row, meta, user, payload.ticket_code)
        ticket_id = ticket.id if ticket else None
        if current['ticket'] != ticket_id:
            conversation.clear(context_key)
            current['ticket'] = ticket_id
            revision = current['revision']
        private = []
        if ticket and ticket.customer:
            private = [ticket.customer.full_name, ticket.customer.phone, ticket.customer.email, ticket.customer.address]
        if ticket and ticket.assigned_technician:
            private.append(ticket.assigned_technician.full_name)
        if ticket:
            private.append(ticket.ticket_code)
            if ticket.product_instance:
                private.append(ticket.product_instance.serial_number)
        question = conversation.clean(payload.message, private)
        if not question.strip():
            raise HTTPException(422, 'Bạn muốn hỏi điều gì?')
        history = [dict(m) for m in current['history']]
        context_budget = max(0, min(3000, settings.chatbot_max_context_chars - len(question) - 300))
        while history and sum(len(m['content']) for m in history) > context_budget:
            history.pop(0)
        previous = ('lookup' if ticket and row.last_intent in (None,'outside','blocked') else row.last_intent) or ''
        selected = plan(question, previous, history=history, timeout=max(.1, deadline-time.monotonic()))
        check_active()
        needs_verification = False
        citations = []
        evidence = {}
        safe_fallback = False
        if selected.intent in ('outside','blocked'):
            answer = OUTSIDE
        elif selected.intent in ('lookup','summary','draft') or (selected.intent == 'duration' and ticket):
            if ticket is None:
                needs_verification = not user
                answer = 'Bạn xác minh phiếu ngay bên dưới nhé; mình sẽ tiếp tục trả lời câu hỏi này.' if not user else 'Bạn mở chi tiết phiếu rồi chọn “Hỏi về phiếu này” nhé.'
            else:
                evidence, answer = facts_for(ticket, selected)
                citations = [f'Phiếu {ticket.ticket_code} — dữ liệu hiện tại']
        elif selected.intent == 'duration':
            evidence = {'duration': 'Chưa có thời hạn sửa chữa được xác nhận. Trung tâm cần kiểm tra thực tế; không thể cam kết ngày sửa xong.'}
            answer = 'Mình chưa có thời hạn sửa chữa được xác nhận. Trung tâm cần kiểm tra thực tế trước khi cập nhật cho bạn.'
        else:
            title, passage = knowledge(selected.topic)
            evidence = {'guide': passage}
            # Short, fact-based path for demo and rejected model prose.
            answer = ' '.join(re.split(r'(?<=[.!?])\s+', passage)[:3])
            citations = [title]
        if evidence and mode() != 'Chế độ mô phỏng':
            fallback = answer
            evidence_budget = max(0, settings.chatbot_max_context_chars - len(question) - len(json.dumps(evidence, ensure_ascii=False)) - 300)
            while history and sum(len(m['content']) for m in history) > evidence_budget:
                history.pop(0)
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise HTTPException(504, 'AI phản hồi quá lâu. Bạn có thể thử lại.')
            provider = OpenAICompatibleProvider(timeout=remaining)
            try:
                proposed = provider.compose_support({'question': question, 'history': history,
                    'intent': selected.intent, 'evidence': evidence})
                check_active()
                candidate = proposed.get('answer') if isinstance(proposed, dict) else None
                sources = proposed.get('sources') if isinstance(proposed, dict) else None
                valid = conversation.basic_grounded(candidate, evidence, sources)
                if valid:
                    provider.timeout = max(.1, deadline-time.monotonic())
                    if time.monotonic() >= deadline:
                        raise AIProviderError('SUPPORT_TIMEOUT')
                    verdict = provider.verify_support({'candidate': candidate, 'evidence': evidence})
                    valid = isinstance(verdict, dict) and verdict.get('supported') is True
                if valid:
                    answer = candidate.strip()
                else:
                    safe_fallback = True
                    answer = fallback + ' Mình chỉ xác nhận được những thông tin này từ dữ liệu hiện có.'
            except AIProviderError as exc:
                provider_error(exc)
        if evidence and mode() != 'Chế độ mô phỏng' and time.monotonic() > deadline:
            raise HTTPException(504, 'AI phản hồi quá lâu. Bạn có thể thử lại.')
        fresh, fresh_meta, fresh_user = check_active()
        if ticket:
            latest = live_ticket(db, fresh, fresh_meta, fresh_user, payload.ticket_code)
            latest_evidence, latest_fallback = facts_for(latest, selected)
            if evidence and latest_evidence != evidence:
                answer = latest_fallback + ' Dữ liệu vừa được cập nhật; mình dùng thông tin mới nhất.'
                safe_fallback = True
            card = ticket_card(latest)
        else:
            card = None
        if user and ticket:
            fresh.ticket_id = ticket.id
        fresh.last_intent = selected.intent + (':' + selected.topic if selected.intent == 'general' else '')
        fresh.turn_count += 1
        fresh.last_message_at = datetime.utcnow()
        db.add(ChatMessage(session_id=fresh.id, turn_index=fresh.turn_count, role='SYSTEM', content=request_hash))
        db.commit()
        # Only in-memory, sanitized conversation; no transcripts or model inputs in DB.
        conversation.remember(context_key, question, answer, ticket_id)
        return {'answer': answer, 'citations': citations, 'mode': mode(), 'ticket': card,
                'needs_verification': needs_verification, 'safe_fallback': safe_fallback}
    except HTTPException as exc:
        if exc.status_code in (401,403,404):
            conversation.clear(context_key)
        raise
    finally:
        with LOCK:
            BUSY.discard(key)
