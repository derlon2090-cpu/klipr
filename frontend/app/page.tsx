"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight,
  Check,
  Clock3,
  Globe2,
  MessageCirclePlus,
  Play,
  Radio,
  Send,
  ShieldCheck,
  Video,
  WandSparkles,
  X,
} from "lucide-react";
import { KliprLogo } from "@/components/logo";
import { LanguageToggle, useLanguage } from "@/components/language";
import { api } from "@/lib/api";

const ar = {
  features: "المميزات",
  creators: "البثوث والمشاهير",
  how: "كيف يعمل",
  studio: "دخول الاستوديو",
  badge: "أرشفة تلقائية 24/7 لـ Twitch و Kick",
  heroLead: "لا تفوّت أي",
  heroAccent: "لحظة تستحق النشر.",
  heroBody:
    "Klipr يراقب بثوثك وبثوث صناعك المفضلين، ويحوّلها تلقائياً إلى أرشيف ومقاطع جاهزة لجمهورك.",
  launch: "ابدأ الأرشفة الآن",
  discover: "استكشف المشاهير",
  nowRecording: "يتم التسجيل الآن",
  radar: "رادار البث المباشر",
  mockTitle: "جلسة IRL في الرياض — بث حي",
  detected: "تم رصد البث تلقائياً",
  seconds: "ثانية حتى بدء الأرشفة",
  ready: "جاهز للتصدير",
  creatorOverline: "بثوث محفوظة، لحظات لا تضيع",
  creatorTitle: "تابع صناع المحتوى الذين تتابعهم.",
  creatorBody:
    "أضف أي قناة إلى رادارك ليبدأ Klipr حفظ البث تلقائياً فور انطلاقه.",
  all: "الكل",
  addCreator: "سجّل اقتراحك",
  archived: "أرشيف موثّق",
  featureOverline: "كل ما تحتاجه في مكان واحد",
  featureTitle: "من البث الحي إلى مكتبتك، بلا مجهود يدوي.",
  stepOverline: "كيف يعمل Klipr",
  stepTitle: "ثلاث خطوات تفصل بينك وبين أرشيف لا يفوت شيئاً.",
  footer: "أرشفة البث الذكية لصناع المحتوى.",
  product: "المنتج",
  legal: "روابط سريعة",
  privacy: "الخصوصية",
  terms: "الشروط",
  featuresList: [
    [
      "رادار 24/7 بدون حظر",
      "EventSub لـ Twitch ومراقب Kick ذكي يرصد البث وينبّهك قبل بدء التسجيل بـ30 ثانية.",
    ],
    [
      "ثامبنايل تلقائي بهوية المنصة",
      "غلاف جاهز بعنوان البث ولمسة بنفسجية لـ Twitch أو خضراء لـ Kick.",
    ],
    [
      "قصاص AI Shorts ذكي",
      "تقسيم Facecam وGameplay، وأبعاد عمودية وترجمة عربية وإنجليزية تلقائية.",
    ],
    [
      "نهاية يوتيوب آمنة",
      "شعار قناتك، فيديوهان مقترحان وعزل للموسيقى لحماية أفضل من DMCA.",
    ],
  ],
  steps: [
    ["أضف القناة", "ألصق رابط Twitch أو Kick مرة واحدة."],
    ["نرصد ونؤرشف", "نبدأ تلقائياً عند بدء البث."],
    ["انشر الأفضل", "صدّر VOD أو Shorts بهويتك."],
  ],
} as const;
const en = {
  features: "Features",
  creators: "Featured Creators",
  how: "How it works",
  studio: "Studio Login",
  badge: "24/7 automatic archiving for Twitch & Kick",
  heroLead: "Never miss a",
  heroAccent: "moment worth sharing.",
  heroBody:
    "Klipr watches your streams and favourite creators, then automatically turns every live moment into an archive and share-ready clips.",
  launch: "Launch Studio",
  discover: "Browse creators",
  nowRecording: "Recording now",
  radar: "Live stream radar",
  mockTitle: "Riyadh IRL session — live stream",
  detected: "Live stream detected automatically",
  seconds: "seconds until archive starts",
  ready: "Ready to export",
  creatorOverline: "Saved streams. Zero missed moments.",
  creatorTitle: "Follow the creators you already watch.",
  creatorBody:
    "Add any channel to your radar and Klipr starts preserving every broadcast as it goes live.",
  all: "All",
  addCreator: "Suggest a creator",
  archived: "Verified archive",
  featureOverline: "Everything in one studio",
  featureTitle: "From live stream to library, without the manual work.",
  stepOverline: "How Klipr works",
  stepTitle: "Three steps between you and an archive that misses nothing.",
  footer: "Smart stream archiving for modern creators.",
  product: "Product",
  legal: "Quick links",
  privacy: "Privacy",
  terms: "Terms",
  featuresList: [
    [
      "24/7 radar, no blocking",
      "Twitch EventSub and a stealth Kick watcher spot live streams and give you a 30-second heads-up.",
    ],
    [
      "Platform-native thumbnails",
      "Broadcast titles meet a ready-to-use violet Twitch or green Kick cover.",
    ],
    [
      "Smarter AI Shorts",
      "Facecam + gameplay split layouts, vertical framing, and automatic Arabic/English captions.",
    ],
    [
      "YouTube-ready, DMCA safer",
      "Your channel mark, two recommended videos and music isolation for safer publishing.",
    ],
  ],
  steps: [
    ["Add a channel", "Paste a Twitch or Kick URL once."],
    ["We detect & archive", "Capture starts when the stream does."],
    ["Publish the best bits", "Export branded VODs or Shorts."],
  ],
} as const;
type Copy = typeof ar | typeof en;
const creators = [
  {
    name: "شـونق",
    en: "SHoNgxBoNg",
    initials: "ش",
    platform: "Twitch",
    color: "bg-violet-100 text-violet-800",
    halo: "from-violet-500 to-fuchsia-500",
  },
  {
    name: "دربحه",
    en: "Drb7h",
    initials: "د",
    platform: "Kick",
    color: "bg-green-100 text-green-700",
    halo: "from-green-500 to-emerald-400",
  },
  {
    name: "بندريتا",
    en: "BanderitaX",
    initials: "ب",
    platform: "Twitch",
    color: "bg-violet-100 text-violet-800",
    halo: "from-indigo-500 to-violet-500",
  },
  {
    name: "أبو فلة",
    en: "AboFlah",
    initials: "أ",
    platform: "Kick",
    color: "bg-green-100 text-green-700",
    halo: "from-emerald-500 to-teal-400",
  },
  {
    name: "ماهركو",
    en: "Maherco",
    initials: "م",
    platform: "Twitch",
    color: "bg-violet-100 text-violet-800",
    halo: "from-purple-500 to-violet-400",
  },
  {
    name: "فهد سال",
    en: "Fahad Sal",
    initials: "ف",
    platform: "Kick",
    color: "bg-green-100 text-green-700",
    halo: "from-lime-500 to-emerald-500",
  },
];
export default function LandingPage() {
  const { language } = useLanguage();
  const [suggestionOpen, setSuggestionOpen] = useState(false);
  const [creatorFilter, setCreatorFilter] = useState<"all" | "Twitch" | "Kick">(
    "all",
  );
  const t = language === "ar" ? ar : en;
  const arMode = language === "ar";
  const arrow = <ArrowRight size={17} className={arMode ? "rotate-180" : ""} />;
  const visibleCreators =
    creatorFilter === "all"
      ? creators
      : creators.filter((creator) => creator.platform === creatorFilter);
  return (
    <main className="min-h-screen overflow-x-hidden bg-white text-slate-900">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[700px] bg-[radial-gradient(ellipse_at_12%_10%,rgba(16,185,129,.15),transparent_37%),radial-gradient(ellipse_at_89%_22%,rgba(5,150,105,.10),transparent_30%)]" />
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur-md">
        <nav className="mx-auto flex h-[76px] max-w-7xl items-center justify-between px-5 sm:px-8">
          <KliprLogo className="[&_svg]:size-10" />
          <div className="hidden items-center text-sm font-bold text-slate-600 md:flex">
            <a
              href="#creators"
              className="rounded-lg px-4 py-2 transition hover:bg-emerald-50 hover:text-emerald-700"
            >
              {t.creators}
            </a>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <LanguageToggle />
            <Link
              href="/login"
              className="hidden rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 sm:inline-flex"
            >
              {t.studio}
            </Link>
          </div>
        </nav>
      </header>
      <section className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 pb-24 pt-20 sm:px-8 lg:grid-cols-[1.05fr_.95fr] lg:pb-32 lg:pt-28">
        <div className={arMode ? "lg:text-right" : "lg:text-left"}>
          <p className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-xs font-extrabold text-emerald-800">
            <span className="size-2 animate-pulse rounded-full bg-emerald-500" />
            {t.badge}
          </p>
          <h1 className="mt-7 max-w-3xl text-5xl font-black leading-[1.03] tracking-[-.055em] sm:text-6xl lg:text-7xl">
            {t.heroLead}
            <br />
            <span className="text-emerald-600">{t.heroAccent}</span>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-8 text-slate-600 sm:text-lg">
            {t.heroBody}
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href="/login"
              className="inline-flex h-14 items-center gap-2 rounded-xl bg-emerald-600 px-5 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-700"
            >
              {t.launch}
              {arrow}
            </Link>
            <a
              href="#creators"
              className="inline-flex h-14 items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 text-sm font-bold text-slate-700 transition hover:border-emerald-300 hover:text-emerald-700"
            >
              {t.discover}
              <Globe2 size={17} />
            </a>
          </div>
          <div className="mt-10 flex items-center gap-5 text-xs font-semibold text-slate-500">
            <span className="inline-flex items-center gap-2">
              <Check className="text-emerald-600" size={17} />
              Twitch + Kick
            </span>
            <span className="inline-flex items-center gap-2">
              <Check className="text-emerald-600" size={17} />
              {arMode ? "إعداد خلال دقائق" : "Ready in minutes"}
            </span>
          </div>
        </div>
        <StudioMockup t={t} arMode={arMode} />
      </section>
      <section
        id="creators"
        className="scroll-mt-24 border-y border-slate-100 bg-slate-50/75 py-24"
      >
        <div className="mx-auto max-w-7xl px-5 sm:px-8">
          <div className="flex flex-col justify-between gap-8 lg:flex-row lg:items-end">
            <div>
              <p className="text-xs font-black uppercase tracking-[.19em] text-emerald-600">
                {t.creatorOverline}
              </p>
              <h2 className="mt-3 max-w-2xl text-3xl font-black tracking-[-.035em] sm:text-4xl">
                {t.creatorTitle}
              </h2>
              <p className="mt-4 max-w-xl leading-7 text-slate-600">
                {t.creatorBody}
              </p>
            </div>
            <div className="flex rounded-xl border border-slate-200 bg-white p-1 text-sm font-bold">
              {(["all", "Twitch", "Kick"] as const).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  onClick={() => setCreatorFilter(filter)}
                  className={`rounded-lg px-4 py-2 transition ${creatorFilter === filter ? "bg-emerald-600 text-white" : "text-slate-500 hover:text-emerald-700"}`}
                >
                  {filter === "all" ? t.all : filter}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {visibleCreators.map((creator) => (
              <article
                key={creator.en}
                className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-1 hover:border-emerald-300 hover:shadow-md"
              >
                <div className="flex items-start justify-between">
                  <span
                    className={`grid size-14 place-items-center rounded-2xl bg-gradient-to-br ${creator.halo} text-xl font-black text-white shadow-sm`}
                  >
                    {creator.initials}
                  </span>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-extrabold ${creator.color}`}
                  >
                    {creator.platform}
                  </span>
                </div>
                <div className="mt-5 flex items-center gap-2">
                  <h3 className="font-black">
                    {arMode ? creator.name : creator.en}
                  </h3>
                  <ShieldCheck size={16} className="text-emerald-500" />
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {arMode ? creator.en : creator.name}
                </p>
                <div className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-slate-50 px-2.5 py-1 text-[11px] font-bold text-slate-500">
                  <Video size={13} className="text-emerald-600" />
                  {t.archived}
                </div>
              </article>
            ))}
          </div>
          <div className="mt-8 flex flex-col items-center justify-between gap-4 rounded-2xl border border-emerald-100 bg-emerald-50 px-5 py-5 text-center sm:flex-row sm:text-start">
            <div className="flex items-center gap-3">
              <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-white text-emerald-700 shadow-sm">
                <MessageCirclePlus size={21} />
              </span>
              <p className="max-w-2xl text-sm font-semibold leading-6 text-emerald-950">
                {arMode
                  ? "تعرف مشهورًا بارزًا يستحق أن يكون ضمن أرشيف Klipr؟ اقترح اسمه ومنصته، وسنراجع إضافته إلى الرادار."
                  : "Know a standout creator who belongs in the Klipr archive? Send us their name and platform for review."}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setSuggestionOpen(true)}
              className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-700"
            >
              {t.addCreator}
              <ArrowRight size={16} className={arMode ? "rotate-180" : ""} />
            </button>
          </div>
        </div>
      </section>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-8 px-5 py-10 sm:px-8 md:flex-row md:items-start md:justify-between">
          <div>
            <KliprLogo className="[&_svg]:size-9" />
            <p className="mt-3 max-w-xs text-sm leading-6 text-slate-500">
              {t.footer}
            </p>
          </div>
          <div className="flex gap-10 text-sm">
            <div>
              <p className="font-black">{t.product}</p>
              <a
                href="#creators"
                className="mt-3 block text-slate-500 hover:text-emerald-700"
              >
                {t.creators}
              </a>
            </div>
            <div>
              <p className="font-black">{t.legal}</p>
              <span className="mt-3 block text-slate-500">{t.privacy}</span>
              <span className="mt-2 block text-slate-500">{t.terms}</span>
            </div>
          </div>
          <LanguageToggle />
        </div>
        <div className="border-t border-slate-100 px-5 py-5 text-center text-xs text-slate-400">
          © {new Date().getFullYear()} Klipr.cloud
        </div>
      </footer>
      {suggestionOpen && (
        <SuggestionModal ar={arMode} onClose={() => setSuggestionOpen(false)} />
      )}
    </main>
  );
}

function SuggestionModal({
  ar,
  onClose,
}: {
  ar: boolean;
  onClose: () => void;
}) {
  const [creatorName, setCreatorName] = useState("");
  const [platform, setPlatform] = useState<"twitch" | "kick">("twitch");
  const [channelUrl, setChannelUrl] = useState("");
  const [state, setState] = useState<"idle" | "saving" | "sent" | "error">(
    "idle",
  );
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setState("saving");
    setError("");
    try {
      await api.suggestCreator({
        creator_name: creatorName.trim(),
        platform,
        channel_url: channelUrl.trim() || undefined,
      });
      setState("sent");
    } catch (value) {
      setError(
        value instanceof Error
          ? value.message
          : ar
            ? "تعذّر إرسال الاقتراح."
            : "Could not send the suggestion.",
      );
      setState("error");
    }
  };
  return (
    <div
      className="fixed inset-0 z-[70] grid place-items-center bg-slate-950/50 p-4 backdrop-blur-sm"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="suggestion-title"
        className="w-full max-w-lg overflow-hidden rounded-3xl border border-white/70 bg-white shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-100 bg-gradient-to-br from-emerald-50 to-white p-6">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3 py-1 text-[11px] font-black text-emerald-700">
              <MessageCirclePlus size={14} />
              {ar ? "اقتراحات المجتمع" : "Community suggestions"}
            </span>
            <h2
              id="suggestion-title"
              className="mt-4 text-2xl font-black tracking-tight"
            >
              {ar ? "اقترح مشهورًا لإضافته" : "Suggest a creator"}
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              {ar
                ? "أرسل لنا الاسم والمنصة، وسيصل اقتراحك مباشرة إلى فريق Klipr للمراجعة."
                : "Share their name and platform. Your suggestion will go straight to the Klipr team for review."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl p-2 text-slate-400 transition hover:bg-white hover:text-slate-700"
            aria-label={ar ? "إغلاق" : "Close"}
          >
            <X size={20} />
          </button>
        </div>
        {state === "sent" ? (
          <div className="p-8 text-center">
            <span className="mx-auto grid size-16 place-items-center rounded-full bg-emerald-100 text-emerald-700">
              <Check size={30} />
            </span>
            <h3 className="mt-5 text-xl font-black">
              {ar ? "وصلنا اقتراحك، شكرًا لك!" : "Your suggestion is in!"}
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              {ar
                ? "سيراجع فريقنا المشهور والمنصة قبل إضافتهما إلى الرادار."
                : "Our team will review the creator and platform before adding them to the radar."}
            </p>
            <button
              type="button"
              onClick={onClose}
              className="mt-6 rounded-xl bg-emerald-600 px-6 py-3 text-sm font-bold text-white hover:bg-emerald-700"
            >
              {ar ? "تم" : "Done"}
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-5 p-6">
            <label className="block text-sm font-bold text-slate-700">
              {ar ? "اسم المشهور" : "Creator name"}
              <input
                autoFocus
                required
                minLength={2}
                maxLength={120}
                value={creatorName}
                onChange={(event) => setCreatorName(event.target.value)}
                placeholder={
                  ar ? "مثال: اسم صانع المحتوى" : "e.g. Creator name"
                }
                className="mt-2 h-12 w-full rounded-xl border border-slate-300 px-4 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100"
              />
            </label>
            <fieldset>
              <legend className="text-sm font-bold text-slate-700">
                {ar ? "المنصة" : "Platform"}
              </legend>
              <div className="mt-2 grid grid-cols-2 gap-3">
                {(["twitch", "kick"] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setPlatform(value)}
                    className={`rounded-xl border px-4 py-3 text-sm font-black transition ${platform === value ? (value === "twitch" ? "border-violet-400 bg-violet-50 text-violet-700 ring-2 ring-violet-100" : "border-emerald-400 bg-emerald-50 text-emerald-700 ring-2 ring-emerald-100") : "border-slate-200 text-slate-500 hover:border-slate-300"}`}
                  >
                    {value === "twitch" ? "Twitch" : "Kick"}
                  </button>
                ))}
              </div>
            </fieldset>
            <label className="block text-sm font-bold text-slate-700">
              {ar ? "رابط القناة (اختياري)" : "Channel URL (optional)"}
              <input
                type="url"
                value={channelUrl}
                onChange={(event) => setChannelUrl(event.target.value)}
                placeholder={
                  platform === "twitch"
                    ? "https://twitch.tv/creator"
                    : "https://kick.com/creator"
                }
                className="mt-2 h-12 w-full rounded-xl border border-slate-300 px-4 text-left outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100"
                dir="ltr"
              />
            </label>
            {error && (
              <p
                role="alert"
                className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700"
              >
                {error}
              </p>
            )}
            <button
              disabled={state === "saving"}
              className="inline-flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 text-sm font-black text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-60"
            >
              <Send size={17} />
              {state === "saving"
                ? ar
                  ? "جارٍ الإرسال..."
                  : "Sending..."
                : ar
                  ? "إرسال الاقتراح"
                  : "Send suggestion"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

function StudioMockup({ t, arMode }: { t: Copy; arMode: boolean }) {
  return (
    <div className="relative mx-auto w-full max-w-xl">
      <div className="absolute -inset-6 -z-10 rounded-full bg-emerald-300/20 blur-3xl" />
      <div className="overflow-hidden rounded-[26px] border border-slate-200 bg-white p-3 shadow-2xl shadow-emerald-950/10">
        <div className="rounded-[18px] bg-slate-900 p-4 text-white">
          <div className="flex items-center justify-between text-xs">
            <span className="inline-flex items-center gap-2 font-bold text-emerald-300">
              <Radio size={15} className="animate-pulse" />
              {t.nowRecording}
            </span>
            <span className="rounded-md bg-white/10 px-2 py-1 text-slate-300">
              1080p · 60fps
            </span>
          </div>
          <div className="relative mt-4 h-52 overflow-hidden rounded-xl bg-[radial-gradient(ellipse_at_30%_20%,#6540ae,transparent_45%),linear-gradient(135deg,#122033,#0c3140)] sm:h-64">
            <div className="absolute -end-4 top-8 size-44 rounded-full border-[20px] border-emerald-400/20" />
            <div className="absolute bottom-4 start-4 rounded-lg bg-black/35 px-3 py-2 text-sm font-bold backdrop-blur">
              {t.mockTitle}
            </div>
            <div className="absolute end-4 top-4 grid size-12 place-items-center rounded-full bg-white/90 text-emerald-700 shadow">
              <Play size={19} fill="currentColor" />
            </div>
          </div>
        </div>
        <div className="grid gap-3 p-2 pt-5 sm:grid-cols-[1fr_auto]">
          <div>
            <p className="text-xs font-black text-slate-700">{t.radar}</p>
            <p className="mt-1 text-xs text-slate-500">{t.detected}</p>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
              <span className="block h-full w-3/4 rounded-full bg-emerald-500" />
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800">
            <Clock3 size={16} />
            30 {t.seconds}
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-xs">
          <span className="inline-flex items-center gap-2 font-bold text-slate-600">
            <WandSparkles size={16} className="text-emerald-600" />
            {arMode ? "3 مقاطع ذكية قيد الإعداد" : "3 smart clips preparing"}
          </span>
          <span className="font-bold text-emerald-700">{t.ready}</span>
        </div>
      </div>
    </div>
  );
}
