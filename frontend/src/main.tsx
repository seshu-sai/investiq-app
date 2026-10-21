import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Activity, ArrowUpRight, Bell, BrainCircuit, ChartNoAxesCombined, CircleAlert, Globe2, Plus, Search, ShieldCheck, Trash2} from 'lucide-react';
import LiveResearch from './LiveResearch';
import Trajectory from './Trajectory';
import Valuation from './Valuation';
import AIInsights from './AIInsights';
import StockSearch from './StockSearch';
import './style.css';
type Settings = {amount:number;currency:string;markets:string[];assets:string[];risk:string;horizon:string;frequency:string};
type Watch = {id:number;symbol:string;market:string};
const defaults:Settings={amount:5000,currency:'CAD',markets:['IN','CA','US'],assets:['stocks','funds','etfs'],risk:'high',horizon:'3-5',frequency:'daily'};
async function api<T>(path:string,options?:RequestInit):Promise<T>{const res=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...options?.headers}});if(!res.ok)throw new Error(`Request failed (${res.status})`);return res.status===204?undefined as T:res.json()}
function App(){const [settings,setSettings]=useState<Settings>(defaults);const [watch,setWatch]=useState<Watch[]>([]);const [symbol,setSymbol]=useState('');const [market, setMarket] = useState<'US' | 'CA' | 'IN'>('US');const [notice,setNotice]=useState('');const [selected,setSelected]=useState<Watch|null>(null);const [loading,setLoading]=useState(false);const [activeTab,setActiveTab]=useState<'overview'|'forecasts'|'valuation'>('overview');
const refresh=()=>api<Watch[]>('/watchlist').then(setWatch).catch(()=>setNotice('Cannot connect to backend. Start the API server.'));
useEffect(()=>{api<Settings>('/settings').then(s=>setSettings({...s,amount:Number(s.amount)})).catch(()=>setNotice('Backend unavailable. Showing local defaults.'));refresh()},[]);
const save=async()=>{setLoading(true);try{await api('/settings',{method:'POST',body:JSON.stringify(settings)});setNotice('Preferences saved. New analyses will use this risk tolerance and horizon.')}catch(e){setNotice(String(e))}finally{setLoading(false)}};
const add=async(e:React.FormEvent)=>{e.preventDefault();if(!symbol.trim())return;try{await api('/watchlist',{method:'POST',body:JSON.stringify({symbol:symbol.trim().toUpperCase(),market})});setSymbol('');refresh();setNotice('Added to watchlist. Select View research to retrieve market data.')}catch(e){setNotice(String(e))}};
const remove=async(id:number)=>{try{await api(`/watchlist/${id}`,{method:'DELETE'});if(selected?.id===id)setSelected(null);refresh()}catch(e){setNotice(String(e))}};
return <div className="shell"><aside className="sidebar"><div className="brand"><div className="brandmark"><ChartNoAxesCombined size={23}/></div><span>Invest<span className="accent">IQ</span></span></div><div className="navlabel">WORKSPACE</div><button type="button" className={`nav ${activeTab==='overview' ? 'active' : ''}`} onClick={()=>setActiveTab('overview')}><Activity size={18}/> Overview</button><div className="nav"><Bell size={18}/> Alerts <span className="soon">Soon</span></div><button type="button" className={`nav ${activeTab==='forecasts' ? 'active' : ''}`} onClick={()=>setActiveTab('forecasts')}><BrainCircuit size={18}/> AI Research</button><button type="button" className={`nav ${activeTab==='valuation' ? 'active' : ''}`} onClick={()=>setActiveTab('valuation')}><ChartNoAxesCombined size={18}/> Valuation</button><div className="sidebarfoot"><ShieldCheck size={17}/> Evidence-first research<br/><small>Development preview · v0.1</small></div></aside><main><header><div className="eyebrow">INVESTMENT INTELLIGENCE PLATFORM</div><div className="headrow"><div><h1>Your investment command center</h1><p>Research smarter. Track opportunities across global markets.</p></div><span className="pill"><span className="dot"/> Development mode</span></div></header>
<nav className="mobile-tabs" aria-label="Research sections">
  <button type="button" aria-pressed={activeTab==='overview'} onClick={()=>setActiveTab('overview')}>Overview</button>
  <button type="button" aria-pressed={activeTab==='forecasts'} onClick={()=>setActiveTab('forecasts')}>AI Research</button>
  <button type="button" aria-pressed={activeTab==='valuation'} onClick={()=>setActiveTab('valuation')}>Valuation</button>
</nav>
<div className="notice"><CircleAlert size={19}/><span><b>Research with dated evidence.</b> US quotes use Finnhub; Canadian and Indian prices use daily Yahoo Finance bars. Review data freshness and risk before making a decision.</span></div>
{activeTab==='overview' ? <><section className="metrics"><div className="metric"><span>INVESTMENT BUDGET</span><strong>{new Intl.NumberFormat('en-CA',{style:'currency',currency:settings.currency}).format(settings.amount)}</strong><small>User-configurable allocation</small></div><div className="metric"><span>MARKETS SELECTED</span><strong>{settings.markets.length} <small>markets</small></strong><small>India · Canada · United States</small></div><div className="metric"><span>TRACKED ASSETS</span><strong>{watch.length} <small>symbols</small></strong><small>Personal research watchlist</small></div><div className="metric"><span>QUOTE REFRESH</span><strong className="muted">{selected ? '60 seconds' : 'Select a stock'}</strong><small>While research is open · no background alerts</small></div></section>
<div className="content"><div className="left"><section className="panel"><div className="panelhead"><div><h2><Globe2 size={19}/> Your watchlist</h2><p>Build a list of companies to research.</p></div></div><form className="addform" onSubmit={add}><StockSearch market={market} value={symbol} onChange={setSymbol}/><select aria-label="Market" value={market} onChange={e=>setMarket(e.target.value as typeof market)}><option value="US">USA</option><option value="CA">Canada</option><option value="IN">India</option></select><button type="submit"><Plus size={17}/> Add</button></form>{watch.filter(w=>w.market===market).length===0?<div className="empty"><Search size={30}/><b>No symbols tracked yet</b><p>Add your first ticker to begin building a research watchlist.</p></div>:<div className="watchlist">{watch.filter(w=>w.market===market).map(w=><div className="watchrow" key={w.id}><div className="ticker">{w.symbol.slice(0,2)}</div><div className="watchname"><b>{w.symbol}</b><small>{w.market==='IN'?'India':w.market==='CA'?'Canada':'United States'}</small></div><button className="outline" onClick={()=>setSelected(w)}>View research <ArrowUpRight size={15}/></button><button className="iconbtn" aria-label={`Remove ${w.symbol}`} onClick={()=>remove(w.id)}><Trash2 size={17}/></button></div>)}</div>}</section>
<section className="panel"><div className="panelhead"><div><h2><BrainCircuit size={19}/> Company research & scenarios</h2><p>Dated market data and hypothetical valuation scenarios.</p></div><span className="tag">Provider data · check timestamps</span></div><div className="research">
{selected
  ? <><LiveResearch
      key={`${selected.market}-${selected.symbol}`}
      market={selected.market}
      symbol={selected.symbol}
    />
    <Trajectory
      key={`trajectory-${selected.market}-${selected.symbol}`}
      market={selected.market}
      symbol={selected.symbol}
    />

</>
  : <>
      <div className="researchicon"><BrainCircuit size={28}/></div>
      <h3>Select a company to research</h3>
      <p>Choose a stock from your watchlist to view available prices, company data and research.</p>
    </>
}
</div></section></div>
<div className="right"><section className="panel"><div className="panelhead"><div><h2>Investor profile</h2><p>Personalize your research preferences.</p></div></div><div className="fields"><label>Investment amount<input type="number" min="1" step="0.01" value={settings.amount} onChange={e=>setSettings({...settings,amount:Number(e.target.value)})}/></label><label>Base currency<select value={settings.currency} onChange={e=>setSettings({...settings,currency:e.target.value})}><option>CAD</option><option>USD</option><option>INR</option></select></label><label>Risk tolerance<select value={settings.risk} onChange={e=>setSettings({...settings,risk:e.target.value})}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label><label>Investment horizon<select value={settings.horizon} onChange={e=>setSettings({...settings,horizon:e.target.value})}><option value="0-1">Under 1 year</option><option value="1-3">1–3 years</option><option value="3-5">3–5 years</option><option value="5+">5+ years</option></select></label><label>Research cadence<select value={settings.frequency} onChange={e=>setSettings({...settings,frequency:e.target.value})}><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label><div className="fieldlabel">Markets</div><div className="checks">{[['IN','India'],['CA','Canada'],['US','USA']].map(([code,name])=><label key={code}><input type="checkbox" checked={settings.markets.includes(code)} onChange={e=>setSettings({...settings,markets:e.target.checked?[...settings.markets,code]:settings.markets.filter(x=>x!==code)})}/>{name}</label>)}</div><div className="fieldlabel">Asset classes</div><div className="checks">{[['stocks','Stocks'],['funds','Mutual funds'],['etfs','ETFs']].map(([code,name])=><label key={code}><input type="checkbox" checked={settings.assets.includes(code)} onChange={e=>setSettings({...settings,assets:e.target.checked?[...settings.assets,code]:settings.assets.filter(x=>x!==code)})}/>{name}</label>)}</div><button className="save" disabled={loading||settings.amount<=0||!settings.markets.length||!settings.assets.length} onClick={save}>{loading?'Saving…':'Save preferences'}</button></div></section><div className="disclaimer">InvestIQ is a research prototype, not a registered investment adviser. Research assessments can be incomplete. Investment losses are possible.</div></div></div></> : activeTab === "forecasts" ? <section className="panel">
      <div className="panelhead">
        <div>
          <h2><BrainCircuit size={19}/> Investment Research</h2>
          <p>Focused investment research and risk assessment.</p>
        </div>
      </div>
      {selected ? (
        <AIInsights
          key={`ai-${selected.market}-${selected.symbol}`}
          market={selected.market}
          symbol={selected.symbol}
        />
      ) : (
        <div className="empty">
          <BrainCircuit size={30}/>
          <h3>Select a stock first</h3>
          <p>Go to Overview, choose a stock from your watchlist, then return here.</p>
        </div>
      )}
    </section> : <section className="panel">
      <div className="panelhead">
        <div>
          <h2><ChartNoAxesCombined size={19}/> Valuation & Potential Gains</h2>
          <p>Your preferences, historical returns, earnings sensitivities and current company news.</p>
        </div>
      </div>
      {selected ? (
        <Valuation
          key={`valuation-${selected.market}-${selected.symbol}`}
          market={selected.market}
          symbol={selected.symbol}
        />
      ) : (
        <div className="empty">
          <ChartNoAxesCombined size={30}/>
          <h3>Select a stock first</h3>
          <p>Go to Overview, choose a stock, then return to Valuation.</p>
        </div>
      )}
    </section>}{notice&&<div className="toast" role="status" onClick={()=>setNotice('')}>{notice} ×</div>}</main></div>}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
