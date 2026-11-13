"use client";
import { useState } from "react";
import {
  Archive,
  Clapperboard,
  Image as ImageIcon,
  LogOut,
  Menu,
  Radio,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { KliprLogo } from "@/components/logo";
import { LanguageToggle, useLanguage } from "@/components/language";

export type DashboardSection =
  | "live"
  | "archive"
  | "shorts"
  | "thumbnail"
  | "branding";

export function Shell({
  children,
  activeCount = 0,
  activeSection = "live",
  onSectionChange,
}: {
  children: React.ReactNode;
  activeCount?: number;
  activeSection?: DashboardSection;
  onSectionChange?: (section: DashboardSection) => void;
}) {
  const [open, setOpen] = useState(false);
  const { language, t } = useLanguage();
  const ar = language === "ar";
  const items: {
    id: DashboardSection;
    icon: typeof Radio;
    ar: string;
    en: string;
    hintAr: string;
    hintEn: string;
  }[] = [
    {
      id: "live",
      icon: Radio,
      ar: "البثوث النشطة",
      en: "Live Capture",
      hintAr: "التسجيل المباشر",
      hintEn: "Record live",
    },
    {
      id: "archive",
      icon: Archive,
      ar: "مكتبة الأرشيف",
      en: "VOD Archive",
      hintAr: "التسجيلات المكتملة",
      hintEn: "Completed VODs",
    },
    {
      id: "shorts",
      icon: Clapperboard,
      ar: "صانع الشورتات",
      en: "Shorts & Clipper",
      hintAr: "قصاص المقاطع الذكي",
      hintEn: "AI clip studio",
    },
    {
      id: "thumbnail",
      icon: ImageIcon,
      ar: "صانع الثامبنايل",
      en: "Thumbnail Studio",
      hintAr: "أغلفة احترافية",
      hintEn: "Cover creator",
    },
    {
      id: "branding",
      icon: Sparkles,
      ar: "الهوية وشاشة النهاية",
      en: "Branding & Outro",
      hintAr: "هوية قناة الأرشيف",
      hintEn: "Archive identity",
    },
  ];
  const choose = (id: DashboardSection) => {
    setOpen(false);
    if (onSectionChange) onSectionChange(id);
    else window.location.assign(`/dashboard?section=${id}`);
  };
  const logout = async () => {
    await api.logout();
    window.location.assign("/");
  };
  const nav = (
    <nav className="space-y-2 p-3">
      {items.map(({ id, icon: Icon, ar: arLabel, en, hintAr, hintEn }) => (
        <button
          key={id}
          onClick={() => choose(id)}
          className={`flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-start transition ${activeSection === id ? "border-emerald-200 bg-emerald-50 text-emerald-700 shadow-sm" : "border-transparent text-slate-600 hover:border-slate-200 hover:bg-slate-50"}`}
        >
          <span
            className={`grid size-10 shrink-0 place-items-center rounded-lg ${activeSection === id ? "bg-emerald-500 text-white" : "bg-slate-100 text-slate-500"}`}
          >
            <Icon size={19} />
          </span>
          <span className="min-w-0">
            <b className="block truncate text-sm">{ar ? arLabel : en}</b>
            <small className="block truncate text-[11px] text-slate-400">
              {ar ? hintAr : hintEn}
            </small>
          </span>
          {id === "live" && activeCount > 0 && (
            <span className="ms-auto rounded-full bg-emerald-500 px-2 py-0.5 text-[10px] font-black text-white">
              {activeCount}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="fixed inset-x-0 top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur lg:start-72">
        <div className="flex h-16 items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3 lg:hidden">
            <button
              onClick={() => setOpen(true)}
              className="rounded-lg border border-slate-200 p-2 text-slate-600"
              aria-label={ar ? "فتح القائمة" : "Open menu"}
            >
              <Menu size={20} />
            </button>
            <KliprLogo href="/dashboard" compact className="[&_svg]:size-9" />
          </div>
          <div className="hidden lg:block">
            <p className="text-xs font-black uppercase tracking-[.18em] text-emerald-600">
              {ar ? "مساحة عمل المبدع" : "Creator workspace"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700 sm:inline">
              {activeCount} {t.active}
            </span>
            <LanguageToggle />
            <button
              onClick={logout}
              aria-label={t.logout}
              title={t.logout}
              className="rounded-lg p-2.5 text-slate-500 hover:bg-slate-100"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </header>
      <aside className="fixed inset-y-0 start-0 z-40 hidden w-72 border-e border-slate-200 bg-white lg:flex lg:flex-col">
        <div className="flex h-20 items-center border-b border-slate-100 px-6">
          <KliprLogo href="/dashboard" className="[&_svg]:size-11" />
        </div>
        <div className="flex-1 overflow-y-auto py-3">{nav}</div>
        <div className="border-t border-slate-100 p-4">
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-xs font-black text-slate-700">Klipr.cloud</p>
            <p className="mt-1 text-[11px] leading-5 text-slate-400">
              {ar
                ? "من البث المباشر إلى محتوى جاهز للنشر."
                : "From live stream to publish-ready content."}
            </p>
          </div>
        </div>
      </aside>
      {open && (
        <div
          className="fixed inset-0 z-50 bg-slate-950/35 lg:hidden"
          onClick={() => setOpen(false)}
        >
          <aside
            className="h-full w-[86%] max-w-80 bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex h-20 items-center justify-between border-b border-slate-100 px-5">
              <KliprLogo href="/dashboard" className="[&_svg]:size-10" />
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg p-2 hover:bg-slate-100"
              >
                <X />
              </button>
            </div>
            {nav}
          </aside>
        </div>
      )}
      <main className="px-4 pb-10 pt-24 sm:px-6 lg:ms-72 lg:px-8">
        {children}
      </main>
    </div>
  );
}
