"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Clapperboard, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";

type Step = "password" | "email";

export default function AccessPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("password");
  const [value, setValue] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const email = step === "email";

  useEffect(() => { api.me().then(() => router.replace("/dashboard")).catch(() => undefined); }, [router]);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setLoading(true); setMessage("");
    try {
      if (email) { await api.email(value); router.replace("/dashboard"); }
      else { await api.password(value); setValue(""); setStep("email"); }
    } catch (error) {
      const detail = (error as { detail?: { retry_after?: number; remaining?: number } }).detail;
      if (typeof detail === "object" && detail?.retry_after) setMessage(`تم إيقاف المحاولة لمدة ${Math.ceil(detail.retry_after / 60)} دقائق لحماية الحساب.`);
      else if (typeof detail === "object" && detail?.remaining !== undefined) setMessage(`كلمة المرور غير صحيحة. متبقي ${detail.remaining} محاولات.`);
      else setMessage(error instanceof Error ? error.message : "تعذر التحقق من البيانات.");
    } finally { setLoading(false); }
  };

  return <main dir="rtl" className="relative min-h-screen overflow-hidden bg-[#090a0a] text-white">
    <div className="absolute inset-x-0 top-0 h-[56vh] bg-[radial-gradient(circle_at_50%_25%,rgba(52,211,153,.38),transparent_40%),linear-gradient(135deg,#064e3b_0%,#047857_44%,#052e27_100%)]" />
    <div className="absolute inset-x-0 top-0 h-[56vh] opacity-[.14] [background-image:linear-gradient(rgba(255,255,255,.42)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.42)_1px,transparent_1px)] [background-size:34px_34px]" />
    <div className="absolute inset-x-0 top-[56vh] h-px bg-emerald-300/30" />
    <div className="relative mx-auto flex min-h-screen w-full max-w-xl flex-col px-5 pt-16 sm:pt-20">
      <header className="text-center">
        <div className="mx-auto mb-5 grid size-12 place-items-center rounded-2xl border border-white/25 bg-white/10 text-emerald-100 shadow-xl shadow-emerald-950/40 backdrop-blur"><Clapperboard size={25} /></div>
        <p className="mb-3 text-[11px] font-black tracking-[.34em] text-emerald-100">KLIPR.CLOUD</p>
        <h1 className="text-4xl font-black tracking-tight sm:text-5xl">بوابة صُنّاع المحتوى</h1>
        <p className="mt-3 text-emerald-50/80">وصول خاص إلى استوديو Klipr واللحظات الذهبية.</p>
      </header>
      <section className="z-10 mt-11 rounded-[30px] border border-white/10 bg-[#141615] p-6 shadow-2xl shadow-black/60 sm:p-10">
        <div className="mb-8 flex items-center justify-center gap-3 text-sm">
          <span className={`grid size-9 place-items-center rounded-full ${!email ? "bg-emerald-400 text-black" : "border border-emerald-400/30 bg-emerald-400/10 text-emerald-300"}`}><LockKeyhole size={16} /></span>
          <i className="h-px w-12 bg-zinc-700" />
          <span className={`grid size-9 place-items-center rounded-full ${email ? "bg-emerald-400 text-black" : "bg-zinc-800 text-zinc-500"}`}><Mail size={16} /></span>
        </div>
        <div className="mb-8 text-center">
          <span className="inline-flex items-center gap-2 text-sm font-bold text-emerald-300"><ShieldCheck size={17} />{email ? "التحقق من البريد" : "وصول محمي"}</span>
          <h2 className="mt-3 text-2xl font-black">{email ? "أدخل بريدك المعتمد" : "أدخل كلمة المرور"}</h2>
          {email && <p className="mt-2 text-sm leading-6 text-zinc-500">نحتاج تأكيد الهوية قبل فتح لوحة Klipr.</p>}
        </div>
        <form onSubmit={submit}>
          <label className="mb-2 block text-sm font-bold text-zinc-300">{email ? "البريد الإلكتروني" : "كلمة المرور"}</label>
          <div className="flex items-center rounded-xl border border-white/10 bg-black/25 px-4 transition focus-within:border-emerald-400/70 focus-within:ring-2 focus-within:ring-emerald-400/15">
            <span className="text-zinc-500">{email ? <Mail size={18} /> : <LockKeyhole size={18} />}</span>
            <input autoFocus value={value} onChange={event => setValue(event.target.value)} type={email ? "email" : "password"} autoComplete={email ? "email" : "current-password"} className="h-14 w-full bg-transparent px-3 text-right outline-none placeholder:text-zinc-700" placeholder={email ? "name@example.com" : "••••••••••••"} required />
          </div>
          {message && <p role="alert" className="mt-3 rounded-lg border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-200">{message}</p>}
          <button disabled={loading} className="mt-5 flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-l from-emerald-300 to-emerald-400 font-black text-emerald-950 shadow-lg shadow-emerald-500/10 transition hover:from-emerald-200 hover:to-emerald-300 disabled:opacity-60">
            {loading ? "جارٍ التحقق…" : email ? "فتح لوحة التحكم" : "متابعة"}<ArrowRight size={18} className="rotate-180" />
          </button>
        </form>
      </section>
      <footer className="mt-auto py-8 text-center text-xs text-zinc-600">Klipr.cloud · وصول خاص ومحمي</footer>
    </div>
  </main>;
}
