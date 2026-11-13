import "./globals.css";
import { LanguageProvider } from "@/components/language";
export const metadata = { title: { default: "Klipr.cloud", template: "%s · Klipr.cloud" }, description: "The on-demand AI clip studio for live creators." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="ar" dir="rtl"><body><LanguageProvider>{children}</LanguageProvider></body></html>; }
