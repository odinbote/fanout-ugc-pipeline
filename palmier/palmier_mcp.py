"""Minimal MCP streamable-HTTP client for Palmier Pro (127.0.0.1:19789/mcp)."""
import json, sys, requests
URL="http://127.0.0.1:19789/mcp"
class Palmier:
    def __init__(self):
        self.sid=None; self.n=0; self.proto="2025-06-18"
        r=self._post({"jsonrpc":"2.0","id":self._id(),"method":"initialize","params":{"protocolVersion":self.proto,"capabilities":{},"clientInfo":{"name":"claude-code","version":"1.0"}}})
        self.proto=r["result"].get("protocolVersion",self.proto)
        self._post({"jsonrpc":"2.0","method":"notifications/initialized"},expect=False)
    def _id(self): self.n+=1; return self.n
    def _post(self,msg,expect=True):
        h={"Content-Type":"application/json","Accept":"application/json, text/event-stream","MCP-Protocol-Version":self.proto}
        if self.sid: h["Mcp-Session-Id"]=self.sid
        r=requests.post(URL,headers=h,json=msg,timeout=120,stream=True)
        if r.headers.get("mcp-session-id"): self.sid=r.headers["mcp-session-id"]
        if not expect: return None
        ct=r.headers.get("content-type","").split(";")[0]
        if ct=="application/json": return r.json()
        out=None
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    m=json.loads(line[5:].strip())
                    if "id" in m and m["id"]==msg.get("id"): out=m
                except Exception: pass
        return out
    def tools(self): return self._post({"jsonrpc":"2.0","id":self._id(),"method":"tools/list","params":{}})["result"]["tools"]
    def call(self,name,args=None):
        r=self._post({"jsonrpc":"2.0","id":self._id(),"method":"tools/call","params":{"name":name,"arguments":args or {}}})
        return r.get("result",r)
if __name__=="__main__":
    p=Palmier()
    if len(sys.argv)>1:
        print(json.dumps(p.call(sys.argv[1],json.loads(sys.argv[2]) if len(sys.argv)>2 else {}),indent=1)[:4000])
    else:
        for t in p.tools():
            props=list((t.get("inputSchema") or {}).get("properties",{}).keys())
            print(f"- {t['name']}: {(t.get('description') or '')[:110]}  args={props}")
