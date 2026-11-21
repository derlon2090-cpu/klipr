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
  viral_score?: number;
  hook_title?: string | null;
  highlight_reason?: string | null;
  transcript_snippet?: string | null;
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
  auto_trim_ads: boolean;
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
  overlay_logo_key: string | null;
  overlay_logo_url?: string | null;
  overlay_creator_name: string | null;
  overlay_position: "top-right" | "top-left" | "bottom-center";
};
export type SavedThumbnail = {
  id: string;
  kind: "vod" | "short";
  key: string;
  url: string;
  selected: boolean;
};
export type WatchlistSubscription = {
  id: string;
  platform: "twitch" | "kick";
  channel_slug: string;
  channel_url: string;
  display_name: string;
  avatar_url: string | null;
  auto_record: boolean;
  delay_seconds: number;
  is_currently_live: boolean;
  created_at: string;
};
export type NotificationItem = {
  id: string;
  subscription_id: string | null;
  title: string;
  message: string;
  channel_url: string;
  status:
    | "pending_auto_record"
    | "auto_started"
    | "cancelled"
    | "manual_taken_over"
    | "session_expired";
  is_read: boolean;
  scheduled_for: string | null;
  created_at: string;
};
export type NotificationsResponse = {
  unread_count: number;
  items: NotificationItem[];
};
export type SessionStatus = "active" | "expiring_soon" | "expired" | "unset";
export type SessionCredential = {
  platform: "kick" | "twitch";
  has_session: boolean;
  status: SessionStatus;
  updated_at: string | null;
  expires_at: string | null;
};
export type Credentials = Record<"kick" | "twitch", SessionCredential>;
export type CreatorSuggestion = {
  id: string;
  creator_name: string;
  platform: "twitch" | "kick";
  channel_url: string | null;
  status: "new" | "reviewed";
  created_at: string;
};
export type VodStatus = "fetching_metadata" | "downloading" | "remuxing" | "ready" | "failed";
export type Vod = {
  id: string;
  url: string;
  platform: string;
  quality: string;
  status: VodStatus;
  title: string | null;
  streamer_name: string | null;
  duration_seconds: number | null;
  thumbnail_url: string | null;
  progress: number;
  download_speed: string | null;
  eta_seconds: number | null;
  file_size: number | null;
  error: string | null;
  download_url: string | null;
  created_at: string;
  updated_at: string;
};
const API = (process.env.NEXT_PUBLIC_API_URL || "/api").replace(/\/$/, "");

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown; message?: unknown } | null)?.detail ??
    (body as { message?: unknown } | null)?.message;
  if (Array.isArray(detail)) {
    const fields = detail
      .map((item) => {
        const value = item as { loc?: unknown[]; msg?: unknown };
        const field = Array.isArray(value.loc) ? value.loc.filter((part) => part !== "body").join(".") : "";
        return field ? `${field}: ${String(value.msg ?? "invalid value")}` : String(value.msg ?? "invalid value");
      })
      .join(" · ");
    return `خطأ في البيانات (${status}): ${fields}`;
  }
  if (typeof detail === "string" && detail.trim()) return `${detail} (${status})`;
  return `فشل الطلب من الخادم (${status})`;
}

