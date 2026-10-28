/* Shared support; capabilities and transcripts remain in the current browser session. */
(() => {
  const publicPage = location.pathname === '/support';
  let capability='', busy=false, epoch=0, flight=0, controller=null, lastQuestion=null, opening=null, pendingQuestion=null, activeTicket=null;
  const auth=()=>publicPage?'':(typeof state!=='undefined'?state.session.token:'');
  const launcher=document.createElement('button');
  launcher.className='bh-launch';launcher.innerHTML='<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg><span>Hỗ trợ</span>';launcher.setAttribute('aria-expanded','false');
  const panel=document.createElement('section');
  panel.id='bh-support';launcher.setAttribute('aria-controls','bh-support');panel.className='bh-chat';panel.hidden=true;panel.setAttribute('aria-label','Trợ lý bảo hành');
  panel.innerHTML=`<header class="bh-head"><strong>Trợ lý bảo hành</strong><button type="button" id="bh-new">Hội thoại mới</button><button type="button" id="bh-close" aria-label="Đóng hỗ trợ">✕</button></header>
  <div class="bh-mode"></div><div class="bh-ticket" role="status" hidden></div>
  <div class="bh-messages" role="log" aria-label="Nội dung hội thoại" aria-live="polite"></div>
  <div class="bh-suggestions"></div><button type="button" id="bh-verify-toggle">Xác minh phiếu</button>
  <form class="bh-verify" hidden autocomplete="off"><input name="ticket" aria-label="Mã phiếu" placeholder="Mã phiếu" maxlength="50" required><input name="secret" type="password" aria-label="Mã tra cứu bí mật" placeholder="Mã tra cứu bí mật" maxlength="100" required><button>Xác minh</button></form>
  <div class="bh-status" role="status"></div><div class="bh-wait-actions"><button type="button" id="bh-cancel" hidden>Hủy chờ</button><button type="button" id="bh-retry" hidden>Thử lại</button></div>
  <form class="bh-compose"><textarea aria-label="Câu hỏi" placeholder="Bạn cần hỗ trợ gì?" rows="2" maxlength="1500" required></textarea><button>Gửi</button></form>`;
  document.body.append(launcher,panel);
  const find=s=>panel.querySelector(s);
  const status=text=>{find('.bh-status').textContent=text;};
  function waiting(value){busy=value;find('.bh-compose button').disabled=value;find('#bh-cancel').hidden=!value;}
  function ticketCard(card){activeTicket=card;find('.bh-ticket').hidden=!card;find('.bh-ticket').textContent=card?`Đang hỏi phiếu ${card.code} · ${card.status}`:'';}
  function bubble(text,user=false,citations=[]){
    const div=document.createElement('div');div.className='bh-bubble'+(user?' user':'');div.textContent=text;
    if(citations.length){const source=document.createElement('small');source.textContent='Căn cứ: '+citations.join('; ');div.append(source);}
    if(!user){const copy=document.createElement('button');copy.type='button';copy.textContent='Sao chép';copy.onclick=async()=>{try{await navigator.clipboard.writeText(text);status('Đã sao chép.');}catch{status('Bạn có thể chọn nội dung để sao chép.');}};div.append(copy);}
    find('.bh-messages').append(div);div.scrollIntoView({block:'nearest'});
  }
  function greeting(){const div=document.createElement('div');div.className='bh-bubble';div.textContent='Bạn cần tra tiến độ, hỏi về bảo hành hay hướng dẫn sử dụng?';find('.bh-messages').append(div);}
  async function call(path,method='POST',body,cap=capability,token=auth(),track=true){
    const headers={'Content-Type':'application/json','X-Chat-Session':cap};if(token)headers.Authorization=`Bearer ${token}`;
    const ctl=new AbortController();if(track)controller=ctl;const timer=setTimeout(()=>ctl.abort(),35000);
    try{
      const res=await fetch('/api/v1/chatbot'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body),signal:ctl.signal});
      const data=await res.json();if(!res.ok){const err=new Error(typeof data.detail==='string'?data.detail:'Bạn kiểm tra lại thông tin nhé.');err.status=res.status;throw err;}return data;
    }catch(error){if(error.name==='AbortError')throw new Error('Kết nối quá lâu. Bạn có thể thử lại.');if(error instanceof TypeError)throw new Error('Không kết nối được máy chủ. Bạn có thể thử lại.');throw error;}
    finally{clearTimeout(timer);if(controller===ctl)controller=null;}
  }
  function reset(){
    epoch++;flight++;if(controller)controller.abort();const old=capability;capability='';opening=null;lastQuestion=null;pendingQuestion=null;
    waiting(false);ticketCard(null);find('.bh-messages').replaceChildren();greeting();find('.bh-mode').textContent='';find('#bh-retry').hidden=true;
    find('.bh-verify').reset();find('.bh-verify').hidden=true;find('textarea').value='';find('.bh-suggestions').hidden=false;status('');
    document.getElementById('bh-ticket-tools')?.querySelector('output')?.remove();
    if(old)call('/sessions','DELETE',undefined,old,auth(),false).catch(()=>{});
  }
  async function begin(ticketId){
    if(capability)return;if(opening&&opening.epoch===epoch)return opening.promise;
    const generation=epoch;const pending=call('/sessions','POST',ticketId?{ticket_id:ticketId}:{}).then(data=>{
      if(generation!==epoch)return;capability=data.session;find('.bh-mode').textContent=data.mode;ticketCard(data.ticket);
    });opening={epoch:generation,promise:pending};try{await pending;}finally{if(opening?.promise===pending)opening=null;}
  }
  async function open(ticketId){if(ticketId)reset();panel.hidden=false;launcher.setAttribute('aria-expanded','true');find('textarea').focus();const generation=epoch;try{await begin(ticketId);}catch(error){if(generation===epoch)status(error.message);}}
  function close(){panel.hidden=true;launcher.setAttribute('aria-expanded','false');launcher.focus();}
  function accessError(error){if([401,403,404].includes(error.status)){reset();status(error.message);return true;}return false;}
  async function send(question,retry=false,showUser=true){
    if(busy||!question.trim())return;waiting(true);find('#bh-retry').hidden=true;find('.bh-suggestions').hidden=true;
    const generation=epoch, delivery=++flight, tokenAtStart=auth();
    // Each retry is a new read-only request; cancelled/late responses cannot enter this delivery.
    lastQuestion={message:question,request_id:crypto.randomUUID()};if(showUser&&!retry)bubble(question,true);
    find('textarea').value=question;status('Đang trả lời…');
    try{
      await begin();if(generation!==epoch||delivery!==flight)return;
      const data=await call('/messages','POST',lastQuestion);if(generation!==epoch||delivery!==flight)return;if(auth()!==tokenAtStart){reset();return;}
      bubble(data.answer,false,data.citations);find('.bh-mode').textContent=data.mode;ticketCard(data.ticket);status('');
      if(data.needs_verification){pendingQuestion=question;find('.bh-verify').hidden=false;find('.bh-verify [name="ticket"]').focus();}
      else{pendingQuestion=null;if(find('textarea').value===question)find('textarea').value='';}
    }catch(error){if(generation===epoch&&delivery===flight&&!accessError(error)){status(error.message);find('#bh-retry').hidden=false;}}
    finally{if(generation===epoch&&delivery===flight)waiting(false);}
  }
  function cancelWait(){
    if(!busy)return;flight++;if(controller)controller.abort();waiting(false);status('Đã hủy chờ. Bạn có thể thử lại.');find('#bh-retry').hidden=!lastQuestion;
    if(capability&&lastQuestion)call('/cancel','POST',{request_id:lastQuestion.request_id},capability,auth(),false).catch(()=>{});
  }
  const suggestions=publicPage?['Tra cứu tiến độ','Điều kiện bảo hành','Hướng dẫn gửi máy','Cách sử dụng']:['Tra cứu tiến độ','Tóm tắt lịch sử bảo hành','Soạn thông báo tiến độ bảo hành','Cách sử dụng'];
  for(const text of suggestions){const btn=document.createElement('button');btn.type='button';btn.textContent=text;btn.onclick=()=>send(text);find('.bh-suggestions').append(btn);}
  greeting();launcher.onclick=()=>panel.hidden?open():close();document.getElementById('open-support')?.addEventListener('click',()=>open());
  find('#bh-close').onclick=close;find('#bh-new').onclick=()=>{reset();open();};find('#bh-cancel').onclick=cancelWait;
  find('#bh-retry').onclick=()=>lastQuestion&&send(lastQuestion.message,true);
  find('.bh-compose').onsubmit=e=>{e.preventDefault();send(find('textarea').value);};
  find('textarea').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(e.target.value);}};
  panel.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
  find('#bh-verify-toggle').hidden=!publicPage;
  find('#bh-verify-toggle').onclick=()=>{find('.bh-verify').hidden=!find('.bh-verify').hidden;};
  find('.bh-verify').onsubmit=async e=>{
    e.preventDefault();if(busy)return;waiting(true);find('#bh-cancel').hidden=true;const generation=epoch;
    const form=e.target,payload={ticket_code:form.elements.ticket.value.trim(),secret:form.elements.secret.value};form.elements.secret.value='';
    let resume=null;
    try{await begin();if(generation!==epoch)return;const data=await call('/verify','POST',payload);if(generation!==epoch)return;
      if(activeTicket&&activeTicket.code!==data.ticket.code){find('.bh-messages').replaceChildren();greeting();}
      ticketCard(data.ticket);status('Đã xác minh phiếu.');form.hidden=true;resume=pendingQuestion;pendingQuestion=null;
    }catch(error){if(generation===epoch){ticketCard(null);find('.bh-messages').replaceChildren();greeting();status(error.message);}}
    finally{if(generation===epoch)waiting(false);}
    if(resume&&generation===epoch)await send(resume,false,false);
  };
  window.BaoHanhSupport={open,reset};window.addEventListener('storage',()=>{reset();close();});
  if(!publicPage) {
    const publicLink=document.createElement('a'); publicLink.href='/support'; publicLink.textContent='Hỗ trợ dành cho khách hàng'; publicLink.style.cssText='display:block;text-align:center;margin-top:16px;color:#4f46e5;font-weight:500;text-decoration:none;font-size:13.5px;'; document.getElementById('login-form')?.append(publicLink);
    let previous=auth();setInterval(()=>{const next=auth();if(next!==previous){reset();close();previous=next;}},300);
    // The ticket modal is reused across records; render actions against the current selection.
    const tools=document.createElement('div');tools.id='bh-ticket-tools';tools.style.cssText='display:flex;gap:8px;flex-wrap:wrap;margin:12px 0';
    const ask=document.createElement('button');ask.className='btn btn-secondary btn-sm';ask.textContent='Hỏi về phiếu này';ask.onclick=()=>open(state.selectedTicket?.id);tools.append(ask);
    for(const [label,method] of [['Cấp / đổi mã tra cứu','POST'],['Thu hồi mã tra cứu','DELETE']]) {
      const btn=document.createElement('button');btn.className='btn btn-secondary btn-sm';btn.textContent=label;
      btn.onclick=async()=>{const t=state.selectedTicket;if(!t)return;try {const data=await call(`/tickets/${t.id}/lookup-code`,method);let out=tools.querySelector('output');if(!out){out=document.createElement('output');tools.append(out);}out.textContent=method==='POST'?`Mã bí mật (chỉ hiện lần này, hiệu lực 30 ngày): ${data.secret}`:'Đã thu hồi mã.';}catch(error){status(error.message);open();}};tools.append(btn);
    }
    const modal=document.getElementById('ticket-modal');
    if(modal){const target=modal.firstElementChild;target?.prepend(tools);let ticket=null;new MutationObserver(()=>{if(ticket!==state.selectedTicket?.id||modal.style.display==='none'){tools.querySelector('output')?.remove();ticket=state.selectedTicket?.id;}const allowed=['MANAGER','RECEPTIONIST'].includes(state.session.user?.role);tools.querySelectorAll('button').forEach((b,i)=>{if(i && b.hidden===allowed)b.hidden=!allowed;});}).observe(modal,{attributes:true,subtree:true,childList:true});}
  }
})();
