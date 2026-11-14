export type Status =
  | "queued"
  | "recording"
  | "reconnecting"
  | "processing"
  | "ready"
  | "failed";
export type Clip = {
  id: string;
  start_seconds: number;
  end_seconds: number;
  score: number;
  transcript: string | null;
  url: string | null;
  thumbnail_url?: string | null;
};
export type ArchiveShort = Clip & {
  stream_id: string;
  source_url: string;
  platform: "twitch" | "kick";
  remove_music: boolean;
};
export type Stream = {
  id: string;
  source_url: string;
  platform: "twitch" | "kick";
  status: Status;
  master_url: string | null;
  thumbnail_url?: string | null;
  target_clip_duration?: number;
  started_at: string | null;
  ended_at: string | null;
  error: string | null;
  stop_requested: boolean;
  layout_mode: "center" | "split";
  remove_music: boolean;
  clip_count?: number;
  clips?: Clip[];
};
export type StreamPreview = {
  platform: "twitch" | "kick";
  streamer_name: string;
  title: string;
  live: boolean;
  thumbnail_url: string | null;
};
export type Branding = {
  enable_end_screen: boolean;
  remove_music: boolean;
  use_default_thumbnail: boolean;
  outro_duration_seconds: number;
  archive_channel_name: string | null;
  archive_tagline: string | null;
  archive_logo_key: string | null;
  archive_logo_url?: string | null;
  default_thumbnail_key: string | null;
  default_thumbnail_url?: string | null;
  default_short_thumbnail_key: string | null;
  default_short_thumbnail_url?: string | null;
  default_left_vod_id: string | null;
  default_right_vod_id: string | null;
};
export type SavedThumbnail = {
  id: string;
  kind: "vod" | "short";
  key: string;
  url: string;
  selected: boolean;
};
export type WatchlistSubscription = {
  id: string; platform: "twitch" | "kick"; channel_slug: string; channel_url: string;
  display_name: string; avatar_url: string | null; auto_record: boolean;
  delay_seconds: number; is_currently_live: boolean; created_at: string;
};
export type NotificationItem = {
  id: string; subscription_id: string | null; title: string; message: string;
  channel_url: string; status: "pending_auto_record" | "auto_started" | "cancelled" | "manual_taken_over";
  is_read: boolean; scheduled_for: string | null; created_at: string;
};
export type NotificationsResponse = { unread_count: number; items: NotificationItem[] };
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw Object.assign(
      new Error(
        typeof body?.detail === "string" ? body.detail : "Request failed",
      ),
      { detail: body?.detail },
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
async function upload<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    body,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(
      typeof data?.detail === "string" ? data.detail : "Request failed",
    );
  }
  return response.json();
}
export const api = {
  password: (password: string) =>
    request<{ next: "email" }>("/auth/password", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  email: (email: string) =>
    request<{ email: string }>("/auth/email", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  me: () => request<{ email: string }>("/auth/me"),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  watchlist: () => request<WatchlistSubscription[]>("/watchlist"),
  subscribeCreator: (channel_url: string) => request<WatchlistSubscription>("/watchlist", { method: "POST", body: JSON.stringify({ channel_url, auto_record: true, delay_seconds: 30 }) }),
  updateSubscription: (id: string, patch: { auto_record?: boolean; delay_seconds?: number }) => request<WatchlistSubscription>(`/watchlist/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  unsubscribeCreator: (id: string) => request<void>(`/watchlist/${id}`, { method: "DELETE" }),
  notifications: () => request<NotificationsResponse>("/notifications"),
  readAllNotifications: () => request<void>("/notifications/read-all", { method: "POST" }),
  cancelAutoRecord: (id: string) => request<NotificationItem>(`/notifications/${id}/cancel`, { method: "POST" }),
  streams: () => request<Stream[]>("/streams"),
  archiveShorts: () => request<ArchiveShort[]>("/archive/shorts"),
  stream: (id: string) => request<Stream>(`/streams/${id}`),
  preview: (stream_url: string) =>
    request<StreamPreview>("/streams/preview", {
      method: "POST",
      body: JSON.stringify({ stream_url }),
    }),
  record: (stream_url: string, options?: { remove_music?: boolean }) =>
    request<Stream>("/streams/record", {
      method: "POST",
      body: JSON.stringify({
        stream_url,
        layout_mode: "split",
        ...options,
      }),
    }),
  stop: (id: string) =>
    request<void>(`/streams/${id}/stop`, { method: "POST" }),
  process: (
    id: string,
    options?: {
      duration_seconds?: number;
      max_clips?: number;
      custom_headline?: string;
      layout_mode?: "center" | "split";
      discord_webhook_url?: string;
      embed_intro_cover?: boolean;
      remove_music?: boolean;
    },
  ) =>
    request<void>(`/recordings/${id}/clips/generate`, {
      method: "POST",
      body: JSON.stringify(options ?? {}),
    }),
  remove: (id: string) =>
    request<void>(`/recordings/${id}`, { method: "DELETE" }),
  branding: () => request<Branding>("/branding"),
  savedThumbnails: () => request<SavedThumbnail[]>("/branding/thumbnails"),
  selectThumbnail: (id: string) => request<SavedThumbnail>(`/branding/thumbnails/${id}/select`, { method: "POST" }),
  deleteSavedThumbnail: (id: string) => request<void>(`/branding/thumbnails/${id}`, { method: "DELETE" }),
  saveBranding: (
    branding: Omit<
      Branding,
      | "archive_logo_key"
      | "archive_logo_url"
      | "default_thumbnail_key"
      | "default_thumbnail_url"
      | "default_short_thumbnail_key"
      | "default_short_thumbnail_url"
    >,
  ) =>
    request<Branding>("/branding", {
      method: "PUT",
      body: JSON.stringify(branding),
    }),
  uploadLogo: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return upload<{ archive_logo_key: string; archive_logo_url?: string }>(
      "/branding/logo",
      body,
    );
  },
  deleteLogo: () => request<void>("/branding/logo", { method: "DELETE" }),
  uploadThumbnail: (file: File, kind: "vod" | "short") => {
    const body = new FormData();
    body.append("file", file);
    body.append("kind", kind);
    return upload<{
      kind: "vod" | "short";
      key: string;
      url: string;
      use_default_thumbnail: boolean;
    }>("/branding/thumbnail", body);
  },
  deleteThumbnail: (kind: "vod" | "short") =>
    request<void>(`/branding/thumbnail?kind=${kind}`, { method: "DELETE" }),
  uploadRecordingThumbnail: (id: string, file: File) => {
    const body = new FormData(); body.append("file", file);
    return upload<{ key: string; url: string }>(`/recordings/${id}/thumbnail`, body);
  },
  uploadClipThumbnail: (id: string, file: File) => {
    const body = new FormData(); body.append("file", file);
    return upload<{ key: string; url: string }>(`/clips/${id}/thumbnail`, body);
  },
};
