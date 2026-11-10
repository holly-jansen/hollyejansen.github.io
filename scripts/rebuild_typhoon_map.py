#!/usr/bin/env python3
"""Regenerate the Hugo Blox 1998–2019 Philippine storm exposure map.

Inputs: final 32-column, municipality-by-storm CSV.gz and the checked-in
legacy map template (for the unchanged geometry and track-path assets).
The generated map is self-contained and does not load the original CSV over the web.
"""
import argparse
import base64
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

METRICS = {
    'wind_squared_peak_kn2': ('Primary: population-weighted wind²', 'Population-weighted peak wind² (knots²)'),
    'peak_rms_wind_kn': ('RMS peak wind (knots)', 'Population-weighted RMS of local peak winds (knots)'),
    'wind_cubed_peak_kn3': ('Population-weighted wind³', 'Population-weighted peak wind³ (knots³)'),
    'wind_cumulative_squared_kn2_hours': ('Cumulative wind² × hours', 'Cumulative wind² × hours (knots²·h)'),
    'wind_cumulative_cubed_kn3_hours': ('Cumulative wind³ × hours', 'Cumulative wind³ × hours (knots³·h)'),
    'wind_squared_anomaly_prior5yr_difference_kn2': ('Five-year wind² anomaly: difference', 'Wind² minus prior-five-year mean (knots²)'),
    'wind_squared_anomaly_prior5yr_z': ('Five-year wind² anomaly: z-score', 'Wind² anomaly relative to prior-five-year standard deviation (z)'),
    'wind_squared_peak_kn2_short_outer_tail': ('Sensitivity: shorter outer tail', 'Wind², shorter outer-decay assumption (knots²)'),
    'wind_squared_peak_kn2_long_outer_tail': ('Sensitivity: longer outer tail', 'Wind², longer outer-decay assumption (knots²)'),
    'wind_squared_peak_kn2_fixed2000': ('Sensitivity: fixed 2000 population', 'Wind², year-2000 population weights (knots²)'),
    'wind_squared_peak_kn2_800km_reference': ('Legacy 800-km reference (comparison)', 'Wind², legacy 800-km reference (knots²)'),
}
DIVERGING = ['wind_squared_anomaly_prior5yr_z', 'wind_squared_anomaly_prior5yr_difference_kn2']

def extract_json(s, start, end):
    m = re.search(re.escape(start) + r'(.*?)' + re.escape(end),s,re.S)
    if not m: raise RuntimeError('Missing template data block: ' + start)
    return json.loads(m.group(1))

def fix_bad_name(s):
    if 'Ã' in s:
        try: return s.encode('latin1').decode('utf8')
        except UnicodeError: pass
    return s

