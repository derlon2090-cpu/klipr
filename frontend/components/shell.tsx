"use client";
import { useEffect, useState } from "react";
import {
  Archive,
  Bell,
  CheckCheck,
  Clapperboard,
  Clock3,
  LogOut,
  Menu,
  MessageSquareText,
  KeyRound,
  Plus,
  Radio,
  FolderDown,
  BadgeCheck,
  Image as ImageIcon,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { api, NotificationItem, SessionStatus, WatchlistSubscription } from "@/lib/api";
import { KliprLogo } from "@/components/logo";
import { LanguageToggle, useLanguage } from "@/components/language";

export type DashboardSection =
  | "live"
  | "vods"
  | "clips"
  | "thumbnails"
  | "intro-outro"
  | "studio"
  | "live"
  | "shorts"
  | "ai-metadata"
  | "channels"
  | "settings"
  | "suggestions"
  | "presets"
  | "sessions";

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
  const [bellOpen, setBellOpen] = useState(false);
  const [bellTab, setBellTab] = useState<"alerts" | "creators">("alerts");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [subscriptions, setSubscriptions] = useState<WatchlistSubscription[]>(
    [],
  );
  const [creatorUrl, setCreatorUrl] = useState("");
  const [bellError, setBellError] = useState("");
  const [bellBusy, setBellBusy] = useState(false);
  const [bellNow, setBellNow] = useState(Date.now());
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("unset");
  const { language, t } = useLanguage();
  const ar = language === "ar";
  const refreshBell = async () => {
    try {
      const [alerts, creators, credentials] = await Promise.all([
        api.notifications(),
        api.watchlist(),
        api.credentials(),
      ]);
      setNotifications(alerts.items);
      setUnreadCount(alerts.unread_count);
      setSubscriptions(creators);
      setSessionStatus(
        Object.values(credentials).some((item) => item.status === "expired")
          ? "expired"
          : Object.values(credentials).some((item) => item.status === "active")
            ? "active"
            : "unset",
      );
    } catch {
      /* Session and API errors remain non-blocking for the dashboard. */
    }
  };
  useEffect(() => {
    refreshBell();
    const refreshTimer = setInterval(refreshBell, 15000);
    const clockTimer = setInterval(() => setBellNow(Date.now()), 1000);
    return () => {
      clearInterval(refreshTimer);
      clearInterval(clockTimer);
    };
  }, []);
  const subscribe = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!creatorUrl.trim()) return;
    setBellBusy(true);
    setBellError("");
    try {
      await api.subscribeCreator(creatorUrl.trim());
      setCreatorUrl("");
      await refreshBell();
    } catch (error) {
      setBellError(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBellBusy(false);
    }
  };
  const toggleSubscription = async (item: WatchlistSubscription) => {
    try {
      const next = await api.updateSubscription(item.id, {
        auto_record: !item.auto_record,
      });
      setSubscriptions((current) =>
        current.map((value) => (value.id === item.id ? next : value)),
      );
    } catch (error) {
      setBellError(error instanceof Error ? error.message : "Request failed");
    }
  };
  const removeSubscription = async (id: string) => {
    try {
      await api.unsubscribeCreator(id);
      setSubscriptions((current) => current.filter((item) => item.id !== id));
    } catch (error) {
      setBellError(error instanceof Error ? error.message : "Request failed");
    }
  };
  const cancelAlert = async (id: string) => {
    try {
      const next = await api.cancelAutoRecord(id);
      setNotifications((current) =>
        current.map((item) => (item.id === id ? next : item)),
      );
    } catch (error) {
      setBellError(error instanceof Error ? error.message : "Request failed");
    }
  };
  const readAll = async () => {
    await api.readAllNotifications();
    setUnreadCount(0);
    setNotifications((current) =>
      current.map((item) => ({ ...item, is_read: true })),
    );
  };
  const items: {
    id: DashboardSection;
    icon: typeof Radio;
    ar: string;
    en: string;
    group: "create" | "manage";
  }[] = [
    {
      id: "vods",
      icon: FolderDown,
      ar: "سحب ومكتبة البثوث",
      en: "Import & VOD Library",
      group: "create",
    },
    {
      id: "clips",
      icon: Clapperboard,
      ar: "استوديو القص والمونتاج",
      en: "Clip & Edit Studio",
      group: "create",
    },
    {
      id: "shorts",
      icon: Sparkles,
      ar: "صناعة الشورتات",
      en: "Shorts Studio",
      group: "create",
    },
    {
      id: "ai-metadata",
      icon: MessageSquareText,
      ar: "صناعة العنوان والوصف (AI)",
      en: "AI Titles & Metadata",
      group: "create",
    },
    {
      id: "channels",
      icon: Radio,
      ar: "إدارة القنوات",
      en: "Channel Management",
      group: "manage",
    },
    {
      id: "settings",
      icon: KeyRound,
      ar: "الإعدادات والهوية",
      en: "Settings & Branding",
      group: "manage",
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
  const groups = [
    { id: "create", ar: "الإنتاج والمحتوى", en: "CREATE & PUBLISH" },
    { id: "manage", ar: "الإدارة والإعدادات", en: "MANAGE & SETTINGS" },
  ] as const;
  const nav = (
    <nav className="space-y-2 px-3 py-2">
      {groups.map((group) => (
        <section key={group.id} className="pt-1">
          <p className="px-3 pb-1 pt-2 text-[11px] font-semibold tracking-wider text-slate-500">
            {ar ? group.ar : group.en}
          </p>
          <div className="space-y-1">
            {items.filter((item) => item.group === group.id).map(({ id, icon: Icon, ar: arLabel, en }) => (
              <button key={id} onClick={() => choose(id)} className={`flex w-full items-center gap-2.5 rounded-xl border px-3 py-2.5 text-start text-sm font-medium transition ${activeSection === id ? "border-emerald-400/30 bg-emerald-500/15 text-emerald-300 shadow-sm" : "border-transparent text-slate-300 hover:border-slate-700 hover:bg-slate-800"}`}>
                <span className={`grid size-8 shrink-0 place-items-center rounded-lg ${activeSection === id ? "bg-emerald-500 text-slate-950" : "bg-slate-800 text-slate-400"}`}><Icon size={17} /></span>
                <span className="min-w-0 flex-1 truncate">{ar ? arLabel : en}</span>
                {id === "live" && activeCount > 0 && <span className="rounded-full bg-emerald-500 px-2 py-0.5 text-[10px] font-black text-white">{activeCount}</span>}
                {id === "settings" && <span className={`size-2.5 shrink-0 rounded-full ${sessionStatus === "active" ? "bg-emerald-500" : sessionStatus === "expired" ? "bg-amber-500" : "bg-slate-600"}`} aria-label={sessionStatus} />}
              </button>
            ))}
          </div>
        </section>
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
            <div className="relative">
              <button
                type="button"
                onClick={() => setBellOpen(!bellOpen)}
                aria-label={
                  ar
                    ? "الإشعارات وقائمة المشاهير"
                    : "Notifications and creator watchlist"
                }
                className={`relative rounded-lg p-2.5 ${bellOpen ? "bg-emerald-50 text-emerald-700" : "text-slate-500 hover:bg-slate-100"}`}
              >
                <Bell size={19} />
                {unreadCount > 0 && (
                  <span className="absolute -end-1 -top-1 grid min-w-5 place-items-center rounded-full bg-emerald-500 px-1 text-[10px] font-black leading-5 text-white">
                    {Math.min(unreadCount, 99)}
                  </span>
                )}
              </button>
              {bellOpen && (
                <div className="fixed inset-x-3 top-20 z-50 max-h-[78vh] overflow-hidden rounded-2xl border border-slate-200 bg-white text-start shadow-2xl sm:absolute sm:inset-x-auto sm:end-0 sm:top-12 sm:w-[420px]">
                  <div className="border-b border-slate-100 p-3">
                    <div className="grid grid-cols-2 rounded-xl bg-slate-100 p-1">
                      <button
                        type="button"
                        onClick={() => setBellTab("alerts")}
                        className={`rounded-lg px-3 py-2 text-xs font-black ${bellTab === "alerts" ? "bg-white text-emerald-700 shadow-sm" : "text-slate-500"}`}
                      >
                        {ar ? "التنبيهات الحية" : "Live alerts"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setBellTab("creators")}
                        className={`rounded-lg px-3 py-2 text-xs font-black ${bellTab === "creators" ? "bg-white text-emerald-700 shadow-sm" : "text-slate-500"}`}
                      >
                        {ar ? "قائمة المشاهير" : "Subscribed creators"}
                      </button>
                    </div>
                    {bellError && (
                      <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs font-bold text-rose-600">
                        {bellError}
                      </p>
                    )}
                  </div>
                  <div className="max-h-[62vh] overflow-y-auto p-3">
                    {bellTab === "alerts" ? (
                      <>
                        <div className="mb-3 flex items-center justify-between">
                          <b className="text-sm">
                            {ar ? "تنبيهات بدء البث" : "Stream start alerts"}
                          </b>
                          {notifications.length > 0 && (
                            <button
                              type="button"
                              onClick={readAll}
                              className="inline-flex items-center gap-1 text-[11px] font-black text-emerald-700"
                            >
                              <CheckCheck size={14} />
                              {ar ? "تحديد الكل كمقروء" : "Mark all read"}
                            </button>
                          )}
                        </div>
                        <div className="space-y-2">
                          {notifications.length ? (
                            notifications.map((item) => {
                              const remaining = item.scheduled_for
                                ? Math.max(
                                    0,
                                    Math.ceil(
                                      (Date.parse(item.scheduled_for) -
                                        bellNow) /
                                        1000,
                                    ),
                                  )
                                : 0;
                              return (
                                <article
                                  key={item.id}
                                  className={`rounded-xl border p-3 ${item.is_read ? "border-slate-200" : "border-emerald-200 bg-emerald-50/50"}`}
                                >
                                  <div className="flex items-start gap-3">
                                    <span
                                      className={`mt-1 size-2 shrink-0 rounded-full ${item.status === "pending_auto_record" ? "animate-pulse bg-red-500" : item.status === "auto_started" ? "bg-emerald-500" : "bg-slate-300"}`}
                                    />
                                    <div className="min-w-0 flex-1">
                                      <p className="text-sm font-black">
                                        {item.title}
                                      </p>
                                      <p className="mt-1 text-xs leading-5 text-slate-500">
                                        {item.message}
                                      </p>
                                      {item.status ===
                                        "pending_auto_record" && (
                                        <div className="mt-3 flex items-center justify-between gap-2">
                                          <span className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-1 text-xs font-black text-amber-700">
                                            <Clock3 size={13} />
                                            {remaining}s
                                          </span>
                                          <button
                                            type="button"
                                            onClick={() => cancelAlert(item.id)}
                                            className="rounded-lg bg-rose-600 px-3 py-2 text-[11px] font-black text-white"
                                          >
                                            {ar
                                              ? "إلغاء التسجيل التلقائي"
                                              : "Cancel auto-record"}
                                          </button>
                                        </div>
                                      )}
                                      {item.status !==
                                        "pending_auto_record" && (
                                        <span className="mt-2 inline-block rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-500">
                                          {item.status === "auto_started"
                                            ? ar
                                              ? "بدأ التسجيل تلقائياً"
                                              : "Auto-record started"
                                            : item.status ===
                                                "manual_taken_over"
                                              ? ar
                                                ? "تم التسجيل يدوياً"
                                                : "Manual recording took over"
                                              : ar
                                                ? "تم الإلغاء"
                                                : "Cancelled"}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </article>
                              );
                            })
                          ) : (
                            <p className="rounded-xl border border-dashed border-slate-200 p-7 text-center text-xs text-slate-400">
                              {ar ? "لا توجد تنبيهات بعد." : "No alerts yet."}
                            </p>
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        <form
                          onSubmit={subscribe}
                          className="rounded-xl border border-emerald-200 bg-emerald-50 p-3"
                        >
                          <label className="text-xs font-black text-emerald-800">
                            {ar
                              ? "إضافة قناة Twitch أو Kick"
                              : "Add a Twitch or Kick channel"}
                          </label>
                          <div className="mt-2 flex gap-2">
                            <input
                              value={creatorUrl}
                              onChange={(event) =>
                                setCreatorUrl(event.target.value)
                              }
                              placeholder="https://twitch.tv/creator"
                              className="min-w-0 flex-1 rounded-lg border border-emerald-200 bg-white px-3 py-2 text-xs outline-none focus:border-emerald-500"
                            />
                            <button
                              disabled={bellBusy}
                              className="grid size-9 shrink-0 place-items-center rounded-lg bg-emerald-500 text-white disabled:opacity-50"
                            >
                              <Plus size={17} />
                            </button>
                          </div>
                          <p className="mt-2 text-[10px] leading-4 text-emerald-700">
                            {ar
                              ? "عند بدء البث سيصلك تنبيه، ثم يبدأ التسجيل بعد 30 ثانية ما لم تُلغِه."
                              : "You will be alerted when they go live; recording starts after 30 seconds unless cancelled."}
                          </p>
                        </form>
                        <div className="mt-3 space-y-2">
                          {subscriptions.length ? (
                            subscriptions.map((item) => (
                              <article
                                key={item.id}
                                className="flex items-center gap-3 rounded-xl border border-slate-200 p-3"
                              >
                                {item.avatar_url ? (
                                  <img
                                    src={item.avatar_url}
                                    alt=""
                                    className="size-10 rounded-full object-cover"
                                  />
                                ) : (
                                  <span className="grid size-10 rounded-full bg-slate-100 place-items-center text-xs font-black">
                                    {item.display_name
                                      .slice(0, 2)
                                      .toUpperCase()}
                                  </span>
                                )}
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center gap-2">
                                    <b className="truncate text-sm">
                                      {item.display_name}
                                    </b>
                                    <span
                                      className={`size-2 rounded-full ${item.is_currently_live ? "animate-pulse bg-red-500" : "bg-slate-300"}`}
                                    />
                                  </div>
                                  <p className="text-[10px] text-slate-400">
                                    {item.platform.toUpperCase()} ·{" "}
                                    {item.delay_seconds}s
                                  </p>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => toggleSubscription(item)}
                                  className={`rounded-full px-2 py-1 text-[10px] font-black ${item.auto_record ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}
                                >
                                  {item.auto_record
                                    ? ar
                                      ? "تلقائي"
                                      : "Auto"
                                    : ar
                                      ? "متوقف"
                                      : "Off"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => removeSubscription(item.id)}
                                  className="rounded-lg p-2 text-rose-500 hover:bg-rose-50"
                                >
                                  <Trash2 size={15} />
                                </button>
                              </article>
                            ))
                          ) : (
                            <p className="rounded-xl border border-dashed border-slate-200 p-7 text-center text-xs text-slate-400">
                              {ar
                                ? "أضف أول مشهور إلى قائمة المتابعة."
                                : "Add your first creator to the watchlist."}
                            </p>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
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
      <aside className="fixed inset-y-0 start-0 z-40 hidden w-72 border-e border-slate-800 bg-slate-950 text-white lg:flex lg:flex-col">
        <div className="flex h-16 items-center border-b border-slate-800 px-4 [&_span]:text-white">
          <KliprLogo href="/dashboard" className="[&_svg]:size-9" />
        </div>
        <div className="flex-1 overflow-hidden">{nav}</div>
        <div className="p-4 pt-2">
          <p className="rounded-full bg-slate-900 px-3 py-2 text-center text-[11px] font-semibold text-slate-500">Klipr.cloud • Studio v1.0</p>
        </div>
      </aside>
      {open && (
        <div
          className="fixed inset-0 z-50 bg-slate-950/35 lg:hidden"
          onClick={() => setOpen(false)}
        >
          <aside
            className="h-full w-[86%] max-w-80 bg-slate-950 text-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex h-16 items-center justify-between border-b border-slate-800 px-4 [&_span]:text-white">
              <KliprLogo href="/dashboard" className="[&_svg]:size-9" />
              <button
                onClick={() => setOpen(false)}
                className="rounded-lg p-2 hover:bg-slate-800"
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
