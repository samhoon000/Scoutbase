'use client'
import Link from 'next/link'
import {usePathname} from 'next/navigation'
import {LayoutDashboard,Compass,Building2,Bookmark,Send,History,ChartNoAxesCombined,Sun,Moon} from 'lucide-react'
import {useEffect,useState} from 'react'
const items = [{href:'/discover',label:'Discover',Icon:Compass},{href:'/dashboard',label:'Dashboard',Icon:LayoutDashboard},{href:'/companies',label:'Companies',Icon:Building2},{href:'/saved',label:'Saved',Icon:Bookmark},{href:'/outreach',label:'Outreach',Icon:Send},{href:'/searches',label:'Searches',Icon:History}]
export function Shell({children}:{children:React.ReactNode}) {
  const path=usePathname(); const [dark,setDark]=useState(false)
  useEffect(()=>{const value=localStorage.getItem('theme')==='dark';setDark(value);document.documentElement.classList.toggle('dark',value)},[])
  return <div className="min-h-screen bg-[#f7f9fc] text-slate-900 dark:bg-[#0b1020] dark:text-slate-100 lg:flex">
    <aside className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-[#10182b] lg:fixed lg:inset-y-0 lg:w-64 lg:border-b-0 lg:border-r">
      <div className="flex h-18 items-center justify-between px-6"><Link href="/" className="flex items-center gap-2 text-xl font-bold tracking-tight"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white"><ChartNoAxesCombined size={20}/></span>Scout<span className="text-blue-600">Base</span></Link><button aria-label="Toggle theme" onClick={()=>{localStorage.setItem('theme',dark?'light':'dark');setDark(!dark);document.documentElement.classList.toggle('dark',!dark)}}>{dark?<Sun size={18}/>:<Moon size={18}/>}</button></div>
      <nav className="flex gap-1 overflow-x-auto p-3 lg:flex-col lg:px-3">{items.map(({href,label,Icon})=><Link key={href} href={href} className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium ${path===href||path.startsWith(href+'/')?'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300':'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'}`}><Icon size={18}/>{label}</Link>)}</nav>
      <div className="hidden px-6 pt-8 text-xs text-slate-400 lg:block">COMPANY INTELLIGENCE<br/>FOR THE CURIOUS PROSPECTOR</div>
    </aside><main className="min-w-0 flex-1 lg:ml-64"><div className="mx-auto max-w-7xl p-5 md:p-8 lg:p-10">{children}</div></main>
  </div>
}
