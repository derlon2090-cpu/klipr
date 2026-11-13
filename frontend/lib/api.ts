export type Status = "queued" | "recording" | "reconnecting" | "processing" | "ready" | "failed";
export type Clip = { id: string; start_seconds: number; end_seconds: number; score: number; transcript: string | null; url: string | null; thumbnail_url?: string | null };
export type Stream = { id: string; source_url: string; platform: "twitch" | "kick"; status: Status; master_url: string | null; thumbnail_url?: string | null; target_clip_duration?: number; started_at: string | null; ended_at: string | null; error: string | null; stop_requested: boolean; layout_mode: "center" | "split"; clip_count?: number; clips?: Clip[] };
export type StreamPreview = { platform: "twitch" | "kick"; streamer_name: string; title: string; live: boolean; thumbnail_url: string | null };
export type Branding = { enable_end_screen: boolean; outro_duration_seconds: number; archive_channel_name: string | null; archive_tagline: string | null; archive_logo_key: string | null; archive_logo_url?: string | null; default_left_vod_id: string | null; default_right_vod_id: string | null };
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
async function request<T>(path: string, init?: RequestInit): Promise<T> { const response = await fetch(`${API}${path}`, { ...init, credentials: "include", headers: { "Content-Type": "application/json", ...init?.headers }, cache: "no-store" }); if (!response.ok) { const body = await response.json().catch(() => null); throw Object.assign(new Error(typeof body?.detail === "string" ? body.detail : "Request failed"), { detail: body?.detail }); } return response.status === 204 ? undefined as T : response.json(); }
async function upload<T>(path: string, body: FormData): Promise<T> { const response = await fetch(`${API}${path}`, { method: "POST", body, credentials: "include", cache: "no-store" }); if (!response.ok) { const data = await response.json().catch(() => null); throw new Error(typeof data?.detail === "string" ? data.detail : "Request failed"); } return response.json(); }
export const api = {
  password: (password: string) => request<{ next: "email" }>("/auth/password", { method: "POST", body: JSON.stringify({ password }) }),
  email: (email: string) => request<{ email: string }>("/auth/email", { method: "POST", body: JSON.stringify({ email }) }),
  me: () => request<{ email: string }>("/auth/me"), logout: () => request<void>("/auth/logout", { method: "POST" }),
  streams: () => request<Stream[]>("/streams"), stream: (id: string) => request<Stream>(`/streams/${id}`),
  preview: (stream_url: string) => request<StreamPreview>("/streams/preview", { method: "POST", body: JSON.stringify({ stream_url }) }),
  record: (stream_url: string, layout_mode: "center" | "split", discord_webhook_url?: string, options?: { custom_headline?: string; enable_end_screen?: boolean }) => request<Stream>("/streams/record", { method: "POST", body: JSON.stringify({ stream_url, layout_mode, discord_webhook_url: discord_webhook_url || null, custom_headline: options?.custom_headline || null, enable_end_screen: options?.enable_end_screen ?? true }) }),
  stop: (id: string) => request<void>(`/streams/${id}/stop`, { method: "POST" }),
  process: (id: string, options?: { duration_seconds?: number; max_clips?: number; custom_headline?: string; layout_mode?: "center" | "split"; discord_webhook_url?: string; embed_intro_cover?: boolean }) => request<void>(`/recordings/${id}/clips/generate`, { method: "POST", body: JSON.stringify(options ?? {}) }),
  remove: (id: string) => request<void>(`/recordings/${id}`, { method: "DELETE" }),
  branding: () => request<Branding>("/branding"),
  saveBranding: (branding: Omit<Branding, "archive_logo_key" | "archive_logo_url">) => request<Branding>("/branding", { method: "PUT", body: JSON.stringify(branding) }),
  uploadLogo: (file: File) => { const body = new FormData(); body.append("file", file); return upload<{ archive_logo_key: string; archive_logo_url?: string }>("/branding/logo", body); },
  deleteLogo: () => request<void>("/branding/logo", { method: "DELETE" })
};
