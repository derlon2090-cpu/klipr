import "./globals.css";
export const metadata = { title: { default: "Klipr.cloud", template: "%s · Klipr.cloud" }, description: "The on-demand AI clip studio for live creators." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
