"use client";
import Link from "next/link";
import { Clapperboard, LayoutDashboard, Radio } from "lucide-react";

export function Shell({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-ink text-zinc-100"><aside className="fixed inset-y-0 flex w-64 flex-col border-r border-white/10 bg-panel p-5"><Link href="/dashboard" className="mb-12 flex items-center gap-3 text-xl font-black tracking-tight"><span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-emerald-300 to-violet-500 text-black shadow-lg shadow-violet-500/20"><Clapperboard size={21}/></span><span>Klipr<span className="text-emerald-300">.</span></span></Link><nav className="space-y-2 text-sm font-semibold text-zinc-400"><Link className="flex items-center gap-3 rounded-xl px-3 py-3 transition hover:bg-violet-400/10 hover:text-white" href="/dashboard"><LayoutDashboard size={18}/>Dashboard</Link><Link className="flex items-center gap-3 rounded-xl px-3 py-3 transition hover:bg-emerald-400/10 hover:text-white" href="/dashboard"><Radio size={18}/>Recording library</Link></nav><footer className="mt-auto border-t border-white/10 pt-5 text-xs text-zinc-500"><p className="font-bold text-zinc-300">Klipr.cloud</p><p className="mt-1">Live moments, clipped.</p></footer></aside><main className="ml-64 min-h-screen p-8">{children}</main></div>;
}
