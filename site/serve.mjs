import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
const root=path.resolve('site-build');
const base=`/${(process.env.SITE_BASE_PATH||'ffmpeg-v2').replace(/^\/+|\/+$/g,'')}/`;
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'application/javascript; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.json':'application/json; charset=utf-8','.xml':'application/xml; charset=utf-8','.txt':'text/plain; charset=utf-8'};
const server=http.createServer((req,res)=>{
  let pathname;try{pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}catch{res.writeHead(400).end();return;}
  if(pathname==='/'){res.writeHead(302,{Location:base}).end();return;}
  if(!pathname.startsWith(base)||pathname.includes('\0')){res.writeHead(404).end('Not found');return;}
  let file=path.resolve(root,pathname.slice(base.length));
  if(file!==root&&!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
  if(fs.existsSync(file)&&fs.statSync(file).isDirectory())file=path.join(file,'index.html');
  if(!fs.existsSync(file)){res.writeHead(404,{'Content-Type':'text/html; charset=utf-8'}).end(fs.readFileSync(path.join(root,'404.html')));return;}
  res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','X-Content-Type-Options':'nosniff'});fs.createReadStream(file).pipe(res);
});
server.listen(Number(process.env.PORT||4173),'127.0.0.1',()=>console.log('Preview: http://127.0.0.1:4173'+base));
