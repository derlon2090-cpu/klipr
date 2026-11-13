"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const router = useRouter(); const [ready, setReady] = useState(false);
  useEffect(() => { api.me().then(() => setReady(true)).catch(() => router.replace("/")); }, [router]);
  return ready ? <>{children}</> : <div className="grid min-h-screen place-items-center bg-ink text-emerald-300">جارٍ تأمين الجلسة…</div>;
}
