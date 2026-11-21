"""Genera index.html (autonomo, apribile con doppio clic) da data/ev_ita.json."""
import json

TEMPLATE = r"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><title>Auto elettriche in Italia (Quattroruote)</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font:13px system-ui,sans-serif;margin:16px;color:#1a1a1a}h1{font-size:18px;margin:0 0 4px}.sub{color:#666;margin-bottom:10px}
input{padding:6px 8px;width:260px;margin:0 10px 10px 0}label{margin-right:10px}
.wrap{overflow:auto;max-height:82vh;border:1px solid #ddd}table{border-collapse:collapse;width:100%}
th,td{padding:4px 8px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap}
th{position:sticky;top:0;background:#f3f4f6;cursor:pointer;user-select:none}th .u{display:block;font-weight:400;color:#777;font-size:11px}
td.t,th.t{text-align:left}tr:hover td{background:#f8fafc}.calc{color:#6b7280;font-style:italic}.na{color:#b91c1c}tr.esa td{color:#9a6700;background:#fffbeb}
</style></head><body>
<h1>Auto elettriche (BEV) – listino Quattroruote</h1>
<div class="sub">Aggiornato al __DATE__ · __N__ allestimenti. Autonomia in corsivo = calcolata (capacità/consumo×100). Righe gialle = esaurimento scorte.</div>
<input id="q" placeholder="Filtra (es. tesla, suv, 2026)…"><label><input type="checkbox" id="ne" style="width:auto;margin:0 4px 0 0">nascondi esauriti</label>
<div class="wrap"><table id="t"><thead></thead><tbody></tbody></table></div>
<script>
const DATA=__DATA__;
const cols=[["modello","","Modello",1],["allestimento","","Allestimento",1],["tipo","","Tipo",1],["posti","","Posti"],["cap","kWh","Capacità"],["h","cm","H"],["w","cm","W"],["l","cm","L"],["m","kg","M"],["pomol","cv","P omol"],["ppeak","cv","P peak"],["cons","kWh/100km","Consumo"],["vmax","km/h","V max"],["prezzo","€","Prezzo"],["anno","","Anno"],["autonomia","km","Autonomia"],["stato","","Stato",1],["url","","Link",1]];
let sk="prezzo",sd=1;const th=document.querySelector("#t thead");
th.innerHTML="<tr>"+cols.map(c=>`<th class="${c[3]?'t':''}" data-k="${c[0]}">${c[2]}<span class="u">${c[1]||"&nbsp;"}</span></th>`).join("")+"</tr>";
th.onclick=e=>{const k=e.target.closest("th")?.dataset.k;if(!k)return;sd=sk==k?-sd:1;sk=k;render()};
document.getElementById("q").oninput=render;document.getElementById("ne").onchange=render;
function render(){const q=document.getElementById("q").value.toLowerCase(),ne=document.getElementById("ne").checked;
 let r=DATA.filter(d=>JSON.stringify(d).toLowerCase().includes(q)&&!(ne&&d.stato!="disponibile"));
 r.sort((a,b)=>{const x=a[sk],y=b[sk];if(x==null)return 1;if(y==null)return -1;return(x>y?1:x<y?-1:0)*sd});
 document.querySelector("#t tbody").innerHTML=r.map(d=>`<tr class="${d.stato!="disponibile"?"esa":""}">`+cols.map(c=>{const v=d[c[0]];
  if(v==null||v==="")return '<td class="na">n.d.</td>';
  if(c[0]=="url")return `<td class="t"><a href="${v}" target="_blank" rel="noopener">scheda</a></td>`;
  if(c[0]=="autonomia")return `<td class="${d.autonomia_fonte=="calcolata"?"calc":""}">${v}</td>`;
  if(c[0]=="prezzo")return `<td>${v.toLocaleString("it-IT")}</td>`;
  return `<td class="${c[3]?'t':''}">${typeof v=="number"?String(v).replace(".",","):v}</td>`}).join("")+"</tr>").join("")}
render();
</script></body></html>"""


def build(src="data/ev_ita.json", out="index.html"):
    j = json.load(open(src, encoding="utf-8"))
    html = (TEMPLATE.replace("__DATA__", json.dumps(j["righe"], ensure_ascii=False))
            .replace("__DATE__", j["aggiornato"]).replace("__N__", str(len(j["righe"]))))
    open(out, "w", encoding="utf-8").write(html)


if __name__ == "__main__":
    build()