function handleUnauthorized(path: string) {
  if (typeof window === "undefined" || path.startsWith("/auth/")) return;
  // The auth cookie is HttpOnly; the logout endpoint clears it server-side.
  void fetch(`${API}/auth/logout`, { method: "POST", credentials: "include" }).catch(() => undefined);
  window.location.assign("/login?reason=session-expired");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new Error("تعذّر الاتصال بالخادم — تأكد من تشغيل الباك إند والاتصال بالشبكة.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 401) handleUnauthorized(path);
    throw Object.assign(new Error(errorMessage(response.status, body)), { detail: body?.detail, status: response.status });
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
async function upload<T>(path: string, body: FormData): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      method: "POST",
      body,
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    throw new Error("تعذّر الاتصال بالخادم — تأكد من تشغيل الباك إند والاتصال بالشبكة.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    if (response.status === 401) handleUnauthorized(path);
    throw Object.assign(new Error(errorMessage(response.status, data)), { detail: data?.detail, status: response.status });
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
  suggestCreator: (payload: {
    creator_name: string;
    platform: "twitch" | "kick";
    channel_url?: string;
  }) =>
    request<CreatorSuggestion>("/creator-suggestions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  creatorSuggestions: () =>
    request<CreatorSuggestion[]>("/creator-suggestions"),
  updateCreatorSuggestion: (id: string, status: "new" | "reviewed") =>
    request<CreatorSuggestion>(`/creator-suggestions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  deleteCreatorSuggestion: (id: string) =>
    request<void>(`/creator-suggestions/${id}`, { method: "DELETE" }),
  watchlist: () => request<WatchlistSubscription[]>("/watchlist"),
  subscribeCreator: (channel_url: string) =>
    request<WatchlistSubscription>("/watchlist", {
      method: "POST",
      body: JSON.stringify({
        channel_url,
        auto_record: true,
        delay_seconds: 30,
      }),
    }),
  updateSubscription: (
    id: string,
    patch: { auto_record?: boolean; delay_seconds?: number },
  ) =>
    request<WatchlistSubscription>(`/watchlist/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  unsubscribeCreator: (id: string) =>
    request<void>(`/watchlist/${id}`, { method: "DELETE" }),
  notifications: () => request<NotificationsResponse>("/notifications"),
  readAllNotifications: () =>
    request<void>("/notifications/read-all", { method: "POST" }),
  credentials: () => request<Credentials>("/credentials"),
  saveCredential: (platform: "kick" | "twitch", content: string) =>
    request<SessionCredential>(`/credentials/${platform}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  deleteCredential: (platform: "kick" | "twitch") =>
    request<void>(`/credentials/${platform}`, { method: "DELETE" }),
  cancelAutoRecord: (id: string) =>
    request<NotificationItem>(`/notifications/${id}/cancel`, {
      method: "POST",
    }),
  streams: () => request<Stream[]>("/streams"),
  vods: () => request<Vod[]>("/vods"),
  importVod: (url: string, quality = "best") =>
    request<Vod>("/vods/import", { method: "POST", body: JSON.stringify({ url, quality }) }),
  vodStatus: (id: string) => request<Vod>(`/vods/status/${id}`),
  deleteVod: (id: string) => request<void>(`/vods/${id}`, { method: "DELETE" }),
  openVodInEditor: (id: string) => request<Stream>(`/vods/${id}/open-in-editor`, { method: "POST" }),
  generateVodClips: (id: string) => request<void>(`/vods/${id}/generate-clips`, { method: "POST", body: JSON.stringify({}) }),
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
  selectThumbnail: (id: string) =>
    request<SavedThumbnail>(`/branding/thumbnails/${id}/select`, {
      method: "POST",
    }),
  deleteSavedThumbnail: (id: string) =>
    request<void>(`/branding/thumbnails/${id}`, { method: "DELETE" }),
  saveBranding: (
    branding: Omit<
      Branding,
      | "archive_logo_key"
      | "archive_logo_url"
      | "default_thumbnail_key"
      | "default_thumbnail_url"
      | "default_short_thumbnail_key"
      | "default_short_thumbnail_url"
      | "overlay_logo_key"
      | "overlay_logo_url"
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
  uploadOverlayLogo: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return upload<{ overlay_logo_key: string; overlay_logo_url?: string }>("/branding/overlay-logo", body);
  },
  deleteOverlayLogo: () => request<void>("/branding/overlay-logo", { method: "DELETE" }),
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
    const body = new FormData();
    body.append("file", file);
    return upload<{ key: string; url: string }>(
      `/recordings/${id}/thumbnail`,
      body,
    );
  },
  uploadClipThumbnail: (id: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return upload<{ key: string; url: string }>(`/clips/${id}/thumbnail`, body);
  },
};
