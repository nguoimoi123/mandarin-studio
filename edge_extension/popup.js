const status = document.querySelector('#status');
document.querySelector('#connect').onclick = async () => {
  try {
    const [tab] = await chrome.tabs.query({active:true, currentWindow:true});
    if (!tab?.url || new URL(tab.url).origin !== 'https://chatgpt.com') throw Error('Mở tab https://chatgpt.com đang đăng nhập trước.');
    const token = document.querySelector('#code').value.trim();
    if (token.length < 32) throw Error('Mã kết nối chưa đúng. Sao chép lại mã từ tool.');
    const response = await chrome.runtime.sendMessage({type:'attach', tabId:tab.id, token});
    if (response.error) throw Error(response.error);
    status.textContent = 'Đã kết nối. Quay lại tool để viết bài.';
  } catch (error) { status.textContent = error.message; }
};
document.querySelector('#disconnect').onclick = async () => {
  await chrome.runtime.sendMessage({type:'detach'}); status.textContent = 'Đã ngắt kết nối.';
};
