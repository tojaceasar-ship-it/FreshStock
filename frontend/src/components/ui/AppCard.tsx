import { ElementType, HTMLAttributes, ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

export type AppCardVariant = 'default' | 'kpi' | 'hero' | 'financial' | 'ai' | 'list'

const variants: Record<AppCardVariant, string> = {
  default: 'bg-white',
  kpi: 'bg-white',
  hero: 'overflow-hidden bg-white before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-gradient-to-r before:from-green-500 before:via-emerald-500 before:to-sky-400',
  financial: 'bg-gradient-to-br from-white to-emerald-50/50',
  ai: 'bg-gradient-to-br from-white via-white to-violet-50/70',
  list: 'overflow-hidden bg-white',
}

export const appCardClass = 'relative rounded-[20px] border border-slate-950/[0.05] shadow-[0_4px_18px_rgba(15,23,42,0.05)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-[0_10px_30px_rgba(15,23,42,0.065)]'

type Props = HTMLAttributes<HTMLElement> & {
  as?: ElementType
  variant?: AppCardVariant
  padding?: 'none' | 'compact' | 'default' | 'roomy'
  children: ReactNode
}

export function AppCard({ as: Component='section', variant='default', padding='default', className='', children, ...props }: Props) {
  const spacing = { none:'', compact:'p-5', default:'p-6', roomy:'p-7' }[padding]
  return <Component className={`${appCardClass} ${variants[variant]} ${spacing} ${className}`} {...props}>{children}</Component>
}

export function AppCardHeader({ icon:Icon, title, description, action, to }: { icon?:ElementType; title:string; description?:string; action?:string; to?:string }) {
  return <header className="flex items-start justify-between gap-4"><div className="flex min-w-0 items-start gap-3">{Icon&&<span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-emerald-50 text-emerald-700"><Icon className="h-5 w-5"/></span>}<div><h3 className="text-base font-bold text-slate-800">{title}</h3>{description&&<p className="mt-1 text-sm font-normal text-slate-500">{description}</p>}</div></div>{to&&action&&<Link to={to} className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-slate-500 transition hover:text-green-700">{action}<ArrowRight className="h-4 w-4"/></Link>}</header>
}

export function MiniCard({ icon:Icon, value, title, description, tone='green', to }: { icon:ElementType; value:string|number; title:string; description?:string; tone?:'green'|'red'|'amber'|'blue'|'violet'; to:string }) {
  const tones={green:'bg-emerald-50 text-emerald-700',red:'bg-rose-50 text-rose-700',amber:'bg-amber-50 text-amber-700',blue:'bg-sky-50 text-sky-700',violet:'bg-violet-50 text-violet-700'}
  return <Link to={to} className={`group rounded-2xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${tones[tone]}`}><div className="flex items-center gap-3"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-white/90 shadow-sm"><Icon className="h-5 w-5"/></span><div className="min-w-0 flex-1"><div className="flex items-center justify-between"><strong className="text-2xl font-extrabold">{value}</strong><ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1"/></div><p className="text-sm font-semibold">{title}</p>{description&&<p className="mt-0.5 truncate text-xs opacity-70">{description}</p>}</div></div></Link>
}
