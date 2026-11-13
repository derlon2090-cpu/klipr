import Link from "next/link";

type LogoProps = { href?: string; compact?: boolean; className?: string };

export function KliprLogo({ href = "/", compact = false, className = "" }: LogoProps) {
  const mark = <svg aria-hidden="true" className="shrink-0" viewBox="0 0 96 96" fill="none"><path fill="#08A85A" d="M18 8h22c5.5 0 10 4.5 10 10v20.7L71.7 12A10 10 0 0 1 87.2 24.7L61 48l26.2 23.3A10 10 0 0 1 71.7 84L50 57.3V78c0 5.5-4.5 10-10 10H18C12.5 88 8 83.5 8 78V18C8 12.5 12.5 8 18 8Z"/><path fill="white" d="M30 28.4c0-3.1 3.4-5 6.1-3.3l27 16.8a7.2 7.2 0 0 1 0 12.2l-27 16.8A4 4 0 0 1 30 67.5V28.4Z"/></svg>;
  return <Link href={href} aria-label="Klipr home" className={`inline-flex items-center gap-2.5 ${className}`}>{mark}{!compact && <span className="font-[Arial_Rounded_MT_Bold,Arial,sans-serif] text-[1.55rem] font-black tracking-[-0.09em] text-black">Klipr</span>}</Link>;
}
