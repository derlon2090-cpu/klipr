import type { Config } from "tailwindcss";
export default { content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"], theme: { extend: { colors: { ink: "#0f172a", panel: "#ffffff", acid: "#10b981", "klipr-violet": "#7e22ce" } } }, plugins: [] } satisfies Config;