def jsset_once(s,pattern,replacement,flags=re.S):
    ns,n = re.subn(pattern,lambda m: replacement,s,count=1,flags=flags)
    if n!=1: raise RuntimeError('Template mismatch: '+pattern)
    return ns

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',default='PH_wind_1998_2019.csv.gz')
    ap.add_argument('--template',default='scripts/map_template.html')
    ap.add_argument('--out',default='static/maps/typhoons/index.html')
    args=ap.parse_args()
    source=Path(args.source); templ=Path(args.template); out=Path(args.out)
    s=templ.read_text(encoding='utf-8')
    geos=extract_json(s,'const GEO=',';\nconst STORMS=')
    storms=extract_json(s,'const STORMS=',';\nconst TRACKS=')
    assert len(geos)==1627 and len(storms)==529
    keys=[g['k'] for g in geos]; ids=[t[0] for t in storms]
    assert len(keys)==len(set(keys)) and len(ids)==len(set(ids))
    df=pd.read_csv(source,compression='gzip',low_memory=False)
    assert df.shape==(860683,32),df.shape
    assert set(df['municipality_polygon_key'])==set(keys)
    assert set(df['storm_id'])==set(ids)
    assert not df.duplicated(['municipality_polygon_key','storm_id']).any()
    gid={k:i for i,k in enumerate(keys)}; sid={k:i for i,k in enumerate(ids)}
    df['_gi']=df['municipality_polygon_key'].map(gid)
    df['_si']=df['storm_id'].map(sid)
    assert df['_gi'].notna().all() and df['_si'].notna().all()
    df.sort_values(['_si','_gi'],inplace=True,kind='stable')
    assert (df['_si'].to_numpy(np.int32)*len(keys)+df['_gi'].to_numpy(np.int32)==np.arange(len(df))).all()
    # Keep stable master keys and storm IDs. Update corrupted UTF-8 map labels only.
    for g in geos:g['n']=fix_bad_name(g['n'])
    s=jsset_once(s,r'const GEO=\[.*?\];\s*const STORMS=',
                 'const GEO='+json.dumps(geos,ensure_ascii=False,separators=(',',':'))+';\nconst STORMS=')
    encoded={}; bins={}; summaries={}
    for key in METRICS:
        if key=='peak_rms_wind_kn':
            a=np.sqrt(np.maximum(0,df['wind_squared_peak_kn2'].to_numpy(dtype=np.float64)))
        else:a=df[key].to_numpy(dtype=np.float64,copy=False)
        f=np.asarray(a,dtype='<f4')
        filename = out.parent/'data'/f'{key}.bin'
        filename.parent.mkdir(parents=True,exist_ok=True)
        filename.write_bytes(gzip.compress(f.tobytes(order='C'),mtime=0,compresslevel=7))
        encoded[key] = f'data/{key}.bin'
        if key=='wind_squared_anomaly_prior5yr_z':bins[key]=[-2,-1,-.5,0,.5,1,2,4]
        elif key=='wind_squared_anomaly_prior5yr_difference_kn2':bins[key]=[-2000,-800,-300,-50,0,100,500,2000]
        else:
            pos=f[np.isfinite(f)&(f>0)]
            thresholds=np.quantile(pos,[.20,.35,.50,.65,.80,.95]).tolist()
            bins[key]=[float(round(t,7)) for t in thresholds]
        summaries[key]={'nonmissing':int(np.isfinite(f).sum()),'zero':int(np.count_nonzero(f==0)), 'missing':int(np.count_nonzero(~np.isfinite(f))),'maximum':float(np.nanmax(f))}
    status=np.where(df['wind_coverage_status'].eq('COMPLETE'),0,1).astype('uint8')
    assert np.count_nonzero(status==1)==33823
    sp=out.parent/'data'/'status.bin'
    sp.write_bytes(gzip.compress(status.tobytes(),mtime=0,compresslevel=7))
    encoded['status']='data/status.bin'
    s=jsset_once(s,r'const BINS=\{.*?\};', 'const BINS='+json.dumps(bins,separators=(',',':'))+';')
    s=jsset_once(s,r'const ENCODED=\{.*?\};', 'const ENCODED='+json.dumps(encoded,separators=(',',':'))+';')
    s=jsset_once(s,r'const MLIST=\[.*?\];', 'const MLIST='+json.dumps(list(METRICS),separators=(',',':'))+';')
    s=jsset_once(s,r'function asBytes\(str\)\{.*?\}\s*async function decoded\(str,type\)\{.*?\}',
    """async function decoded(path,type){
const r=await fetch(path+'?v=20261110');if(!r.ok)throw Error('Missing map data: '+path);
let buf=await r.arrayBuffer();const u=new Uint8Array(buf);
if(u.length>2&&u[0]===31&&u[1]===139){const stream=new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));buf=await new Response(stream).arrayBuffer()}
return type==='flags'?new Uint8Array(buf):new Float32Array(buf)}
async function loadMetric(k){if(data[k])return data[k];const a=await decoded(ENCODED[k],'f32');if(a.length!==S*N)throw Error('Metric size mismatch for '+k);data[k]=a;return a}""")
    s=jsset_once(s, r'for\(let i=0;i<MLIST.length;i\+\+\)\{.*?data.status=await decoded\(ENCODED.status,\'flags\'\);if\(data.status.length!==S\*N\)throw Error\(\'Status array mismatch\'\);',
    """$('loading-text').textContent='Loading corrected storm wind exposure…';
await loadMetric(metric);
data.status=await decoded(ENCODED.status,'flags');if(data.status.length!==S*N)throw Error('Source history flag mismatch');""")
    s=s.replace("$('metric').addEventListener('change',e=>{metric=e.target.value;render()});","$('metric').addEventListener('change',async e=>{metric=e.target.value;$('loader').style.display='flex';$('loading-text').textContent='Loading '+METRICLABEL[metric]+'…';try{await loadMetric(metric);render()}catch(err){console.error(err);$('loading-text').textContent=err.message;return}finally{if(data[metric])$('loader').style.display='none'}});")
    s=jsset_once(s,r'const METRICLABEL=\{.*?\};', 'const METRICLABEL='+json.dumps({k:v[1] for k,v in METRICS.items()},ensure_ascii=False,separators=(',',':'))+';\nconst DIVERGING='+json.dumps(DIVERGING)+';')
    options=''.join(f'<option value="{k}">{v[0]}</option>' for k,v in METRICS.items())
    s=jsset_once(s,r'<label class="field">Exposure measure<select id="metric">.*?</select></label>',
                 '<label class="field">Exposure measure<select id="metric">'+options+'</select></label>')
    s=s.replace('>Partial model</span>','>History flagged</span>')
    s=s.replace('>Missing</span>','>Missing measure</span>')
    s=s.replace('Color breaks are fixed across storms for comparison; zero and missing are shown separately.',
                'Fixed breaks permit comparisons between storms within each measure. Zero and missing values are distinct; orange dashed boundaries flag incomplete storm histories.')
    s=jsset_once(s,r'<div class="footer">.*?</div>',
                 '<div class="footer"><b>Model update: 10 November 2026.</b> Corrected empirical-decay reconstruction, JMA/IBTrACS tracks and WorldPop population weights. All 529 storms and 1,627 geographic units are retained. Values are modeled, <b>not validated anemometer observations</b>; the empirical outer tail may overstate remote winds. <a href="methodology.html" target="_blank" rel="noopener">Data, methods & limitations</a>.</div>')
    s=s.replace('<strong id="map-title">Select a storm</strong>', '<strong id="map-title">Select a storm</strong>')
    s=s.replace('Population-weighted wind exposure by municipality</small>', 'Corrected provisional wind exposure · November 2026</small>')
    s=s.replace('.muni.chosen{', '.muni.flagged{stroke:#b45309;stroke-width:.72;stroke-dasharray:2 1.5}.muni.chosen{')
    s=s.replace("if(metric==='wind_sq_anomaly_prior5yr_z')", "if(DIVERGING.includes(metric))")
    s=s.replace('if(st===2)partial++;','if(st===1)partial++;group[i].classList.toggle(\'flagged\',st===1);')
    s=jsset_once(s,r"function updateDetail\(k\)\{.*?\}\nfunction render\(\)",
        '''function updateDetail(k){const g=GEO[k],v=valueAt(k),st=statusAt(k),note=st===1?'Incomplete track history; reported wind may be a lower bound':'Track history marked complete';
$('detail').innerHTML=`<b>${g.n}</b>, ${g.p}<br><b>${METRICLABEL[metric]}:</b> ${fmt(v)}<br><span style="color:${st===1?'#a64b08':'#50677d'}">${note}</span>`}
function render()''')
    s=s.replace("(${METRICLABEL[metric]})</span>`;", "(${METRICLABEL[metric]})</span>${statusAt(k)===1?'<br>⚠ Incomplete track history':''}`;")
    s=s.replace('zero and missing are shown separately.', 'zero and missing are shown separately.')
    # Anomalies and bins use the same missing-value pattern; add additional legend for flagged histories.
    s=s.replace("o+='<div class=\"legend-row\"><span class=\"swatch\" style=\"background:repeating-linear-gradient(135deg,#c0c7cf 0px,#c0c7cf 4px,#788898 4px,#788898 5px)\"></span>Missing / unavailable baseline</div>';",
                "o+='<div class=\"legend-row\"><span class=\"swatch\" style=\"background:repeating-linear-gradient(135deg,#c0c7cf 0px,#c0c7cf 4px,#788898 4px,#788898 5px)\"></span>Missing value / unavailable baseline</div>';o+='<div class=\"legend-row\"><span class=\"swatch\" style=\"border:2px dashed #b45309;background:#fff\"></span>Incomplete source history</div>';" )
    # Make the caveat explicit at map load before values are shown.
    s=s.replace('<div class="side-head"><div class="eyebrow">Philippines · 1998–2019</div>', '<div class="side-head"><div class="eyebrow">Philippines · 1998–2019 · Corrected provisional release</div>')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(s,encoding='utf-8')
    summary={'datafile':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'rows':len(df),'storms':len(ids),'geographies':len(keys),'columns_in_master':32,'flagged_source_histories':int((status==1).sum()),'complete_source_histories':int((status==0).sum()),'metrics':summaries,'rendered_html_bytes':out.stat().st_size,'metric_asset_total_bytes':sum(f.stat().st_size for f in (out.parent/'data').glob('*.bin'))}
    qa=out.parent/'map_data_audit.json';qa.write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
