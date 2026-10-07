import {Slot} from '@radix-ui/react-slot'
import {cva, type VariantProps} from 'class-variance-authority'
import {twMerge} from 'tailwind-merge'
import type {ButtonHTMLAttributes} from 'react'
const styles = cva('inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 cursor-pointer',{variants:{variant:{default:'bg-blue-600 text-white hover:bg-blue-700',outline:'border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800',ghost:'hover:bg-slate-100 dark:hover:bg-slate-800'},size:{default:'h-10 px-4',sm:'h-8 px-3',lg:'h-12 px-6'}},defaultVariants:{variant:'default',size:'default'}})
export function Button({asChild=false,variant,size,className,...props}:ButtonHTMLAttributes<HTMLButtonElement>&VariantProps<typeof styles>&{asChild?:boolean}) { const Comp = asChild ? Slot : 'button'; return <Comp className={twMerge(styles({variant,size,className}))} {...props}/> }
