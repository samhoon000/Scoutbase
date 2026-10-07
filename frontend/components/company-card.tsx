'use client'
import Link from 'next/link'
import {Bookmark,MapPin,ArrowUpRight} from 'lucide-react'
import {useState} from 'react'
import {Company,money,request} from '@/lib/api'
import {Button} from './ui/button'

export function CompanyCard({company,selected,onSelect,showReasons=false,matchReasons}:{company:Company;selected?:boolean;onSelect?:(id:string)=>void;showReasons?:boolean;matchReasons?:string[]}) {
  const [saved,setSaved]=useState(false)
  const [error,setError]=useState('')
  async function save(){try{await request('/api/saved-companies',{method:'POST',body:JSON.stringify({company_id:company.id})});setSaved(true)}catch(e){setError((e as Error).message)}}
  const location=[company.location?.city,company.location?.country||company.location?.country_code].filter(Boolean).join(', ')
  const employeeText=company.employees?.exact!=null?String(company.employees.exact):company.employees?.min!=null?company.employees.min+'–'+(company.employees.max??'?'):null
  const confidence=company.data_confidence!=null?(company.data_confidence>=75?'High':company.data_confidence>=45?'Medium':'Limited'):null
  const reasons=(matchReasons?.length?matchReasons:company.prospect_reason||[]).slice(0,4)
  return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md dark:border-slate-800 dark:bg-[#121b30]">
    <div className="flex items-start gap-4">{onSelect&&<input aria-label={'Select '+company.name} type="checkbox" checked={!!selected} onChange={()=>onSelect(company.id)} className="mt-2"/>}
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-lg font-bold text-blue-700 dark:bg-blue-950">{company.name.slice(0,2).toUpperCase()}</div>
      <div className="min-w-0 flex-1"><div className="flex flex-wrap items-start justify-between gap-2"><div><Link href={'/companies/'+company.id} className="text-lg font-semibold hover:text-blue-600">{company.name}</Link>{location&&<p className="mt-1 flex items-center gap-1 text-sm text-slate-500"><MapPin size={14}/>{location}</p>}</div>{company.prospect_score!=null&&<div className="rounded-xl bg-blue-50 px-3 py-2 text-center dark:bg-blue-950"><div className="text-xl font-bold text-blue-700 dark:text-blue-300">{company.prospect_score}<span className="text-xs font-normal">/100</span></div><div className="text-[10px] font-semibold uppercase tracking-wider text-blue-600">Prospect score</div></div>}</div>
        {company.description&&<p className="mt-3 line-clamp-2 text-sm text-slate-600 dark:text-slate-300">{company.description}</p>}
        <div className="mt-4 flex flex-wrap gap-2">{(company.industry||[]).map(x=><span key={x} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs dark:bg-slate-800">{x}</span>)}{employeeText&&<span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs dark:bg-slate-800">{employeeText} employees</span>}</div>
        {showReasons&&<div className="mt-4 rounded-xl bg-slate-50 p-3 text-xs dark:bg-slate-900"><p className="font-semibold">Evidence and match reasons</p>{reasons.length>0&&<ul className="mt-1 list-inside list-disc space-y-1 text-slate-600 dark:text-slate-300">{reasons.map((reason,i)=><li key={i}>{reason}</li>)}</ul>}<p className="mt-2 text-slate-500">{confidence&&'Data confidence: '+confidence+' · '}{company.sources?.length||0} sourced record{company.sources?.length===1?'':'s'}</p></div>}
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4 text-sm dark:border-slate-800"><div>{company.funding?.total_amount_usd!=null&&<><span className="text-slate-500">Funding </span><strong>{money(company.funding.total_amount_usd)}</strong></>}</div><div className="flex gap-2"><Button size="sm" variant="outline" onClick={save}><Bookmark size={15}/>{saved?'Saved':'Save'}</Button><Button size="sm" asChild><Link href={'/companies/'+company.id}>View company <ArrowUpRight size={15}/></Link></Button></div></div>{error&&<p className="mt-2 text-xs text-red-600">{error}</p>}
      </div>
    </div>
  </article>
}
