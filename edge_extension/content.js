(() => {
  if (globalThis.mandarinBridgeRunning) return;
  globalThis.mandarinBridgeRunning = true;
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = element => element && element.getClientRects().length;
  const findButton = names => [...document.querySelectorAll('button')].find(b => visible(b) && names.includes(b.getAttribute('aria-label') || b.textContent.trim()));
  const stopButton = () => [...document.querySelectorAll('button')].find(b => visible(b) && (/stop/i.test(b.getAttribute('data-testid')||'') || /^(Stop generating|Stop streaming|Dừng tạo|Dừng)$/i.test(b.getAttribute('aria-label')||'')));
  async function bridge(message) {
    const result = await chrome.runtime.sendMessage(message);
    if (result?.error) throw Error(result.error);
    return result;
  }
  async function run(job) {
    if (!findButton(['Open profile menu']) && !document.querySelector('[data-testid="accounts-profile-button"]')) throw Error('Tab ChatGPT chưa đăng nhập hoặc giao diện đã đổi. Kiểm tra tab hiện tại.');
    if (stopButton()) throw Error('Tab đang trả lời yêu cầu khác. Chờ xong rồi thử lại trong tool.');
    if (job.conversation_url) {
      const expected = new URL(job.conversation_url);
      if (expected.origin !== 'https://chatgpt.com' || !/^\/c\/[a-zA-Z0-9-]+$/.test(expected.pathname)) throw Error('Địa chỉ cuộc trò chuyện không hợp lệ.');
      if (location.pathname !== expected.pathname) throw Error('Hãy quay lại cuộc trò chuyện đã viết prompt trong tab Edge rồi nhấn lại nút. Chưa gửi yêu cầu.');
    } else if (location.pathname !== '/') {
      const fresh = findButton(['New chat','Cuộc trò chuyện mới']);
      if (!fresh) throw Error('Không tìm thấy nút New chat. Mở chat mới trong tab rồi thử lại.');
      fresh.click();
      for (let i=0;i<40 && location.pathname!=='/';i++) await wait(250);
      if (location.pathname !== '/') throw Error('Chưa mở được chat mới; chưa gửi yêu cầu.');
    }
    const beforeCodes = new Set([...document.querySelectorAll('main pre code')]);
    const beforeImages = new Set([...document.querySelectorAll('main img')].map(img => img.currentSrc || img.src));
    const editor = [...document.querySelectorAll('#prompt-textarea,#mobile-composer-prompt,[contenteditable="true"][role="textbox"],textarea[placeholder*="ChatGPT"]')].find(visible);
    if (!editor) throw Error('Không tìm thấy ô Ask ChatGPT. Không tự gửi lại yêu cầu.');
    if ((editor.value || editor.innerText || '').trim()) throw Error('Ô nhập đang có nội dung của bạn. Hãy gửi hoặc xóa nội dung đó trước khi chạy tool.');
    editor.focus();
    const prompt = job.prompt + (job.image || job.web ? '' : '\nReturn the complete JSON in one fenced json code block. No other text.');
    if (editor.tagName === 'TEXTAREA') {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(editor,prompt);
      editor.dispatchEvent(new Event('input',{bubbles:true}));
    } else if (!document.execCommand('insertText',false,prompt)) {
      throw Error('Không điền được ô nhập; chưa gửi yêu cầu.');
    }
    await wait(600);
    const send = [...document.querySelectorAll('[data-testid="send-button"],button[aria-label="Send"],button[aria-label="Send prompt"],button[aria-label="Send message"]')].find(visible) || findButton(['Send','Gửi']);
    if (!send || send.disabled) throw Error('Nút gửi chưa sẵn sàng; kiểm tra ô nhập trong Edge.');
    send.click(); // Exactly once; never retry a submitted prompt.
    if (job.web) {
      // The user watches/copies/downloads directly on ChatGPT. Do not scrape or download.
      return bridge({type:'result',result:{id:job.id,presented:true}});
    }
    let last = '', stable = Date.now();
    for (let i=0;i<1200;i++) {
      await wait(500);
      const state = await bridge({type:'state',id:job.id});
      if (state.cancelled) { stopButton()?.click(); return; }
      if (stopButton()) { stable=Date.now(); continue; }
      if (job.image) {
        const images = [...document.querySelectorAll('main img')].filter(img => img.naturalWidth>=400 && img.naturalHeight>=400 && !beforeImages.has(img.currentSrc || img.src));
        if (!images.length) continue;
        const img=images.at(-1), src=img.currentSrc || img.src;
        if (src!==last) {last=src;stable=Date.now();continue;}
        if (Date.now()-stable<5000) continue;
        const response=await fetch(src,{credentials:'include'});
        if (!response.ok) throw Error('Ảnh đã tạo nhưng chưa tải được file gốc. Tải ảnh trong Edge rồi lưu lại.');
        const blob=await response.blob();
        if (!blob.type.startsWith('image/')) throw Error('Phản hồi tải ảnh không hợp lệ.');
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(blob);});
        return bridge({type:'result',result:{id:job.id,image:data}});
      }
      const candidates=[...document.querySelectorAll('main pre code')].filter(code=>!beforeCodes.has(code));
      let text='';
      for (const candidate of candidates.reverse()) {
        try { const parsed=JSON.parse(candidate.textContent); if(parsed && !Array.isArray(parsed) && typeof parsed==='object'){text=candidate.textContent;break;} } catch {}
      }
      if (!text) continue;
      if (text!==last) {last=text;stable=Date.now();continue;}
      if(Date.now()-stable>=5000) return bridge({type:'result',result:{id:job.id,text,conversation_url:location.href}});
    }
    throw Error('ChatGPT chưa hoàn tất trước hạn chờ. Kiểm tra Edge trước khi thử lại.');
  }
  async function poll() {
    while (true) {
      try {
        const result=await bridge({type:'next'});
        if (result.job) {
          try {await run(result.job);}
          catch(error){await bridge({type:'result',result:{id:result.job.id,error:error.message}});}
        }
      } catch {}
      await wait(1000);
    }
  }
  poll();
})();
