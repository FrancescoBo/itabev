"""Genera index.html (autonomo, apribile con doppio clic) da data/ev_ita.json."""
import json
import re

TEMPLATE = r"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><title>Auto elettriche in Italia (Quattroruote)</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{box-sizing:border-box}
body{font:13px system-ui,sans-serif;margin:16px;color:#1a1a1a}
h1{font-size:18px;margin:0 0 4px}.sub{color:#666;margin-bottom:12px}
.bar{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;margin-bottom:8px}
.bar label{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
input[type=text]{padding:6px 8px;width:220px}
select{padding:4px}
.price{display:flex;align-items:flex-end;gap:16px;margin:4px 0 12px}
.price .lab{min-width:230px;line-height:1.7}.price b{font-weight:600}
.pbox{width:min(620px,62vw)}#curve{width:100%;height:64px;display:block}
.range{position:relative;height:22px;width:100%}
.range .track{position:absolute;left:0;right:0;top:9px;height:4px;background:#d1d5db;border-radius:2px}
.range .fill{position:absolute;top:9px;height:4px;background:#2563eb;border-radius:2px}
.range input{position:absolute;left:0;top:0;width:100%;height:22px;margin:0;background:none;pointer-events:none;-webkit-appearance:none;appearance:none}
.range input::-webkit-slider-thumb{pointer-events:auto;-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:#fff;border:2px solid #2563eb;cursor:pointer}
.range input::-moz-range-thumb{pointer-events:auto;width:12px;height:12px;border-radius:50%;background:#fff;border:2px solid #2563eb;cursor:pointer}
.range input::-webkit-slider-runnable-track{background:none}.range input::-moz-range-track{background:none}
.tabs{display:flex;gap:4px;border-bottom:1px solid #ddd;margin:6px 0 10px}
.tabs button{padding:7px 16px;border:1px solid #ddd;border-bottom:none;background:#f3f4f6;cursor:pointer;border-radius:6px 6px 0 0;font:inherit}
.tabs button.on{background:#fff;font-weight:600;position:relative;top:1px}
.count{color:#555;margin-left:auto}
.wrap{overflow:auto;max-height:76vh;border:1px solid #ddd}table{border-collapse:collapse;width:100%}
th,td{padding:4px 8px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap}
th{position:sticky;top:0;background:#f3f4f6;cursor:pointer;user-select:none}th .u{display:block;font-weight:400;color:#777;font-size:11px}
td.t,th.t{text-align:left}tr:hover td{background:#f8fafc}.calc{color:#6b7280;font-style:italic}.na{color:#b91c1c}tr.esa td{color:#9a6700;background:#fffbeb}
.axes{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;margin-bottom:8px}
#cv{width:100%;height:68vh;min-height:380px;border:1px solid #ddd;display:block;background:#fff}
#tip{position:fixed;pointer-events:none;background:#111c;color:#fff;padding:6px 8px;border-radius:5px;font-size:12px;display:none;max-width:320px;line-height:1.35}
.hint{color:#666;margin-top:6px}
</style></head><body>
<h1>Auto elettriche (BEV) – listino Quattroruote</h1>
<div class="sub">Aggiornato al __DATE__ · __N__ allestimenti in archivio. Autonomia in corsivo = calcolata (capacità batteria/consumo×100). Righe gialle = esaurimento scorte.</div>

<div class="bar">
 <input type="text" id="q" placeholder="Filtra (es. tesla, suv, 2026)…">
 <label><input type="checkbox" id="ne">nascondi esauriti</label>
 <label><input type="checkbox" id="np" checked>nascondi senza prezzo (fuori listino)</label>
 <label><input type="checkbox" id="base">solo allestimento base
  <select id="bmode"><option value="m">il più economico di ogni modello</option><option value="a">il più economico per modello e nome allestimento</option></select></label>
 <span class="count" id="cnt"></span>
</div>
<div class="price">
 <div class="lab"><b id="plab"></b></div>
 <div class="pbox"><canvas id="curve"></canvas>
  <div class="range"><div class="track"></div><div class="fill" id="fill"></div>
   <input type="range" id="lo"><input type="range" id="hi"></div></div>
</div>

<div class="tabs"><button id="tb1" class="on">Tabella</button><button id="tb2">Grafico</button></div>

<div id="v1"><div class="wrap"><table id="t"><thead></thead><tbody></tbody></table></div></div>

<div id="v2" style="display:none">
 <div class="axes">
  <label>Asse X <select id="ax"></select></label>
  <label>Asse Y <select id="ay"></select></label>
  <button id="sw" type="button">⇄ scambia</button>
 </div>
 <canvas id="cv"></canvas>
 <div class="hint" id="ghint"></div>
</div>
<div id="tip"></div>

<script>
const DATA=__DATA__;
const COLS=[
 {k:"modello",l:"Modello",t:1},{k:"allestimento",l:"Allestimento",t:1},{k:"tipo",l:"Tipo",t:1},
 {k:"posti",l:"Posti"},{k:"cap",l:"Capacità batteria",u:"kWh"},{k:"vmax",l:"V max",u:"km/h"},
 {k:"cons",l:"Consumo",u:"kWh/100km"},{k:"autonomia",l:"Autonomia",u:"km"},{k:"prezzo",l:"Prezzo",u:"€"},
 {k:"h",l:"H",u:"cm"},{k:"w",l:"W",u:"cm"},{k:"l",l:"L",u:"cm"},{k:"m",l:"M",u:"kg"},
 {k:"pomol",l:"P omol",u:"cv"},{k:"ppeak",l:"P peak",u:"cv"},{k:"anno",l:"Anno"},
 {k:"stato",l:"Stato",t:1},{k:"url",l:"Link",t:1}];
const NUM=COLS.filter(c=>!c.t);
DATA.forEach(d=>{d._s=(d.modello+" "+d.allestimento+" "+(d.tipo||"")+" "+d.anno+" "+d.stato).toLowerCase()});
const $=id=>document.getElementById(id);
const fmt=(v,k)=>v==null?"":(k=="prezzo"?v.toLocaleString("it-IT"):(k=="anno"?String(v):v.toLocaleString("it-IT",{maximumFractionDigits:2})));

/* ---- slider prezzo (lineare; il massimo = "150.000 € e oltre", senza limite superiore) ---- */
const CAP=150000,SP=DATA.map(d=>d.prezzo).filter(v=>v!=null),PMIN=Math.floor(Math.min(...SP)/500)*500;
const lo=$("lo"),hi=$("hi"),eur=v=>v.toLocaleString("it-IT")+" €";
for(const s of [lo,hi]){s.min=PMIN;s.max=CAP;s.step=500}
lo.value=PMIN;hi.value=CAP;let PLO=PMIN,PHI=Infinity;
const OVER=SP.filter(v=>v>CAP).length;
function drawHist(){
 const c=$("curve"),dpr=window.devicePixelRatio||1,W=c.clientWidth,H=c.clientHeight;c.width=W*dpr;c.height=H*dpr;
 const g=c.getContext("2d");g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);
 const BIN=2500,n=Math.ceil((CAP-PMIN)/BIN),cnt=new Array(n).fill(0);
 SP.forEach(v=>{if(v<=CAP)cnt[Math.min(n-1,Math.floor((v-PMIN)/BIN))]++});
 const mx=Math.max(...cnt),pad=8,bw=(W-2*pad)/n;
 cnt.forEach((k,i)=>{const p0=PMIN+i*BIN,sel=p0+BIN>PLO&&p0<(PHI===Infinity?1e9:PHI),h=k/mx*(H-18);
  g.fillStyle=sel?"rgba(37,99,235,.55)":"#d1d5db";g.fillRect(pad+i*bw+.5,H-3-h,bw-1,h)});
 g.fillStyle="#555";g.font="11px system-ui";g.textBaseline="top";
 g.textAlign="left";g.fillText("allestimenti per fascia di prezzo (barre da "+BIN.toLocaleString("it-IT")+" €)",pad,0);
 g.textAlign="right";g.fillText("oltre "+eur(CAP)+": "+OVER+" allestimenti",W-pad,0);
}
function sliders(e){
 if(+lo.value>+hi.value){ if(e&&e.target===lo)lo.value=hi.value; else hi.value=lo.value }
 const a=(+lo.value-PMIN)/(CAP-PMIN)*100,b=(+hi.value-PMIN)/(CAP-PMIN)*100;
 PLO=+lo.value;PHI=+hi.value>=CAP?Infinity:+hi.value;
 $("fill").style.left=a+"%";$("fill").style.right=(100-b)+"%";
 $("plab").textContent="Prezzo: "+(PLO>=CAP?"da ":"")+eur(PLO)+(PLO>=CAP?" in su":" – "+(PHI===Infinity?"oltre "+eur(CAP)+" (nessun limite)":eur(PHI)));
 drawHist();update();
}
lo.oninput=hi.oninput=sliders;

/* ---- filtri ---- */
function filtered(){
 const q=$("q").value.toLowerCase().trim();
 let r=DATA;
 if($("ne").checked)r=r.filter(d=>d.stato==="disponibile");
 if($("np").checked)r=r.filter(d=>d.prezzo!=null);
 if($("base").checked){
  const key=$("bmode").value=="m"?(d=>d.modello):(d=>d.modello+"|"+d.allestimento), best=new Map();
  for(const d of r){ if(d.prezzo==null)continue; const k=key(d),b=best.get(k); if(!b||d.prezzo<b.prezzo)best.set(k,d) }
  r=[...best.values()];
 }
 const narrowed=+lo.value>PMIN||+hi.value<CAP;
 r=r.filter(d=>d.prezzo==null?!narrowed:(d.prezzo>=PLO&&d.prezzo<=PHI));
 if(q)r=r.filter(d=>d._s.includes(q));
 return r;
}

/* ---- tabella ---- */
let sk="prezzo",sd=1;
const th=document.querySelector("#t thead");
th.innerHTML="<tr>"+COLS.map(c=>`<th class="${c.t?'t':''}" data-k="${c.k}">${c.l}<span class="u">${c.u||"&nbsp;"}</span></th>`).join("")+"</tr>";
th.onclick=e=>{const k=e.target.closest("th")?.dataset.k;if(!k)return;sd=sk==k?-sd:1;sk=k;renderTable(filtered())};
function renderTable(r){
 r=r.slice().sort((a,b)=>{const x=a[sk],y=b[sk];if(x==null)return 1;if(y==null)return -1;return(x>y?1:x<y?-1:0)*sd});
 document.querySelector("#t tbody").innerHTML=r.map(d=>`<tr class="${d.stato!="disponibile"?"esa":""}">`+COLS.map(c=>{const v=d[c.k];
  if(v==null||v==="")return '<td class="na">n.d.</td>';
  if(c.k=="url")return `<td class="t"><a href="${v}" target="_blank" rel="noopener">scheda</a></td>`;
  if(c.k=="autonomia")return `<td class="${d.autonomia_fonte=="calcolata"?"calc":""}">${v}</td>`;
  if(c.t)return `<td class="t">${v}</td>`;
  return `<td>${fmt(v,c.k)}</td>`}).join("")+"</tr>").join("");
}

/* ---- grafico ---- */
const ax=$("ax"),ay=$("ay");
for(const s of [ax,ay])s.innerHTML=NUM.map(c=>`<option value="${c.k}">${c.l}${c.u?" ("+c.u+")":""}</option>`).join("");
ax.value="autonomia";ay.value="prezzo";
$("sw").onclick=()=>{const t=ax.value;ax.value=ay.value;ay.value=t;drawChart(filtered())};
ax.onchange=ay.onchange=()=>drawChart(filtered());
const cv=$("cv"),tip=$("tip");let pts=[];
function nice(min,max,n){const span=(max-min)||1,s0=span/n,mag=Math.pow(10,Math.floor(Math.log10(s0))),e=s0/mag,
 st=mag*(e>=7.5?10:e>=3.5?5:e>=1.5?2:1),out=[];for(let v=Math.ceil(min/st)*st;v<=max+st*1e-9;v+=st)out.push(+v.toFixed(10));return out}
function drawChart(r){
 if($("v2").style.display=="none")return;
 const xk=ax.value,yk=ay.value,cx=NUM.find(c=>c.k==xk),cy=NUM.find(c=>c.k==yk);
 const dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;
 cv.width=W*dpr;cv.height=H*dpr;const g=cv.getContext("2d");g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);
 const ok=r.filter(d=>d[xk]!=null&&d[yk]!=null),skipped=r.length-ok.length;
 $("ghint").textContent=`${ok.length} punti`+(skipped?` (${skipped} allestimenti senza valore per un asse, esclusi)`:"")+" · passa sopra un punto per i dettagli, clic per aprire la scheda. I punti rispettano i filtri qui sopra. Gialli = esaurimento scorte.";
 const m={l:70,r:20,t:16,b:52};pts=[];
 if(!ok.length){g.fillStyle="#666";g.font="14px system-ui";g.fillText("Nessun dato con i filtri attuali",m.l,60);return}
 let x0=Math.min(...ok.map(d=>d[xk])),x1=Math.max(...ok.map(d=>d[xk])),y0=Math.min(...ok.map(d=>d[yk])),y1=Math.max(...ok.map(d=>d[yk]));
 const px=((x1-x0)||Math.abs(x0)||1)*.05,py=((y1-y0)||Math.abs(y0)||1)*.05;x0-=px;x1+=px;y0-=py;y1+=py;
 const X=v=>m.l+(v-x0)/(x1-x0)*(W-m.l-m.r),Y=v=>H-m.b-(v-y0)/(y1-y0)*(H-m.t-m.b);
 g.font="11px system-ui";g.strokeStyle="#eee";g.fillStyle="#555";g.lineWidth=1;
 g.textAlign="center";g.textBaseline="top";
 for(const v of nice(x0,x1,Math.max(3,Math.floor(W/90)))){const x=X(v);g.beginPath();g.moveTo(x,m.t);g.lineTo(x,H-m.b);g.stroke();g.fillText(fmt(v,xk),x,H-m.b+5)}
 g.textAlign="right";g.textBaseline="middle";
 for(const v of nice(y0,y1,Math.max(3,Math.floor(H/55)))){const y=Y(v);g.beginPath();g.moveTo(m.l,y);g.lineTo(W-m.r,y);g.stroke();g.fillText(fmt(v,yk),m.l-6,y)}
 g.strokeStyle="#999";g.strokeRect(m.l,m.t,W-m.l-m.r,H-m.t-m.b);
 g.fillStyle="#222";g.font="12px system-ui";g.textAlign="center";g.textBaseline="bottom";
 g.fillText(cx.l+(cx.u?" ("+cx.u+")":""),m.l+(W-m.l-m.r)/2,H-6);
 g.save();g.translate(14,m.t+(H-m.t-m.b)/2);g.rotate(-Math.PI/2);g.textBaseline="top";g.fillText(cy.l+(cy.u?" ("+cy.u+")":""),0,0);g.restore();
 for(const d of ok){const x=X(d[xk]),y=Y(d[yk]);pts.push({x,y,d});
  g.beginPath();g.arc(x,y,4,0,6.2832);g.fillStyle=d.stato=="disponibile"?"rgba(37,99,235,.55)":"rgba(217,119,6,.75)";g.fill();g.strokeStyle="rgba(255,255,255,.8)";g.lineWidth=.8;g.stroke()}
}
function near(e){const b=cv.getBoundingClientRect(),x=e.clientX-b.left,y=e.clientY-b.top;let best=null,bd=100;
 for(const p of pts){const dd=(p.x-x)**2+(p.y-y)**2;if(dd<bd){bd=dd;best=p}}return best}
cv.onmousemove=e=>{const p=near(e);if(!p){tip.style.display="none";cv.style.cursor="default";return}
 const d=p.d,cx=NUM.find(c=>c.k==ax.value),cy=NUM.find(c=>c.k==ay.value);
 tip.innerHTML=`<b>${d.modello}</b><br>${d.allestimento}<br>${cx.l}: ${fmt(d[ax.value],ax.value)} ${cx.u||""}<br>${cy.l}: ${fmt(d[ay.value],ay.value)} ${cy.u||""}`;
 tip.style.display="block";tip.style.left=Math.min(e.clientX+14,innerWidth-340)+"px";tip.style.top=(e.clientY+14)+"px";cv.style.cursor="pointer"};
cv.onmouseleave=()=>tip.style.display="none";
cv.onclick=e=>{const p=near(e);if(p)window.open(p.d.url,"_blank","noopener")};

/* ---- schede e aggiornamento ---- */
function tab(n){$("v1").style.display=n==1?"":"none";$("v2").style.display=n==2?"":"none";$("tb1").className=n==1?"on":"";$("tb2").className=n==2?"on":"";update()}
$("tb1").onclick=()=>tab(1);$("tb2").onclick=()=>tab(2);
function update(){const r=filtered();$("cnt").textContent=`${r.length} allestimenti mostrati su ${DATA.length}`;
 if($("v1").style.display!="none")renderTable(r);else drawChart(r)}
for(const id of ["q","ne","np","base","bmode"])$(id).oninput=$(id).onchange=update;
addEventListener("resize",()=>{drawHist();if($("v2").style.display!="none")drawChart(filtered())});
sliders();
</script></body></html>"""


def _nome_da_url(url):
    n = re.sub(r"-\d{9,}$", "", url.rstrip("/").rsplit("/", 1)[-1]).replace("-", " ")
    return n[:1].upper() + n[1:]


def pulisci(rows):
    """Toglie testi spuri tipo 'quattroruote.it/listino/...' (anche dall'URL) e i doppioni che ne derivano."""
    out = {}
    for r in rows:
        marca, modello, ultimo = r["url"].split("/auto/")[1].split("/")[:3]
        if "quattroruote" in modello.lower():
            modello = re.sub(r"^quattroruoteitlistino" + re.escape(marca), "", modello) or marca
            if "quattroruote" in modello.lower():
                modello = marca
            r["url"] = f"https://www.quattroruote.it/auto/{marca}/{modello}/{ultimo}"
        if "quattroruote" in r["modello"].lower() or "/" in r["modello"]:
            r["modello"] = marca.replace("-", " ").upper() + " " + modello
        if "quattroruote" in r["allestimento"].lower() or "/" in r["allestimento"]:
            r["allestimento"] = _nome_da_url(r["url"])
        out.setdefault(ultimo, r)          # stessa versione = stesso codice finale: tieni una sola riga
    return list(out.values())


def build(src="data/ev_ita.json", out="index.html"):
    j = json.load(open(src, encoding="utf-8"))
    html = (TEMPLATE.replace("__DATA__", json.dumps(pulisci(j["righe"]), ensure_ascii=False, separators=(",", ":")))
            .replace("__DATE__", j["aggiornato"]).replace("__N__", str(len(j["righe"]))))
    open(out, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    build()
