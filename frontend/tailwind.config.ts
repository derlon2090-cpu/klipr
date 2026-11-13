import type { Config } from "tailwindcss";
export default { content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"], theme: { extend: { colors: { ink: "#09090b", panel: "#15151a", acid: "#34d399", "klipr-violet": "#a78bfa" } } }, plugins: [] } satisfies Config;
