const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture(pathname = '/', response = null) {
  const calls = {inserted:[],sent:0,results:[]};
  let sent=false, now=0;
  const location = {pathname,href:'https://chatgpt.com'+pathname};
  const element = (label, extra={}) => ({getClientRects:()=>[{}],getAttribute:name=>name==='aria-label'?label:null,textContent:label,...extra});
  const profile=element('Open profile menu');
  const editor=element('',{value:'',innerText:'',tagName:'DIV',focus(){}});
  const send=element('Send',{disabled:false,click(){calls.sent++;sent=true;location.pathname='/c/new-conversation';location.href='https://chatgpt.com/c/new-conversation';}});
  const code={textContent:JSON.stringify(response)};
  const document={
    querySelector:()=>null,
    querySelectorAll(selector){
      if(selector==='button')return [profile];
      if(selector==='main pre code')return sent && response ? [code] : [];
      if(selector==='main img')return [];
      if(selector.startsWith('#prompt-textarea'))return [editor];
      if(selector.startsWith('[data-testid="send-button"]'))return [send];
      throw Error('Unexpected selector: '+selector);
    },
    execCommand(command,_,text){calls.inserted.push(text);return true;}
  };
  const context=vm.createContext({document,location,URL,Date:{now:()=>now+=6000},
    setTimeout:callback=>callback(),chrome:{runtime:{async sendMessage(message){
      if(message.type==='state')return {cancelled:false};
      if(message.type==='result'){calls.results.push(message.result);return {ok:true};}
      throw Error('Unexpected message');
    }}}});
  const source=fs.readFileSync(__dirname+'/edge_extension/content.js','utf8').replace('  poll();','  globalThis.runForTest = run;');
  vm.runInContext(source,context);
  return {calls,run:context.runForTest};
}

test('web image request is sent once and is not forced to JSON/download mode',async()=>{
  const {calls,run}=fixture();
  await run({id:'image',prompt:'TẠO ẢNH theo prompt đã sửa',web:true,image:false});
  assert.equal(calls.sent,1);
  assert.deepEqual(calls.inserted,['TẠO ẢNH theo prompt đã sửa']);
  assert.equal(calls.results[0].presented,true);
  assert.equal(calls.results[0].image,undefined);
});

test('JSON draft returns the current conversation for later copy/image requests',async()=>{
  const {calls,run}=fixture('/',{image_prompt:'Review this prompt'});
  await run({id:'draft',prompt:'Write a draft only',web:false,image:false});
  assert.equal(calls.sent,1);
  assert.match(calls.inserted[0],/fenced json/);
  assert.equal(JSON.parse(calls.results[0].text).image_prompt,'Review this prompt');
  assert.equal(calls.results[0].conversation_url,'https://chatgpt.com/c/new-conversation');
});

test('changed conversation is rejected before typing or sending',async()=>{
  const {calls,run}=fixture('/c/some-other-chat');
  await assert.rejects(run({id:'copy',prompt:'Copy text',web:true,
    conversation_url:'https://chatgpt.com/c/original-chat'}),/quay lại cuộc trò chuyện/);
  assert.equal(calls.sent,0);
  assert.deepEqual(calls.inserted,[]);
});
