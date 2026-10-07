'use client'
import {useEffect,useState} from 'react'
import Link from 'next/link'
import {Shell} from '@/components/shell'
import {Button} from '@/components/ui/button'
import {Criteria,request} from '@/lib/api'
type Search={id:string;name:string;criteria:Criteria;created_at:string}
function summary(c:Criteria){return [c.countries?.length&&'Countries: '+c.countries.join(', '),c.country_code&&'Country: '+c.country_code,c.industries?.length&&'Industries: '+c.industries.join(', '),c.industry&&'Industry: '+c.industry,c.company_types?.length&&'Types: '+c.company_types.join(', '),c.employees_min!=null&&'Employees from '+c.employees_min,c.funding_min!=null&&'Funding from $'+c.funding_min,c.score_min!=null&&'Score '+c.score_min+'+',c.query&&'Name: '+c.query].filter(Boolean).join(' · ')||'All companies'}
export default function SearchesPage(){const [items,setItems]=useState<Search[]>([]),[error,setError]=useState('')
 async function load(){try{setItems(await request<Search[]>('/api/searches'))}catch(e){setError((e as Error).message)}}
 useEffect(()=>{load()},[])
 async function rename(id:string,current:string){const name=window.prompt('Rename search',current)?.trim();if(!name)return;try{await request('/api/searches/'+id,{method:'PATCH',body:JSON.stringify({name})});load()}catch(e){setError((e as Error).message)}}
 async function remove(id:string){try{await request('/api/searches/'+id,{method:'DELETE'});load()}catch(e){setError((e as Error).message)}}
 return <Shell><p className="text-sm font-semibold uppercase tracking-widest text-blue-600">Repeatable research</p><h1 className="mt-2 text-3xl font-bold">Saved searches</h1><p className="mt-2 text-slate-500">Rerun your saved Discover filters against current company data.</p><Button asChild className="mt-6"><Link href="/discover">Create a search in Discover</Link></Button>{error&&<p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}<div className="mt-6 space-y-3">{items.map(item=><div key={item.id} className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-[#121b30]"><div><h2 className="font-semibold">{item.name}</h2><p className="mt-1 text-xs text-slate-500">{summary(item.criteria)} · {item.created_at.slice(0,10)}</p></div><div className="flex gap-2"><Button asChild variant="outline" size="sm"><Link href={'/discover?search='+encodeURIComponent(item.id)}>Run</Link></Button><Button variant="ghost" size="sm" onClick={()=>rename(item.id,item.name)}>Rename</Button><Button variant="ghost" size="sm" onClick={()=>remove(item.id)}>Delete</Button></div></div>)}{!items.length&&<p className="text-sm text-slate-500">No searches saved yet.</p>}</div></Shell>
}
