const base = 'http://127.0.0.1:8765';
async function request(path, data) {
  const config = await chrome.storage.session.get(['token']);
  if (!config.token) throw Error('Chưa ghép nối với tool.');
  const response = await fetch(base+path, {method:data?'POST':'GET', headers:{'Authorization':'Bearer '+config.token,'Content-Type':'application/json'}, body:data?JSON.stringify(data):undefined});
  if (!response.ok) throw Error('Không kết nối được tool ('+response.status+'). Sao chép lại mã kết nối nếu tool vừa khởi động lại.');
  return response.json();
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  (async () => {
    if (message.type === 'attach' && !sender.tab) {
      const tab = await chrome.tabs.get(message.tabId);
      if (new URL(tab.url).origin !== 'https://chatgpt.com') throw Error('Chỉ kết nối tab ChatGPT.');
      await chrome.storage.session.set({token:message.token, tabId:message.tabId});
      await request('/state?id=');
      await chrome.scripting.executeScript({target:{tabId:message.tabId}, files:['content.js']});
      return {ok:true};
    }
    if (message.type === 'detach' && !sender.tab) { await chrome.storage.session.clear(); return {ok:true}; }
    const config = await chrome.storage.session.get(['tabId']);
    if (sender.tab?.id !== config.tabId || new URL(sender.tab.url).origin !== 'https://chatgpt.com') throw Error('Tab chưa ghép nối.');
    if (message.type === 'next') return request('/next');
    if (message.type === 'state') return request('/state?id='+encodeURIComponent(message.id));
    if (message.type === 'result') return request('/result', message.result);
    throw Error('Yêu cầu không hợp lệ.');
  })().then(reply, error => reply({error:error.message}));
  return true;
});
