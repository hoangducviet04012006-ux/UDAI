"""Launch only the disposable support acceptance dataset, never the application DB."""
import test_support_chatbot as fixture
from app.services.auth_service import hash_password
from app.models import User
with fixture.SessionLocal() as db:
    for user in db.query(User):
        user.password_hash=hash_password('SupportTest-Only-8093')
    db.commit()
# Optional faults exist only on this disposable UI test server, never in app code.
import sys
if '--ui-faults' in sys.argv:
    import asyncio
    from fastapi.responses import JSONResponse
    fault_state={'usage_failed':False}
    @fixture.app.middleware('http')
    async def ui_faults(request,call_next):
        if request.url.path=='/api/v1/chatbot/messages':
            payload=await request.json()
            if payload.get('message')=='Cách sử dụng' and not fault_state['usage_failed']:
                fault_state['usage_failed']=True
                return JSONResponse(status_code=502,content={'detail':'Lỗi kết nối giả lập trên server kiểm thử. Bạn có thể thử lại.'})
            if payload.get('message')=='Tra cứu tiến độ':
                await asyncio.sleep(4)
        return await call_next(request)

if __name__=='__main__':
    import uvicorn
    uvicorn.run(fixture.app,host='127.0.0.1',port=8093,log_level='warning')
