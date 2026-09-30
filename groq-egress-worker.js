const MAX_BYTES = 4 * 1024 * 1024;
function unavailable(status = 503) {
  return new Response('{"error":"unavailable"}', {status, headers:{'content-type':'application/json','cache-control':'no-store'}});
}
async function boundedBody(body, limit) {
  if (!body) throw new Error('missing body');
  const reader = body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw new Error('body bound');
      chunks.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {result.set(chunk, offset); offset += chunk.byteLength;}
  return result;
}
export default {
 async fetch(request, env) {
  const path = new URL(request.url).pathname;
  if (request.method !== 'POST' || path !== '/transcribe') return unavailable(404);
  const authorization = request.headers.get('authorization') || '';
  if (!env.GROQ_KEY || authorization !== 'Bearer ' + env.GROQ_KEY) return unavailable(401);
  const length = Number(request.headers.get('content-length') || 0);
  if (!Number.isInteger(length) || length < 44 || length > MAX_BYTES || request.headers.get('content-type') !== 'audio/wav') return unavailable(413);
  let bytes;
  try { bytes = await boundedBody(request.body, MAX_BYTES); } catch { return unavailable(413); }
  if (bytes.byteLength > MAX_BYTES || bytes.byteLength < 44 || bytes.byteLength !== length) return unavailable(413);
  const view = new Uint8Array(bytes);
  const ascii = (start,end) => String.fromCharCode(...view.slice(start,end));
  if (ascii(0,4) !== 'RIFF' || ascii(8,12) !== 'WAVE') return unavailable(400);
  const form = new FormData();
  form.set('model','whisper-large-v3');
  form.set('file',new Blob([bytes],{type:'audio/wav'}),'dispatch.wav');
  let response;
  try {
   response = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
    method:'POST',redirect:'error',headers:{authorization:'Bearer '+env.GROQ_KEY},body:form,
    signal:AbortSignal.timeout(18000)
   });
   if (!response.ok) return unavailable(response.status === 429 ? 429 : 503);
   const raw = await boundedBody(response.body, 65536);
   const body = new TextDecoder('utf-8',{fatal:true}).decode(raw);
   const result = JSON.parse(body);
   if (typeof result.text !== 'string' || result.text.length > 16000) return unavailable();
   return new Response(JSON.stringify({text:result.text.trim()}),{
    headers:{'content-type':'application/json','cache-control':'no-store'}
   });
  } catch {return unavailable();}
 }
};
