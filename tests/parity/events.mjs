import {createServer} from 'node:http';

export async function createEventServer(paths,{validate}={}){
 const allowed=new Set(paths),streams=new Map(),failures=[];
 const server=createServer((request,response)=>{
  const url=new URL(request.url,'http://fixture');
  if(request.method!=='GET'||!allowed.has(url.pathname)){
   failures.push(`${request.method} ${url.pathname}`);response.writeHead(404);response.end();return;
  }
  try{
   if(validate)validate({url,request});
   else if(url.search)throw new Error('Undeclared stream query');
  }catch(error){failures.push(`${request.method} ${url.pathname}${url.search}: ${error.message}`);response.writeHead(400);response.end();return;}
  response.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-store'});
  response.write(': canonical fixture connected\n\n');
  if(!streams.has(url.pathname))streams.set(url.pathname,new Set());
  streams.get(url.pathname).add(response);
  response.on('close',()=>streams.get(url.pathname)?.delete(response));
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 return {
  origin:`http://127.0.0.1:${server.address().port}`,
  clients:path=>streams.get(path)?.size||0,
  emit(path,event,data){
   if(!allowed.has(path)||!event||/[\r\n]/.test(event))throw new Error('Invalid fixture event target');
   const clients=streams.get(path);
   if(!clients?.size)throw new Error(`No connected fixture stream: ${path}`);
   for(const response of clients)response.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  },
  assertRequests(){if(failures.length)throw new Error(`Unexpected SSE requests: ${failures.join(', ')}`);},
  async dispose(){for(const clients of streams.values())for(const response of clients)response.end();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));},
 };
}
