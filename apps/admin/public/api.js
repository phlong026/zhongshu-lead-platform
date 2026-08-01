export const API='/api/v1';
export async function request(path,options={}){
  const headers={...(options.headers||{})};
  if(options.body!==undefined && !(options.body instanceof FormData))headers['Content-Type']='application/json';
  const response=await fetch(API+path,{...options,headers,credentials:'include'});
  let payload={};try{payload=await response.json()}catch{payload={message:response.statusText}}
  if(!response.ok||payload.code!=='OK'){const error=new Error(payload.message||'请求失败');error.code=payload.code;error.details=payload.details;error.status=response.status;throw error}
  return payload.data;
}
export function query(params={}){const q=new URLSearchParams();Object.entries(params).forEach(([k,v])=>{if(v!==undefined&&v!==null&&v!=='')q.set(k,v)});const s=q.toString();return s?'?'+s:''}
