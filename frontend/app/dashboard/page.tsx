"use client";
import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  Check,
  CheckCircle2,
  Clapperboard,
  Clock3,
  Download,
  ExternalLink,
  Film,
  Image as ImageIcon,
  MessageSquareText,
  Play,
  Radio,
  Search,
  Sparkles,
  Square,
  Trash2,
  Upload,
  FolderDown,
  WandSparkles,
  KeyRound,
  X,
} from "lucide-react";
import {
  api,
  AiMetadata,
  ArchiveShort,
  Branding,
  CreatorSuggestion,
  SavedThumbnail,
  Credentials,
  Stream,
  StreamPreview,
  StudioRender,
  SmartThumbnail,
  Vod,
} from "@/lib/api";
import { DashboardSection, Shell } from "@/components/shell";
import { StatusBadge } from "@/components/status";
import { useLanguage } from "@/components/language";

const emptyBranding: Branding = {
  enable_end_screen: true,
  remove_music: false,
  auto_trim_ads: false,
  use_default_thumbnail: true,
  outro_duration_seconds: 15,
  archive_channel_name: "",
  archive_tagline: "",
  archive_logo_key: null,
  archive_logo_url: null,
  default_thumbnail_key: null,
  default_thumbnail_url: null,
  default_short_thumbnail_key: null,
  default_short_thumbnail_url: null,
  default_left_vod_id: null,
  default_right_vod_id: null,
  overlay_logo_key: null,
  overlay_logo_url: null,
  overlay_creator_name: "",
  overlay_position: "top-right",
  auto_merge_branding: true,
  default_intro_key: null,
  default_outro_key: null,
  ai_music_removal: false,
  channel_banner_key: null,
  channel_banner_url: null,
};
const drb7hLogo = "/branding/drb7h-logo.png";
const drb7hBanner = "/branding/drb7h-channel-banner.png";
const validSections: DashboardSection[] = [
  "live",
  "vods",
  "shorts",
  "metadata",
  "settings",
  "suggestions",
  "sessions",
  "presets",
  "thumbnails",
  "intro-outro",
  "studio",
];
const platformClass = (platform: string) =>
  platform === "twitch"
    ? "bg-violet-100 text-violet-700"
    : "bg-lime-100 text-lime-800";
const elapsed = (start: string | null, now: number) => {
  if (!start) return "00:00:00";
  const seconds = Math.max(0, Math.floor((now - Date.parse(start)) / 1000));
  return [seconds / 3600, (seconds % 3600) / 60, seconds % 60]
    .map((n) => String(Math.floor(n)).padStart(2, "0"))
    .join(":");
};
const handle = (stream: Stream) => {
  try {
    return (
      new URL(stream.source_url).pathname.replace(/^\//, "") ||
      stream.source_url
    );
  } catch {
    return stream.source_url;
  }
};
const durationText = (stream: Stream) =>
  stream.started_at && stream.ended_at
    ? `${Math.max(1, Math.round((Date.parse(stream.ended_at) - Date.parse(stream.started_at)) / 60000))} min`
    : "—";
const vodDuration = (seconds: number | null) => {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600),
    m = Math.floor((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
};
const fileSize = (bytes: number | null) => {
  if (!bytes) return "—";
  return bytes >= 1024 ** 3
    ? `${(bytes / 1024 ** 3).toFixed(2)} GB`
    : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
};
const vodQualityText = (vod: Vod) => {
  const fps = vod.fps ? Math.round(vod.fps) : null;
  if (vod.height && vod.height >= 2160) return `4K 2160p${fps || 60}`;
  if (vod.height) return `${vod.height}p${fps || ""} Source`;
  return vod.quality === "4k" ? "4K 2160p60" : "Legacy source";
};
const bitrateText = (bitrate: number | null) =>
  bitrate ? `${(bitrate / 1_000_000).toFixed(1)} Mbps` : "—";

function SectionTitle({
  eyebrow,
  title,
  description,
  icon: Icon,
}: {
  eyebrow: string;
  title: string;
  description: string;
  icon: React.ComponentType<{ size?: number }>;
}) {
  return (
    <header className="mb-7 flex items-start gap-4">
      <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-emerald-100 text-emerald-700">
        <Icon size={23} />
      </span>
      <div>
        <p className="text-xs font-black uppercase tracking-[.18em] text-emerald-600">
          {eyebrow}
        </p>
        <h1 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">
          {title}
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
          {description}
        </p>
      </div>
    </header>
  );
}
function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}
const inputClass =
  "mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100";
const emptyCredentials: Credentials = {
  kick: {
    platform: "kick",
    has_session: false,
    status: "unset",
    updated_at: null,
    expires_at: null,
  },
  twitch: {
    platform: "twitch",
    has_session: false,
    status: "unset",
    updated_at: null,
    expires_at: null,
  },
};

export function DashboardWorkspace({
  initialSection = "live",
}: {
  initialSection?: DashboardSection;
}) {
  const { language } = useLanguage();
  const ar = language === "ar";
  const [section, setSection] = useState<DashboardSection>(initialSection),
    [streams, setStreams] = useState<Stream[]>([]),
    [archiveShorts, setArchiveShorts] = useState<ArchiveShort[]>([]),
    [detailed, setDetailed] = useState<Stream | null>(null),
    [url, setUrl] = useState(""),
    [preview, setPreview] = useState<StreamPreview | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [now, setNow] = useState(Date.now());
  const [options, setOptions] = useState(false);
  const [removeMusic, setRemoveMusic] = useState(false);
  const [search, setSearch] = useState(""),
    [filter, setFilter] = useState<"all" | "twitch" | "kick">("all"),
    [archiveKind, setArchiveKind] = useState<"vod" | "short">("vod"),
    [deleting, setDeleting] = useState<string | null>(null);
  const [selected, setSelected] = useState(""),
    [clipDuration, setClipDuration] = useState(30),
    [clipCount, setClipCount] = useState(3),
    [clipHeadline, setClipHeadline] = useState(""),
    [embedCover, setEmbedCover] = useState(true);
  const [thumbPlatform, setThumbPlatform] = useState<"twitch" | "kick">("kick"),
    [thumbFormat, setThumbFormat] = useState<"vod" | "short">("vod");
  const [branding, setBranding] = useState<Branding>(emptyBranding),
    [savedThumbnails, setSavedThumbnails] = useState<SavedThumbnail[]>([]),
    [logoPreview, setLogoPreview] = useState<string | null>(null),
    [savingBrand, setSavingBrand] = useState(false);
  const [suggestions, setSuggestions] = useState<CreatorSuggestion[]>([]),
    [suggestionsBusy, setSuggestionsBusy] = useState(false);
  const [credentials, setCredentials] = useState<Credentials>(emptyCredentials);
  const [sessionInput, setSessionInput] = useState<
    Record<"kick" | "twitch", string>
  >({ kick: "", twitch: "" });
  const [sessionBusy, setSessionBusy] = useState<"kick" | "twitch" | null>(
    null,
  );
  const [vods, setVods] = useState<Vod[]>([]);
  const [vodUrl, setVodUrl] = useState("");
  const vodQuality = "4k" as const;
  const [vodBusy, setVodBusy] = useState(false);
  const [studioVodId, setStudioVodId] = useState("");
  const [studioIntro, setStudioIntro] = useState<File | null>(null);
  const [studioOutro, setStudioOutro] = useState<File | null>(null);
  const [studioExportQuality, setStudioExportQuality] = useState<
    "original" | "4k"
  >("original");
  const [studioRender, setStudioRender] = useState<StudioRender | null>(null);
  const [studioBusy, setStudioBusy] = useState(false);
  const [editorRanges, setEditorRanges] = useState<
    Record<string, { start: string; end: string }>
  >({});
  const [editorToEnd, setEditorToEnd] = useState<Record<string, boolean>>({});
  const [smartVodId, setSmartVodId] = useState("");
  const [smartPlatform, setSmartPlatform] =
    useState<SmartThumbnail["platform"]>("youtube");
  const [smartStyle, setSmartStyle] =
    useState<SmartThumbnail["frame_style"]>("bold");
  const [smartItems, setSmartItems] = useState<SmartThumbnail[]>([]);
  const [smartBusy, setSmartBusy] = useState(false);
  const [metadataVodId, setMetadataVodId] = useState("");
  const [aiMetadata, setAiMetadata] = useState<AiMetadata | null>(null);
  const [metadataBusy, setMetadataBusy] = useState(false);

  const loadCredentials = () =>
    api
      .credentials()
      .then(setCredentials)
      .catch(() => undefined);

  const loadSuggestions = async () => {
    setSuggestionsBusy(true);
    try {
      setSuggestions(await api.creatorSuggestions());
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : ar
            ? "تعذّر تحميل الاقتراحات"
            : "Could not load suggestions",
      );
    } finally {
      setSuggestionsBusy(false);
    }
  };

  const load = async () => {
    try {
      const [nextStreams, nextShorts] = await Promise.all([
        api.streams(),
        api.archiveShorts(),
      ]);
      setStreams(nextStreams);
      setArchiveShorts(nextShorts);
    } catch (e) {
      setMessage(
        e instanceof Error
          ? e.message
          : ar
            ? "تعذّر تحميل التسجيلات"
            : "Could not load recordings",
      );
    }
  };
  const loadVods = () =>
    api
      .vods()
      .then(setVods)
      .catch(() => undefined);
  useEffect(() => {
    const query = new URLSearchParams(window.location.search).get(
      "section",
    ) as DashboardSection | null;
    if (query && validSections.includes(query)) setSection(query);
    load();
    loadVods();
    loadCredentials();
    Promise.all([api.branding(), api.savedThumbnails()])
      .then(([value, thumbnails]) => {
        setBranding(value);
        setSavedThumbnails(thumbnails);
        setRemoveMusic(value.remove_music);
      })
      .catch(() => undefined);
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (section === "suggestions") loadSuggestions();
    if (section === "sessions") loadCredentials();
    if (
      ["vods", "shorts", "metadata", "thumbnails", "suggestions"].includes(
        section,
      )
    )
      loadVods();
  }, [section]);
  useEffect(() => {
    if (
      !studioRender ||
      !["queued", "processing"].includes(studioRender.status)
    )
      return;
    const timer = window.setInterval(
      () =>
        api
          .studioRender(studioRender.id)
          .then(setStudioRender)
          .catch(() => undefined),
      2500,
    );
    return () => window.clearInterval(timer);
  }, [studioRender?.id, studioRender?.status]);
  useEffect(() => {
    if (
      !smartItems.some(
        (item) => item.status === "queued" || item.status === "processing",
      )
    )
      return;
    const timer = window.setInterval(() => {
      Promise.all(smartItems.map((item) => api.smartThumbnail(item.id)))
        .then(setSmartItems)
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [smartItems]);
  useEffect(() => {
    if (
      section !== "vods" ||
      !vods.some((vod) => !["ready", "failed"].includes(vod.status))
    )
      return;
    const timer = setInterval(loadVods, 2500);
    return () => clearInterval(timer);
  }, [section, vods]);
  useEffect(() => {
    if (
      section !== "clips" ||
      !streams.some((stream) => stream.status === "processing")
    )
      return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [section, streams]);
  useEffect(() => {
    const value = url.trim();
    setPreview(null);
    if (!/^https:\/\/(?:www\.|m\.)?(?:twitch\.tv|kick\.com)\//i.test(value))
      return;
    const timer = setTimeout(
      () =>
        api
          .preview(value)
          .then(setPreview)
          .catch(() => setPreview(null)),
      500,
    );
    return () => clearTimeout(timer);
  }, [url]);
  useEffect(() => {
    if (!selected) {
      setDetailed(null);
      return;
    }
    api
      .stream(selected)
      .then(setDetailed)
      .catch(() => setDetailed(null));
    const found = streams.find((s) => s.id === selected);
    if (found) setThumbPlatform(found.platform);
  }, [selected, streams]);
  const active = useMemo(
    () =>
      streams.filter((s) =>
        ["queued", "recording", "reconnecting"].includes(s.status),
      ),
    [streams],
  );
  const completed = useMemo(
    () => streams.filter((s) => !active.some((a) => a.id === s.id)),
    [streams, active],
  );
  useEffect(() => {
    if (!selected && completed[0]) setSelected(completed[0].id);
  }, [completed, selected]);
  const visibleArchive = completed.filter(
    (s) =>
      (filter === "all" || s.platform === filter) &&
      (!search.trim() ||
        `${handle(s)} ${s.source_url}`
          .toLowerCase()
          .includes(search.toLowerCase())),
  );
  const visibleArchiveShorts = archiveShorts.filter(
    (clip) =>
      (filter === "all" || clip.platform === filter) &&
      (!search.trim() ||
        `${handle({ source_url: clip.source_url } as Stream)} ${clip.transcript || ""}`
          .toLowerCase()
          .includes(search.toLowerCase())),
  );
  const changeSection = (next: DashboardSection) => {
    setSection(next);
    const directPaths: Partial<Record<DashboardSection, string>> = {
      vods: "/dashboard?section=vods",
      shorts: "/dashboard?section=shorts",
      metadata: "/dashboard?section=metadata",
      thumbnails: "/dashboard?section=thumbnails",
      suggestions: "/dashboard?section=suggestions",
      sessions: "/dashboard?section=sessions",
      settings: "/dashboard?section=settings",
    };
    window.history.replaceState(
      null,
      "",
      directPaths[next] || `/dashboard?section=${next}`,
    );
    setMessage("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const record = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await api.record(url, { remove_music: removeMusic });
      setUrl("");
      setPreview(null);
      await load();
      setMessage(ar ? "بدأ التسجيل بنجاح." : "Recording started successfully.");
    } catch (e) {
      setMessage(
        e instanceof Error
          ? e.message
          : ar
            ? "تعذّر بدء التسجيل"
            : "Could not start recording",
      );
    } finally {
      setBusy(false);
    }
  };
  const stop = async (id: string) => {
    try {
      await api.stop(id);
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  };
  const remove = async () => {
    if (!deleting) return;
    try {
      await api.remove(deleting);
      setDeleting(null);
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  };
  const importVod = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!vodUrl.trim()) return;
    setVodBusy(true);
    setMessage("");
    try {
      const item = await api.importVod(vodUrl.trim(), vodQuality);
      setVods((current) => [
        item,
        ...current.filter((vod) => vod.id !== item.id),
      ]);
      setVodUrl("");
      setMessage(
        ar
          ? "بدأ جلب البث المحفوظ في الخلفية."
          : "VOD import started in the background.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not start VOD import",
      );
    } finally {
      setVodBusy(false);
    }
  };
  const openVodInEditor = async (vod: Vod) => {
    setVodBusy(true);
    try {
      const stream = await api.openVodInEditor(vod.id);
      setStreams((current) => [stream, ...current]);
      setSelected(stream.id);
      changeSection("shorts");
      setMessage(
        ar
          ? "أصبح البث جاهزاً في أداة التقطيع."
          : "The VOD is ready in the clip editor.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not open VOD in editor",
      );
    } finally {
      setVodBusy(false);
    }
  };
  const generateVodClips = async (vod: Vod) => {
    setVodBusy(true);
    setMessage("");
    try {
      await api.generateVodClips(vod.id);
      await load();
      changeSection("shorts");
      setMessage(
        ar
          ? "بدأ التحليل والتقطيع التلقائي. ستُحفظ المقاطع النهائية في الأرشيف."
          : "Automatic analysis and clipping started. Finished clips will appear in the archive.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not start automatic clips",
      );
    } finally {
      setVodBusy(false);
    }
  };
  const removeVod = async (id: string) => {
    try {
      await api.deleteVod(id);
      setVods((current) => current.filter((vod) => vod.id !== id));
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not delete VOD",
      );
    }
  };
  const cancelVod = async (id: string) => {
    setVodBusy(true);
    setMessage("");
    try {
      const item = await api.cancelVod(id);
      setVods((current) => current.map((vod) => (vod.id === id ? item : vod)));
      setMessage(
        ar
          ? "تم إلغاء المعالجة فورياً وتحرير العامل."
          : "Processing cancelled immediately and the worker was released.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not cancel VOD processing",
      );
    } finally {
      setVodBusy(false);
    }
  };
  const generateMetadata = async (regenerate = false) => {
    if (!metadataVodId) return;
    setMetadataBusy(true);
    setMessage("");
    try {
      setAiMetadata(await api.generateAiMetadata(metadataVodId, regenerate));
      setMessage(
        ar
          ? "تم توليد العناوين والوصف والفصول بنجاح."
          : "Titles, description and chapters generated.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not generate metadata",
      );
    } finally {
      setMetadataBusy(false);
    }
  };
  const copyText = async (value: string) => {
    await navigator.clipboard.writeText(value);
    setMessage(ar ? "تم النسخ." : "Copied.");
  };
  const generate = async () => {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      await api.process(selected, {
        duration_seconds: clipDuration,
        max_clips: clipCount,
        custom_headline: clipHeadline,
        embed_intro_cover:
          embedCover && Boolean(branding.default_short_thumbnail_key),
        remove_music: removeMusic,
      });
      await load();
      setDetailed(await api.stream(selected));
      setMessage(
        ar
          ? "بدأ توليد الشورتات. ستظهر هنا عند اكتمال المعالجة."
          : "Short generation started. They will appear here when ready.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  const generateArchiveClips = async (stream: Stream) => {
    setBusy(true);
    setMessage("");
    try {
      await api.process(stream.id, {
        duration_seconds: 30,
        max_clips: 3,
        layout_mode: "split",
        remove_music: stream.remove_music,
      });
      await load();
      setMessage(
        ar
          ? "بدأ التعديل التلقائي. ستتحدث البطاقة حتى اكتمال الشورتات."
          : "Automatic editing started. This card will update until the Shorts are ready.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not start automatic editing",
      );
    } finally {
      setBusy(false);
    }
  };
  const saveBranding = async () => {
    setSavingBrand(true);
    setMessage("");
    try {
      const {
        archive_logo_key: _key,
        archive_logo_url: _url,
        default_thumbnail_key: _thumbnailKey,
        default_thumbnail_url: _thumbnailUrl,
        default_short_thumbnail_key: _shortThumbnailKey,
        default_short_thumbnail_url: _shortThumbnailUrl,
        overlay_logo_key: _overlayLogoKey,
        overlay_logo_url: _overlayLogoUrl,
        ...payload
      } = branding;
      setBranding(await api.saveBranding(payload));
      setMessage(ar ? "تم حفظ إعدادات الهوية." : "Branding settings saved.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    } finally {
      setSavingBrand(false);
    }
  };
  const uploadLogo = async (file?: File) => {
    if (!file) return;
    if (
      file.size > 5 * 1024 * 1024 ||
      !["image/png", "image/jpeg", "image/webp"].includes(file.type)
    ) {
      setMessage(
        ar
          ? "اختر صورة PNG أو JPG أو WebP بحجم أقل من 5MB."
          : "Choose a PNG, JPG or WebP image under 5MB.",
      );
      return;
    }
    const local = URL.createObjectURL(file);
    setLogoPreview(local);
    try {
      const result = await api.uploadLogo(file);
      setBranding((current) => ({
        ...current,
        archive_logo_key: result.archive_logo_key,
        archive_logo_url: result.archive_logo_url || local,
      }));
      setMessage(ar ? "تم رفع الشعار." : "Logo uploaded.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  };
  const deleteLogo = async () => {
    try {
      await api.deleteLogo();
      setLogoPreview(null);
      setBranding((current) => ({
        ...current,
        archive_logo_key: null,
        archive_logo_url: null,
      }));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  };
  const uploadOverlayLogo = async (file?: File) => {
    if (!file) return;
    if (
      file.size > 5 * 1024 * 1024 ||
      !["image/png", "image/jpeg", "image/webp"].includes(file.type)
    ) {
      setMessage(
        ar
          ? "اختر شعار PNG أو JPG أو WebP بحجم أقل من 5MB."
          : "Choose a PNG, JPG or WebP logo under 5MB.",
      );
      return;
    }
    try {
      const result = await api.uploadOverlayLogo(file);
      setBranding((current) => ({
        ...current,
        overlay_logo_key: result.overlay_logo_key,
        overlay_logo_url: result.overlay_logo_url || URL.createObjectURL(file),
      }));
      setMessage(ar ? "تم رفع شعار القالب." : "Preset logo uploaded.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    }
  };
  const deleteOverlayLogo = async () => {
    try {
      await api.deleteOverlayLogo();
      setBranding((current) => ({
        ...current,
        overlay_logo_key: null,
        overlay_logo_url: null,
      }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Delete failed");
    }
  };
  const persistPreset = async (patch: Partial<Branding>) => {
    const next = { ...branding, ...patch };
    setBranding(next);
    const {
      archive_logo_key: _logoKey,
      archive_logo_url: _logoUrl,
      default_thumbnail_key: _thumbnailKey,
      default_thumbnail_url: _thumbnailUrl,
      default_short_thumbnail_key: _shortThumbnailKey,
      default_short_thumbnail_url: _shortThumbnailUrl,
      overlay_logo_key: _overlayLogoKey,
      overlay_logo_url: _overlayLogoUrl,
      ...payload
    } = next;
    try {
      setBranding(await api.saveBranding(payload));
      setMessage(
        ar
          ? "تم حفظ الخيار وسيُطبّق تلقائيًا على كل بث جديد."
          : "Preset saved and will apply to every new recording.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  };
  const saveThumbnail = async () => {
    setBusy(true);
    setMessage("");
    try {
      const canvas = document.createElement("canvas");
      canvas.width = thumbFormat === "short" ? 1080 : 1920;
      canvas.height = thumbFormat === "short" ? 1920 : 1080;
      const canvasWidth = canvas.width;
      const canvasHeight = canvas.height;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas is unavailable");
      context.fillStyle = "#0f172a";
      context.fillRect(0, 0, canvas.width, canvas.height);
      if (thumbSource) {
        try {
          const source = await fetch(thumbSource).then((response) =>
            response.blob(),
          );
          const image = await createImageBitmap(source);
          const scale = Math.max(
            canvasWidth / image.width,
            canvasHeight / image.height,
          );
          const width = image.width * scale;
          const height = image.height * scale;
          context.drawImage(
            image,
            (canvasWidth - width) / 2,
            (canvasHeight - height) / 2,
            width,
            height,
          );
          context.fillStyle = "rgba(2,6,23,.25)";
          context.fillRect(0, 0, canvasWidth, canvasHeight);
        } catch {
          // The designed fallback remains usable when a remote source expires.
        }
      }
      const accent = thumbPlatform === "twitch" ? "#9146FF" : "#53FC18";
      context.strokeStyle = accent;
      context.lineWidth = 18;
      context.beginPath();
      context.roundRect(28, 28, canvasWidth - 56, canvasHeight - 56, 34);
      context.stroke();
      context.fillStyle = thumbPlatform === "twitch" ? "#9146FF" : "#20b94b";
      context.beginPath();
      context.roundRect(55, 55, 255, 72, 22);
      context.fill();
      context.fillStyle = "white";
      context.font = "900 26px Arial";
      context.fillText(`${thumbPlatform.toUpperCase()} · KLIPR`, 78, 100);
      const blob = await new Promise<Blob>((resolve, reject) =>
        canvas.toBlob(
          (value) => (value ? resolve(value) : reject(new Error("PNG failed"))),
          "image/png",
          0.95,
        ),
      );
      const result = await api.uploadThumbnail(
        new File([blob], `klipr-${thumbFormat}-thumbnail.png`, {
          type: "image/png",
        }),
        thumbFormat,
      );
      setBranding((current) =>
        thumbFormat === "short"
          ? {
              ...current,
              default_short_thumbnail_key: result.key,
              default_short_thumbnail_url: result.url,
            }
          : {
              ...current,
              default_thumbnail_key: result.key,
              default_thumbnail_url: result.url,
              use_default_thumbnail: true,
            },
      );
      setSavedThumbnails(await api.savedThumbnails());
      setMessage(
        ar
          ? thumbFormat === "short"
            ? "تم حفظ ثامبنيل الشورت الطولي لاستخدامه في بداية الشورتات."
            : "تم حفظ ثامبنيل البث العادي لكل التسجيلات الجديدة."
          : thumbFormat === "short"
            ? "Vertical Short thumbnail saved for Short intros."
            : "Regular VOD thumbnail saved for new recordings.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  const deleteThumbnail = async (kind: "vod" | "short" = thumbFormat) => {
    try {
      await api.deleteThumbnail(kind);
      setBranding((current) =>
        kind === "short"
          ? {
              ...current,
              default_short_thumbnail_key: null,
              default_short_thumbnail_url: null,
            }
          : {
              ...current,
              default_thumbnail_key: null,
              default_thumbnail_url: null,
              use_default_thumbnail: false,
            },
      );
      setSavedThumbnails(await api.savedThumbnails());
      setMessage(
        ar ? "تمت إزالة الثامبنيل المحفوظة." : "Saved thumbnail removed.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  };
  const chooseSavedThumbnail = async (thumbnail: SavedThumbnail) => {
    try {
      const selectedThumbnail = await api.selectThumbnail(thumbnail.id);
      setSavedThumbnails((current) =>
        current.map((item) => ({
          ...item,
          selected:
            item.kind === thumbnail.kind
              ? item.id === thumbnail.id
              : item.selected,
        })),
      );
      setBranding((current) =>
        thumbnail.kind === "short"
          ? {
              ...current,
              default_short_thumbnail_key: selectedThumbnail.key,
              default_short_thumbnail_url: selectedThumbnail.url,
            }
          : {
              ...current,
              default_thumbnail_key: selectedThumbnail.key,
              default_thumbnail_url: selectedThumbnail.url,
              use_default_thumbnail: true,
            },
      );
      if (thumbnail.kind === "short") setEmbedCover(true);
      setMessage(
        ar
          ? "تم اختيار الثامبنيل وتفعيلها تلقائيًا."
          : "Thumbnail selected and activated.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  };
  const removeSavedThumbnail = async (thumbnail: SavedThumbnail) => {
    try {
      await api.deleteSavedThumbnail(thumbnail.id);
      setSavedThumbnails((current) =>
        current.filter((item) => item.id !== thumbnail.id),
      );
      if (thumbnail.selected)
        setBranding((current) =>
          thumbnail.kind === "short"
            ? {
                ...current,
                default_short_thumbnail_key: null,
                default_short_thumbnail_url: null,
              }
            : {
                ...current,
                default_thumbnail_key: null,
                default_thumbnail_url: null,
                use_default_thumbnail: false,
              },
        );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Request failed");
    }
  };
  const thumbnailChoices = (kind: "vod" | "short", compact = false) => {
    const items = savedThumbnails.filter((item) => item.kind === kind);
    if (!items.length)
      return (
        <p className="mt-3 text-xs text-slate-400">
          {ar
            ? "لا توجد ثامبنيلات محفوظة بهذا المقاس بعد."
            : "No saved thumbnails in this format yet."}
        </p>
      );
    return (
      <div
        className={`mt-3 grid gap-2 ${compact ? (kind === "short" ? "grid-cols-4" : "grid-cols-3") : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4"}`}
      >
        {items.map((item) => (
          <button
            type="button"
            key={item.id}
            onClick={() => chooseSavedThumbnail(item)}
            className={`group relative overflow-hidden rounded-xl border-2 bg-slate-100 ${item.selected ? "border-emerald-500 ring-2 ring-emerald-100" : "border-transparent hover:border-slate-300"}`}
          >
            <img
              src={item.url}
              alt="Saved thumbnail"
              className={`${kind === "short" ? "aspect-[9/16]" : "aspect-video"} w-full object-cover`}
            />
            {item.selected && (
              <span className="absolute end-1 top-1 grid size-5 place-items-center rounded-full bg-emerald-500 text-white">
                <Check size={12} />
              </span>
            )}
          </button>
        ))}
      </div>
    );
  };
  const uploadRecordingThumbnail = async (streamId: string, file?: File) => {
    if (!file) return;
    try {
      const result = await api.uploadRecordingThumbnail(streamId, file);
      setStreams((current) =>
        current.map((stream) =>
          stream.id === streamId
            ? { ...stream, thumbnail_url: result.url }
            : stream,
        ),
      );
      if (detailed?.id === streamId)
        setDetailed({ ...detailed, thumbnail_url: result.url });
      setMessage(
        ar
          ? "تم حفظ غلاف البث وربطه بالأرشيف."
          : "VOD cover saved to the archive.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Upload failed");
    }
  };
  const uploadShortThumbnail = async (clipId: string, file?: File) => {
    if (!file) return;
    try {
      const result = await api.uploadClipThumbnail(clipId, file);
      setArchiveShorts((current) =>
        current.map((clip) =>
          clip.id === clipId ? { ...clip, thumbnail_url: result.url } : clip,
        ),
      );
      if (detailed)
        setDetailed({
          ...detailed,
          clips: detailed.clips?.map((clip) =>
            clip.id === clipId ? { ...clip, thumbnail_url: result.url } : clip,
          ),
        });
      setMessage(
        ar
          ? "تم حفظ غلاف الشورت وربطه بالمكتبة."
          : "Short cover saved to the library.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Upload failed");
    }
  };

  const picker = (
    <select
      value={selected}
      onChange={(e) => setSelected(e.target.value)}
      className={inputClass}
    >
      <option value="">
        {ar ? "اختر بثًا من الأرشيف" : "Select a VOD from the archive"}
      </option>
      {completed.map((stream) => (
        <option key={stream.id} value={stream.id}>
          {stream.platform.toUpperCase()} · {handle(stream)}
        </option>
      ))}
    </select>
  );
  const liveView = (
    <>
      <SectionTitle
        icon={Radio}
        eyebrow={ar ? "التسجيل المباشر" : "LIVE CAPTURE"}
        title={
          ar ? "البثوث النشطة والتسجيل" : "Live capture & active recordings"
        }
        description={
          ar
            ? "ألصق رابط Twitch أو Kick، راجع بيانات البث ثم ابدأ تسجيلًا عالي الجودة."
            : "Paste a Twitch or Kick URL, review the stream and start a high-quality recording."
        }
      />
      <form
        onSubmit={record}
        className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <label className="text-sm font-black text-slate-700">
          {ar ? "رابط البث المباشر" : "Live stream URL"}
        </label>
        <div className="mt-3 flex flex-col gap-3 xl:flex-row">
          <input
            className="h-14 min-w-0 flex-1 rounded-xl border border-slate-300 px-4 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://twitch.tv/creator  أو  https://kick.com/creator"
          />
          <button
            disabled={busy}
            className="inline-flex h-14 items-center justify-center gap-2 rounded-xl bg-emerald-500 px-6 font-black text-white shadow-sm hover:bg-emerald-600 disabled:opacity-50"
          >
            <Play size={17} fill="currentColor" />
            {busy
              ? ar
                ? "جارٍ البدء…"
                : "Starting…"
              : ar
                ? "ابدأ التسجيل عالي الجودة"
                : "Start high-quality recording"}
          </button>
        </div>
        {preview && (
          <div className="mt-5 grid gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-[180px_1fr]">
            {preview.thumbnail_url ? (
              <img
                src={preview.thumbnail_url}
                alt="Stream preview"
                className="aspect-video w-full rounded-xl object-cover"
              />
            ) : (
              <div className="grid aspect-video place-items-center rounded-xl bg-slate-200 text-slate-400">
                <Radio />
              </div>
            )}
            <div className="self-center">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-black ${platformClass(preview.platform)}`}
                >
                  {preview.platform.toUpperCase()}
                </span>
                <span
                  className={`flex items-center gap-1 text-xs font-black ${preview.live ? "text-emerald-600" : "text-slate-400"}`}
                >
                  <span
                    className={`size-2 rounded-full ${preview.live ? "animate-pulse bg-emerald-500" : "bg-slate-300"}`}
                  />
                  {preview.live
                    ? ar
                      ? "مباشر الآن"
                      : "LIVE NOW"
                    : ar
                      ? "غير متصل"
                      : "OFFLINE"}
                </span>
              </div>
              <p className="mt-3 font-black">{preview.streamer_name}</p>
              <p className="mt-1 text-sm text-slate-500">
                {preview.title ||
                  (ar ? "لا يتوفر عنوان للبث" : "No stream title available")}
              </p>
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={() => setOptions(!options)}
          className="mt-5 inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-black text-emerald-700"
        >
          {options
            ? ar
              ? "− إخفاء خيارات التسجيل"
              : "− Hide stream options"
            : ar
              ? "+ خيارات التسجيل"
              : "+ Stream options"}
        </button>
        {options && (
          <div className="mt-4 grid gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 lg:grid-cols-2">
            <label className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 lg:col-span-2">
              <input
                type="checkbox"
                checked={removeMusic}
                onChange={(e) => setRemoveMusic(e.target.checked)}
                className="mt-1 size-5 accent-emerald-500"
              />
              <span>
                <span className="block font-black">
                  {ar
                    ? "إزالة الأغاني وموسيقى الدونيشن تلقائياً (DMCA Safe)"
                    : "Remove donation songs & music automatically (DMCA Safe)"}
                </span>
                <span className="mt-1 block text-xs leading-5 text-slate-600">
                  {ar
                    ? "تُعزل الموسيقى الخلفية وأغاني الدونيشن مع الحفاظ على صوت الستريمر واضحًا."
                    : "Background music and donation songs are stripped while the streamer voice stays clear."}
                </span>
              </span>
            </label>
            <article className="flex flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start gap-4">
                <div className="h-24 w-40 shrink-0 overflow-hidden rounded-xl bg-slate-100">
                  {branding.default_thumbnail_url ? (
                    <img
                      src={branding.default_thumbnail_url}
                      alt="Saved thumbnail"
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="grid h-full place-items-center text-slate-400">
                      <ImageIcon />
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-black">
                    {ar ? "إضافة الثامبنيل" : "Add saved thumbnail"}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {branding.default_thumbnail_key
                      ? ar
                        ? "محفوظة وثابتة لكل بث جديد."
                        : "Saved and persistent for every new recording."
                      : ar
                        ? "صمّم واحفظ صورة من صانع الثامبنيل أولًا."
                        : "Create and save one in Thumbnail Studio first."}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {branding.default_thumbnail_key && (
                  <button
                    type="button"
                    onClick={() =>
                      persistPreset({
                        use_default_thumbnail: !branding.use_default_thumbnail,
                      })
                    }
                    className={`rounded-lg px-3 py-2 text-xs font-black ${branding.use_default_thumbnail ? "bg-emerald-500 text-white" : "border border-slate-300 text-slate-600"}`}
                  >
                    {branding.use_default_thumbnail
                      ? ar
                        ? "✓ تُدرج تلقائيًا"
                        : "✓ Auto insert on"
                      : ar
                        ? "إدراج الصورة"
                        : "Insert image"}
                  </button>
                )}
                <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-black text-emerald-700">
                  {ar ? "يُختار تلقائياً" : "Selected automatically"}
                </span>
                {branding.default_thumbnail_key && (
                  <button
                    type="button"
                    onClick={() => deleteThumbnail("vod")}
                    className="ms-auto rounded-lg px-3 py-2 text-xs font-black text-rose-600 hover:bg-rose-50"
                  >
                    {ar ? "إزالة" : "Remove"}
                  </button>
                )}
              </div>
              <div className="mt-4 border-t border-slate-100 pt-3">
                <p className="text-xs font-black text-slate-600">
                  {ar
                    ? "اختر ثامبنيل محفوظة للبث"
                    : "Choose a saved VOD thumbnail"}
                </p>
                {thumbnailChoices("vod", true)}
              </div>
            </article>
            <article className="flex flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start gap-4">
                <div className="grid h-24 w-40 shrink-0 place-items-center rounded-xl bg-[radial-gradient(circle_at_50%_25%,#174235,#07140f_70%)] text-emerald-300">
                  <Sparkles size={28} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-black">
                    {ar ? "إضافة شاشة النهاية" : "Add saved end screen"}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {ar
                      ? `${branding.outro_duration_seconds} ثانية · ${branding.archive_channel_name || "هوية Klipr"}`
                      : `${branding.outro_duration_seconds}s · ${branding.archive_channel_name || "Klipr identity"}`}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() =>
                    persistPreset({
                      enable_end_screen: !branding.enable_end_screen,
                    })
                  }
                  className={`rounded-lg px-3 py-2 text-xs font-black ${branding.enable_end_screen ? "bg-emerald-500 text-white" : "border border-slate-300 text-slate-600"}`}
                >
                  {branding.enable_end_screen
                    ? ar
                      ? "✓ تُضاف تلقائيًا"
                      : "✓ Auto outro on"
                    : ar
                      ? "إضافة النهاية"
                      : "Add end screen"}
                </button>
                <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-black text-emerald-700">
                  {ar ? "هوية تلقائية" : "Automatic branding"}
                </span>
                {branding.enable_end_screen && (
                  <button
                    type="button"
                    onClick={() => persistPreset({ enable_end_screen: false })}
                    className="ms-auto rounded-lg px-3 py-2 text-xs font-black text-rose-600 hover:bg-rose-50"
                  >
                    {ar ? "إزالة" : "Remove"}
                  </button>
                )}
              </div>
            </article>
          </div>
        )}
      </form>
      <section className="mt-8">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-black">
            {ar ? "التسجيلات النشطة" : "Active recordings"}
          </h2>
          <span className="text-xs text-slate-400">
            {ar ? "تحديث حي كل ثانية" : "Live updates every second"}
          </span>
        </div>
        {active.length ? (
          <div className="grid gap-4 md:grid-cols-2">
            {active.map((stream) => (
              <article
                key={stream.id}
                className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-black ${platformClass(stream.platform)}`}
                      >
                        {stream.platform.toUpperCase()}
                      </span>
                      <span className="flex items-center gap-1 text-xs font-black text-emerald-600">
                        <span className="size-2 animate-pulse rounded-full bg-emerald-500" />
                        {ar ? "يسجّل الآن" : "RECORDING"}
                      </span>
                    </div>
                    <p className="mt-3 font-black">{handle(stream)}</p>
                    <p className="mt-2 flex items-center gap-2 font-mono text-lg text-emerald-600">
                      <Clock3 size={16} />
                      {elapsed(stream.started_at, now)}
                    </p>
                  </div>
                  <StatusBadge status={stream.status} />
                </div>
                <button
                  onClick={() => stop(stream.id)}
                  disabled={stream.stop_requested}
                  className="mt-5 inline-flex items-center gap-2 rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-black text-white hover:bg-amber-600 disabled:opacity-50"
                >
                  <Square size={14} fill="currentColor" />
                  {stream.stop_requested
                    ? ar
                      ? "جارٍ الإيقاف…"
                      : "Stopping…"
                    : ar
                      ? "إيقاف ومعالجة الآن"
                      : "Stop & process now"}
                </button>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            text={
              ar
                ? "لا توجد تسجيلات مباشرة الآن."
                : "No live recordings right now."
            }
          />
        )}
      </section>
    </>
  );

  const archiveView = (
    <>
      <SectionTitle
        icon={Archive}
        eyebrow={ar ? "المحتوى المسجل" : "VOD ARCHIVE"}
        title={ar ? "مكتبة الأرشيف" : "Archive library"}
        description={
          ar
            ? "كل بثوثك المكتملة في مكتبة مرتبة، مع التحميل والوصول السريع لأدوات المعالجة."
            : "All completed streams in one organized library with downloads and quick tool shortcuts."
        }
      />
      <div className="mb-6 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row">
        <label className="relative flex-1">
          <Search
            className="absolute start-3 top-3.5 text-slate-400"
            size={17}
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl border border-slate-300 py-3 pe-3 ps-10 text-sm outline-none focus:border-emerald-500"
            placeholder={
              ar ? "ابحث باسم القناة أو الرابط…" : "Search channel or URL…"
            }
          />
        </label>
        <div className="flex gap-2">
          {(["all", "twitch", "kick"] as const).map((value) => (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={`rounded-xl px-4 py-2 text-xs font-black ${filter === value ? "bg-emerald-500 text-white" : "border border-slate-200 bg-white text-slate-600"}`}
            >
              {value === "all"
                ? ar
                  ? "الكل"
                  : "All"
                : value === "twitch"
                  ? "Twitch"
                  : "Kick"}
            </button>
          ))}
        </div>
      </div>
      <div className="mb-5 inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
        {(["vod", "short"] as const).map((value) => (
          <button
            key={value}
            onClick={() => setArchiveKind(value)}
            className={`rounded-lg px-4 py-2 text-sm font-black ${archiveKind === value ? "bg-emerald-500 text-white" : "text-slate-500"}`}
          >
            {value === "vod"
              ? ar
                ? "البثوث"
                : "VODs"
              : ar
                ? `الشورتات (${archiveShorts.length})`
                : `Shorts (${archiveShorts.length})`}
          </button>
        ))}
      </div>
      {archiveKind === "vod" &&
        (visibleArchive.length ? (
          <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-3">
            {visibleArchive.map((stream) => (
              <article
                key={stream.id}
                className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
              >
                <div className="aspect-video bg-gradient-to-br from-slate-100 to-emerald-50">
                  {stream.thumbnail_url ? (
                    <img
                      src={stream.thumbnail_url}
                      alt="VOD thumbnail"
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="grid h-full place-items-center text-sm font-bold text-slate-400">
                      <Film className="mb-2" />{" "}
                      {ar ? "صورة البث المصغّرة" : "Branded VOD thumbnail"}
                    </div>
                  )}
                </div>
                <div className="p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-black ${platformClass(stream.platform)}`}
                      >
                        {stream.platform.toUpperCase()}
                      </span>
                      {stream.remove_music && (
                        <span className="rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-black text-emerald-700">
                          DMCA Safe • {ar ? "بدون موسيقى" : "No music"}
                        </span>
                      )}
                    </div>
                    <StatusBadge status={stream.status} />
                  </div>
                  <h3 className="mt-3 truncate font-black">{handle(stream)}</h3>
                  <div className="mt-2 flex gap-4 text-xs text-slate-500">
                    <span>
                      {stream.ended_at
                        ? new Date(stream.ended_at).toLocaleDateString(
                            ar ? "ar-SA" : "en-US",
                          )
                        : "—"}
                    </span>
                    <span>{durationText(stream)}</span>
                    <span>
                      {stream.clip_count ?? 0} {ar ? "شورت" : "Shorts"}
                    </span>
                  </div>
                  {stream.status === "processing" ? (
                    <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-center text-sm font-black text-emerald-700">
                      <span className="inline-flex items-center gap-2">
                        <Sparkles size={16} className="animate-pulse" />
                        {ar
                          ? "جارٍ تحليل البث وتعديل الشورتات تلقائياً…"
                          : "Analyzing and editing Shorts automatically…"}
                      </span>
                    </div>
                  ) : (stream.clip_count ?? 0) > 0 ? (
                    <div className="mt-5 grid grid-cols-2 gap-2">
                      <button
                        onClick={() => setArchiveKind("short")}
                        className="col-span-2 inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-3 py-3 text-xs font-black text-white"
                      >
                        <Clapperboard size={15} />
                        {ar
                          ? `عرض الشورتات الجاهزة (${stream.clip_count})`
                          : `View ready Shorts (${stream.clip_count})`}
                      </button>
                      {stream.master_url && (
                        <a
                          href={stream.master_url}
                          download
                          className="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold"
                        >
                          <Download size={14} />
                          {ar ? "تنزيل البث الأصلي" : "Original VOD"}
                        </a>
                      )}
                    </div>
                  ) : (
                    <button
                      onClick={() => generateArchiveClips(stream)}
                      disabled={busy || !stream.master_url}
                      className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 font-black text-white disabled:opacity-50"
                    >
                      <WandSparkles size={17} />
                      {ar
                        ? "تعديل المقاطع تلقائياً"
                        : "Edit clips automatically"}
                    </button>
                  )}
                  <button
                    onClick={() => setDeleting(stream.id)}
                    className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg py-2 text-xs font-bold text-rose-600 hover:bg-rose-50"
                  >
                    <Trash2 size={14} />
                    {ar ? "حذف شامل ونهائي" : "Hard delete"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            text={
              ar
                ? "لا توجد تسجيلات تطابق البحث."
                : "No recordings match your search."
            }
          />
        ))}
      {archiveKind === "short" &&
        (visibleArchiveShorts.length ? (
          <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {visibleArchiveShorts.map((clip) => (
              <article
                key={clip.id}
                className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-3 shadow-sm"
              >
                {clip.thumbnail_url ? (
                  <img
                    src={clip.thumbnail_url}
                    alt="Short thumbnail"
                    className="aspect-[9/16] w-full rounded-xl object-cover"
                  />
                ) : (
                  <video
                    controls
                    src={clip.url || undefined}
                    className="aspect-[9/16] w-full rounded-xl bg-slate-950 object-cover"
                  />
                )}
                <div className="mt-3 flex items-center justify-between">
                  <span
                    className={`rounded-full px-2 py-1 text-[10px] font-black ${platformClass(clip.platform)}`}
                  >
                    {clip.platform.toUpperCase()} · SHORT
                  </span>
                  <span className="text-xs text-slate-500">
                    {Math.round(clip.end_seconds - clip.start_seconds)}s
                  </span>
                </div>
                <p className="mt-2 truncate text-sm font-black">
                  {handle({ source_url: clip.source_url } as Stream)}
                </p>
                <div className="mt-2 rounded-lg bg-slate-50 p-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="line-clamp-2 text-xs font-black">
                      {clip.hook_title ||
                        (ar ? "لقطة قوية من البث" : "Powerful stream moment")}
                    </p>
                    <span className="shrink-0 text-[10px] font-black text-orange-700">
                      🔥 {clip.viral_score ?? Math.round(clip.score * 100)}%
                    </span>
                  </div>
                  {clip.highlight_reason && (
                    <p className="mt-1 text-[10px] font-bold text-emerald-700">
                      {clip.highlight_reason}
                    </p>
                  )}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <a
                    href={clip.url || undefined}
                    download
                    className="inline-flex items-center justify-center gap-1 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-bold text-white"
                  >
                    <Download size={14} />
                    {ar ? "تحميل" : "Download"}
                  </a>
                  <label className="inline-flex cursor-pointer items-center justify-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold">
                    <Upload size={14} />
                    {ar ? "رفع غلاف" : "Upload cover"}
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      onChange={(e) =>
                        uploadShortThumbnail(clip.id, e.target.files?.[0])
                      }
                    />
                  </label>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            text={
              ar
                ? "لم تُولّد شورتات بعد. ستُحفظ هنا تلقائيًا عند اكتمال التوليد."
                : "No Shorts yet. Generated Shorts are saved here automatically."
            }
          />
        ))}
    </>
  );

  const shortsView = (
    <>
      <SectionTitle
        icon={ClapperboardIcon}
        eyebrow={ar ? "القصاص الذكي" : "AI SHORTS & CLIPPER"}
        title={ar ? "قصاص المقاطع وصانع الشورتات" : "AI Shorts & Clipper"}
        description={
          ar
            ? "اختر بثًا مكتملًا، اضبط شكل ومدة المقاطع ثم ولّد مجموعة شورتات جاهزة للنشر."
            : "Choose a completed VOD, configure the clips and generate publish-ready vertical Shorts."
        }
      />
      <div className="grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <label className="text-sm font-black">
            {ar ? "اختر بثًا من الأرشيف" : "Select archive VOD"}
            {picker}
          </label>
          <div className="mt-5">
            <p className="text-sm font-black">
              {ar ? "مدة الشورت" : "Short duration"}
            </p>
            <div className="mt-2 grid grid-cols-4 gap-2">
              {[15, 30, 45, 60].map((value) => (
                <button
                  key={value}
                  onClick={() => setClipDuration(value)}
                  className={`rounded-lg border py-2 text-xs font-black ${clipDuration === value ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200"}`}
                >
                  {value}s
                </button>
              ))}
            </div>
            <input
              type="number"
              min="10"
              max="180"
              value={clipDuration}
              onChange={(e) =>
                setClipDuration(
                  Math.min(180, Math.max(10, Number(e.target.value))),
                )
              }
              className={inputClass}
            />
          </div>
          <label className="mt-4 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
            <input
              type="checkbox"
              checked={removeMusic}
              onChange={(e) => setRemoveMusic(e.target.checked)}
              className="mt-1 size-5 accent-emerald-500"
            />
            <span>
              <span className="block text-sm font-black">
                {ar
                  ? "إزالة الأغاني وموسيقى الدونيشن تلقائياً (DMCA Safe)"
                  : "DMCA-safe vocal-only Shorts"}
              </span>
              <span className="mt-1 block text-xs leading-5 text-slate-600">
                {ar
                  ? "تُزال الموسيقى من الشورت مع إبقاء صوت الستريمر واضحًا."
                  : "Strip music from each Short while retaining the streamer voice."}
              </span>
            </span>
          </label>
          <label className="mt-5 block text-sm font-black">
            {ar ? "عدد المقاطع (1–10)" : "Clip count (1–10)"}
            <input
              type="number"
              min="1"
              max="10"
              value={clipCount}
              onChange={(e) =>
                setClipCount(Math.min(10, Math.max(1, Number(e.target.value))))
              }
              className={inputClass}
            />
          </label>
          <div
            className={`mt-5 rounded-2xl border p-4 ${embedCover ? "border-emerald-300 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}
          >
            <div className="flex items-center gap-3">
              <div className="h-28 w-16 shrink-0 overflow-hidden rounded-lg bg-slate-900">
                {branding.default_short_thumbnail_url ? (
                  <img
                    src={branding.default_short_thumbnail_url}
                    alt="Short intro thumbnail"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="grid h-full place-items-center text-slate-500">
                    <ImageIcon size={20} />
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <label className="flex items-center gap-3 font-black">
                  <input
                    type="checkbox"
                    checked={
                      embedCover &&
                      Boolean(branding.default_short_thumbnail_key)
                    }
                    onChange={(e) => setEmbedCover(e.target.checked)}
                    disabled={!branding.default_short_thumbnail_key}
                    className="size-5 accent-emerald-500"
                  />
                  {ar
                    ? "إضافة ثامبنيل في بداية الشورت"
                    : "Add thumbnail at the start"}
                </label>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  {branding.default_short_thumbnail_key
                    ? ar
                      ? "تظهر الصورة الطولية باحترافية خلال أول 0.8 ثانية."
                      : "The vertical cover appears during the first 0.8 seconds."
                    : ar
                      ? "احفظ أولًا صورة طولية 9:16 من صانع الثامبنيل."
                      : "Save a 9:16 cover in Thumbnail Studio first."}
                </p>
                <p className="mt-2 text-xs font-black text-emerald-700">
                  {ar
                    ? "يتم إنشاء غلاف كل مقطع تلقائياً."
                    : "Every clip cover is created automatically."}
                </p>
              </div>
            </div>
            <div className="mt-4 border-t border-emerald-200 pt-3">
              <p className="text-xs font-black text-emerald-800">
                {ar
                  ? "اختر ثامبنيل طولية محفوظة"
                  : "Choose a saved vertical thumbnail"}
              </p>
              {thumbnailChoices("short", true)}
            </div>
          </div>
          <label className="mt-5 block text-sm font-black">
            {ar ? "عنوان الغلاف" : "Cover headline"}
            <input
              value={clipHeadline}
              onChange={(e) => setClipHeadline(e.target.value)}
              className={inputClass}
            />
          </label>
          <button
            onClick={generate}
            disabled={!selected || busy}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3.5 font-black text-white hover:bg-emerald-600 disabled:opacity-40"
          >
            <Sparkles size={17} />
            {busy
              ? ar
                ? "جارٍ البدء…"
                : "Starting…"
              : ar
                ? "توليد شورتات جذابة"
                : "Generate viral Shorts"}
          </button>
        </aside>
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-black">
              {ar ? "معرض الشورتات" : "Shorts gallery"}
            </h2>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-500">
              {detailed?.clips?.length ?? 0}
            </span>
          </div>
          {detailed?.clips?.length ? (
            <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
              {detailed.clips.map((clip) => (
                <article
                  key={clip.id}
                  className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-3 shadow-sm"
                >
                  {clip.thumbnail_url ? (
                    <img
                      src={clip.thumbnail_url}
                      className="aspect-[9/16] w-full rounded-xl object-cover"
                      alt="Short thumbnail"
                    />
                  ) : (
                    <video
                      className="aspect-[9/16] w-full rounded-xl bg-black object-cover"
                      controls
                      src={clip.url ?? undefined}
                    />
                  )}
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-black text-emerald-700">
                        AR / EN {ar ? "ترجمة" : "CAPTIONS"}
                      </span>
                      {detailed?.remove_music && (
                        <span className="rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-black text-emerald-700">
                          DMCA Safe • {ar ? "بدون موسيقى" : "No music"}
                        </span>
                      )}
                    </div>
                    <span className="text-xs font-bold text-slate-500">
                      {Math.round(clip.end_seconds - clip.start_seconds)}s
                    </span>
                  </div>
                  <div className="mt-3 rounded-xl bg-slate-50 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="font-black leading-5">
                        {clip.hook_title ||
                          (ar ? "لقطة قوية من البث" : "Powerful stream moment")}
                      </h3>
                      <span className="shrink-0 rounded-full bg-orange-100 px-2 py-1 text-[10px] font-black text-orange-700">
                        🔥 {clip.viral_score ?? Math.round(clip.score * 100)}%
                        Viral
                      </span>
                    </div>
                    {clip.highlight_reason && (
                      <p className="mt-2 text-xs font-bold text-emerald-700">
                        {clip.highlight_reason}
                      </p>
                    )}
                  </div>
                  <div className="mt-3 grid gap-2">
                    {clip.url && (
                      <a
                        href={clip.url}
                        download
                        className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-black text-white"
                      >
                        <Download size={14} />
                        {ar ? "تحميل الشورت" : "Download Short"}
                      </a>
                    )}
                    {clip.thumbnail_url && (
                      <a
                        href={clip.thumbnail_url}
                        download
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-xs font-black"
                      >
                        <Download size={14} />
                        {ar ? "تحميل غلاف 9:16" : "Download 9:16 cover"}
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              text={
                ar
                  ? "اختر بثًا وابدأ التوليد؛ ستظهر الشورتات هنا."
                  : "Select a VOD and generate; your Shorts will appear here."
              }
            />
          )}
        </section>
      </div>
    </>
  );

  const thumbSource =
    thumbFormat === "short"
      ? detailed?.clips?.[0]?.thumbnail_url || detailed?.thumbnail_url
      : detailed?.thumbnail_url || detailed?.clips?.[0]?.thumbnail_url;
  const thumbnailView = (
    <>
      <SectionTitle
        icon={ImageIcon}
        eyebrow={ar ? "استوديو الأغلفة" : "THUMBNAIL STUDIO"}
        title={ar ? "صانع الثامبنايل" : "Thumbnail Studio"}
        description={
          ar
            ? "صمّم غلافًا عاديًا 16:9 للبث أو غلافًا طوليًا 9:16 للشورتات."
            : "Create a 16:9 VOD cover or a vertical 9:16 cover for Shorts."
        }
      />
      <section className="mb-6 rounded-3xl border border-violet-200 bg-[linear-gradient(135deg,#f5f3ff,#ffffff)] p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-black">
              {ar ? "صانع الثامبنيل بالذكاء الاصطناعي" : "AI Thumbnail Studio"}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {ar
                ? "حلّل البث المختار واحصل على 3 لقطات مع عناوين عربية قابلة للتنزيل."
                : "Analyze a saved VOD and get three downloadable, captioned moments."}
            </p>
          </div>
          <span className="rounded-full bg-violet-100 px-3 py-1 text-xs font-black text-violet-700">
            OpenAI Vision + DeepSeek
          </span>
        </div>
        <div className="mt-5 grid gap-3 lg:grid-cols-4">
          <select
            value={smartVodId}
            onChange={(event) => setSmartVodId(event.target.value)}
            className={inputClass}
          >
            <option value="">
              {ar ? "اختر بثاً محفوظاً" : "Choose a saved VOD"}
            </option>
            {vods
              .filter((vod) => vod.status === "ready")
              .map((vod) => (
                <option key={vod.id} value={vod.id}>
                  {vod.title || "Untitled VOD"}
                </option>
              ))}
          </select>
          <select
            value={smartPlatform}
            onChange={(event) =>
              setSmartPlatform(event.target.value as SmartThumbnail["platform"])
            }
            className={inputClass}
          >
            <option value="youtube">YouTube · 16:9 · Original quality</option>
            <option value="tiktok">TikTok · 9:16 · 1080×1920</option>
            <option value="shorts">YouTube Shorts · 9:16</option>
            <option value="reels">Reels · 9:16</option>
            <option value="x">X / Twitter · 16:9 · Original quality</option>
            <option value="kick">Kick · 16:9 · Original quality</option>
          </select>
          <select
            value={smartStyle}
            onChange={(event) =>
              setSmartStyle(event.target.value as SmartThumbnail["frame_style"])
            }
            className={inputClass}
          >
            <option value="bold">
              {ar ? "إطار حماسي عالي التباين" : "Bold high-contrast frame"}
            </option>
            <option value="clean">
              {ar ? "إطار نظيف" : "Clean platform frame"}
            </option>
            <option value="none">{ar ? "بدون إطار" : "No frame"}</option>
          </select>
          <button
            disabled={smartBusy || !smartVodId}
            onClick={async () => {
              setSmartBusy(true);
              setMessage("");
              try {
                setSmartItems(
                  await api.createSmartThumbnails(
                    smartVodId,
                    smartPlatform,
                    smartStyle,
                  ),
                );
                setMessage(
                  ar
                    ? "بدأ تحليل أقوى اللحظات وترتيب أوضح اللقطات — ستظهر 3 اقتراحات احترافية عند اكتماله."
                    : "Analysing the strongest moments and clearest frames — three polished suggestions will appear here.",
                );
              } catch (error) {
                setMessage(
                  error instanceof Error
                    ? error.message
                    : "Could not start thumbnail analysis",
                );
              } finally {
                setSmartBusy(false);
              }
            }}
            className="mt-2 inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 font-black text-white hover:bg-violet-700 disabled:opacity-50"
          >
            <WandSparkles size={18} />
            {smartBusy
              ? ar
                ? "جارٍ البدء…"
                : "Starting…"
              : ar
                ? "اختيار أقوى اللقطات وصناعة الثامبنيل"
                : "Choose best moments & generate"}
          </button>
        </div>
        {smartItems.length > 0 && (
          <div className="mt-6 grid gap-5 md:grid-cols-3">
            {smartItems.map((item, index) => (
              <article
                key={item.id}
                className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
              >
                <div className="aspect-video shrink-0 bg-slate-100">
                  {item.image_url ? (
                    <img
                      src={`${process.env.NEXT_PUBLIC_API_URL || "/api"}${item.image_url}`}
                      alt={item.headline || "AI thumbnail"}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="grid h-full place-items-center text-sm font-bold text-slate-400">
                      {item.status === "failed"
                        ? ar
                          ? "فشل التوليد"
                          : "Generation failed"
                        : `${Math.round(item.progress)}%`}
                    </div>
                  )}
                </div>
                <div className="flex flex-1 flex-col p-4">
                  <span className="text-[11px] font-black tracking-wide text-violet-600">
                    {ar ? `أفضل لحظة ${index + 1}` : `TOP MOMENT ${index + 1}`}
                  </span>
                  <p className="mt-1 min-h-12 font-black">
                    {item.headline ||
                      (ar
                        ? "يجري اختيار أوضح لقطة من أقوى لحظة…"
                        : "Choosing the clearest frame from a top moment…")}
                  </p>
                  {item.context && (
                    <p className="mt-2 line-clamp-2 text-xs text-slate-500">
                      {item.context}
                    </p>
                  )}
                  {item.error && (
                    <p className="mt-2 text-xs text-rose-600">{item.error}</p>
                  )}
                  {item.image_url && (
                    <div className="mt-4 grid grid-cols-2 gap-2">
                      <button
                        onClick={async () => {
                          try {
                            const saved = await api.approveSmartThumbnail(
                              item.id,
                            );
                            setSavedThumbnails((current) => [
                              saved,
                              ...current
                                .filter((entry) => entry.id !== saved.id)
                                .map((entry) => ({
                                  ...entry,
                                  selected:
                                    entry.kind === "vod"
                                      ? false
                                      : entry.selected,
                                })),
                            ]);
                            setMessage(
                              ar
                                ? "تم اعتماد الثامبنيل وحفظه في المكتبة."
                                : "Thumbnail approved and saved to the library.",
                            );
                          } catch (error) {
                            setMessage(
                              error instanceof Error
                                ? error.message
                                : "Could not approve thumbnail",
                            );
                          }
                        }}
                        className="rounded-xl bg-emerald-600 px-3 py-2 text-xs font-black text-white"
                      >
                        {ar ? "اعتماد وحفظ" : "Approve & save"}
                      </button>
                      <a
                        href={`${process.env.NEXT_PUBLIC_API_URL || "/api"}${item.image_url}`}
                        download
                        className="inline-flex items-center justify-center gap-2 rounded-xl border border-violet-200 px-3 py-2 text-xs font-black text-violet-700"
                      >
                        <Download size={15} />
                        {ar ? "تنزيل" : "Download"}
                      </a>
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      <div className="grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <p className="text-sm font-black">
              {ar ? "مقاس الصورة" : "Image size"}
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                onClick={() => setThumbFormat("vod")}
                className={`rounded-xl border p-3 text-start ${thumbFormat === "vod" ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200"}`}
              >
                <b className="block text-sm">16:9</b>
                <span className="mt-1 block text-xs text-slate-400">
                  {ar
                    ? "مقطع عادي · الدقة الأصلية"
                    : "Regular VOD · original quality"}
                </span>
              </button>
              <button
                onClick={() => setThumbFormat("short")}
                className={`rounded-xl border p-3 text-start ${thumbFormat === "short" ? "border-emerald-500 bg-emerald-50 text-emerald-700" : "border-slate-200"}`}
              >
                <b className="block text-sm">9:16</b>
                <span className="mt-1 block text-xs text-slate-400">
                  {ar ? "شورت طولي · 1080×1920" : "Vertical Short · 1080×1920"}
                </span>
              </button>
            </div>
          </div>
          <div className="mt-5">
            <p className="text-sm font-black">
              {ar ? "هوية المنصة" : "Platform frame"}
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button
                onClick={() => setThumbPlatform("twitch")}
                className={`rounded-xl border p-3 font-black ${thumbPlatform === "twitch" ? "border-violet-500 bg-violet-50 text-violet-700" : "border-slate-200"}`}
              >
                Twitch · #9146FF
              </button>
              <button
                onClick={() => setThumbPlatform("kick")}
                className={`rounded-xl border p-3 font-black ${thumbPlatform === "kick" ? "border-lime-500 bg-lime-50 text-lime-700" : "border-slate-200"}`}
              >
                Kick · #53FC18
              </button>
            </div>
          </div>
          <button
            onClick={saveThumbnail}
            disabled={busy}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3.5 font-black text-white disabled:opacity-50"
          >
            <Check size={17} />
            {busy
              ? ar
                ? "جارٍ الحفظ…"
                : "Saving…"
              : ar
                ? thumbFormat === "short"
                  ? "حفظ غلاف الشورت الطولي"
                  : "حفظ غلاف البث العادي"
                : thumbFormat === "short"
                  ? "Save vertical Short cover"
                  : "Save regular VOD cover"}
          </button>
          {savedThumbnails.find(
            (item) => item.kind === thumbFormat && item.selected,
          ) && (
            <a
              href={`${process.env.NEXT_PUBLIC_API_URL || "/api"}/branding/thumbnails/${savedThumbnails.find((item) => item.kind === thumbFormat && item.selected)?.id}/download`}
              className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 font-black text-emerald-800 hover:bg-emerald-100"
            >
              <Download size={17} />
              {ar
                ? "تنزيل الثامبنيل بجودة كاملة"
                : "Download full-quality thumbnail"}
            </a>
          )}
          {(thumbFormat === "short"
            ? branding.default_short_thumbnail_key
            : branding.default_thumbnail_key) && (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
              <div className="flex items-center gap-2 text-xs font-black text-emerald-700">
                <Check size={15} />
                {ar
                  ? thumbFormat === "short"
                    ? "غلاف الشورت الطولي محفوظ لبداية الشورتات."
                    : "غلاف البث العادي محفوظ للأرشيف."
                  : thumbFormat === "short"
                    ? "Vertical Short cover is saved for Short intros."
                    : "Regular VOD cover is saved for the archive."}
              </div>
              <button
                onClick={() => deleteThumbnail(thumbFormat)}
                className="mt-2 text-xs font-black text-rose-600"
              >
                {ar ? "إزالة الثامبنيل المحفوظة" : "Remove saved thumbnail"}
              </button>
            </div>
          )}
        </aside>
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-black">
              {ar ? "المعاينة الحية" : "Live preview"}
            </h2>
            <span className="text-xs text-slate-400">
              {thumbFormat === "short"
                ? "1080 × 1920"
                : "1920 × 1080 · Original quality"}
            </span>
          </div>
          <div
            className={`relative mx-auto overflow-hidden rounded-2xl border-[5px] bg-slate-950 shadow-xl ${thumbFormat === "short" ? "aspect-[9/16] max-h-[680px]" : "aspect-video w-full"} ${thumbPlatform === "twitch" ? "border-[#9146FF] shadow-violet-500/20" : "border-[#53FC18] shadow-lime-500/20"}`}
          >
            {thumbSource ? (
              <img
                src={thumbSource}
                alt="Thumbnail preview"
                className="h-full w-full object-cover opacity-80"
              />
            ) : (
              <div className="h-full bg-[radial-gradient(circle_at_50%_40%,#334155,#020617_70%)]" />
            )}
            <span
              className={`absolute start-4 top-4 rounded-lg px-3 py-1.5 text-xs font-black text-white ${thumbPlatform === "twitch" ? "bg-[#9146FF]" : "bg-[#20b94b]"}`}
            >
              {thumbPlatform.toUpperCase()} · KLIPR
            </span>
            {thumbFormat === "vod" && (
              <span
                className={`absolute start-4 top-14 rounded-md border px-2.5 py-1 text-[10px] font-black tracking-wide text-white shadow-sm ${thumbPlatform === "twitch" ? "border-[#9146FF] bg-slate-950/90" : "border-[#53FC18] bg-slate-950/90"}`}
              >
                ORIGINAL
              </span>
            )}
          </div>
        </section>
      </div>
      <SavedThumbnailLibrary />
    </>
  );

  function SavedThumbnailLibrary() {
    return (
      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-black">
              {ar ? "مكتبة الثامبنيلات المحفوظة" : "Saved thumbnail library"}
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              {ar
                ? "اختر أي تصميم ليصبح الغلاف الافتراضي، أو احذف التصاميم التي لم تعد تحتاجها."
                : "Select a design as the default, or remove designs you no longer need."}
            </p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-black text-slate-500">
            {savedThumbnails.filter((item) => item.kind === thumbFormat).length}
          </span>
        </div>
        {savedThumbnails.some((item) => item.kind === thumbFormat) ? (
          <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {savedThumbnails
              .filter((item) => item.kind === thumbFormat)
              .map((item) => (
                <article
                  key={item.id}
                  className={`overflow-hidden rounded-xl border-2 p-2 ${item.selected ? "border-emerald-500 bg-emerald-50" : "border-slate-200"}`}
                >
                  <button
                    type="button"
                    onClick={() => chooseSavedThumbnail(item)}
                    className="relative block w-full overflow-hidden rounded-lg bg-slate-100"
                  >
                    <img
                      src={item.url}
                      alt="Saved thumbnail"
                      className={`${item.kind === "short" ? "aspect-[9/16]" : "aspect-video"} w-full object-cover`}
                    />
                    {item.selected && (
                      <span className="absolute end-2 top-2 rounded-full bg-emerald-500 px-2 py-1 text-[10px] font-black text-white">
                        {ar ? "مختارة" : "Selected"}
                      </span>
                    )}
                  </button>
                  <div className="mt-2 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => chooseSavedThumbnail(item)}
                      className="text-xs font-black text-emerald-700"
                    >
                      {ar ? "اختيار" : "Select"}
                    </button>
                    <button
                      type="button"
                      onClick={() => removeSavedThumbnail(item)}
                      className="text-xs font-black text-rose-600"
                    >
                      {ar ? "حذف" : "Delete"}
                    </button>
                  </div>
                </article>
              ))}
          </div>
        ) : (
          <Empty
            text={
              ar
                ? "صمّم واحفظ أول ثامبنيل لتظهر هنا."
                : "Create and save your first thumbnail to see it here."
            }
          />
        )}
      </section>
    );
  }
  const logo = logoPreview || branding.archive_logo_url;
  const brandingView = (
    <>
      <SectionTitle
        icon={Sparkles}
        eyebrow={ar ? "هوية الأرشيف" : "END SCREEN & BRANDING"}
        title={
          ar ? "شاشة النهاية وهوية الأرشيف" : "End screen & archive branding"
        }
        description={
          ar
            ? "احفظ هوية موحّدة تظهر تلقائيًا في نهاية التسجيلات وعلى قناة الأرشيف."
            : "Save a consistent identity that appears automatically on your archive and end screen."
        }
      />
      <div className="grid gap-6 2xl:grid-cols-[420px_minmax(0,1fr)]">
        <aside className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <label className="flex items-center justify-between rounded-xl bg-slate-50 p-4 font-black">
            <span>{ar ? "تفعيل شاشة النهاية" : "Enable end screen outro"}</span>
            <input
              type="checkbox"
              checked={branding.enable_end_screen}
              onChange={(e) =>
                setBranding({
                  ...branding,
                  enable_end_screen: e.target.checked,
                })
              }
              className="size-5 accent-emerald-500"
            />
          </label>
          <label className="block text-sm font-black">
            {ar
              ? `مدة النهاية: ${branding.outro_duration_seconds} ثانية`
              : `Outro duration: ${branding.outro_duration_seconds}s`}
            <input
              type="range"
              min="10"
              max="20"
              value={branding.outro_duration_seconds}
              onChange={(e) =>
                setBranding({
                  ...branding,
                  outro_duration_seconds: Number(e.target.value),
                })
              }
              className="mt-3 w-full accent-emerald-500"
            />
          </label>
          <div>
            <p className="text-sm font-black">
              {ar ? "شعار قناة الأرشيف" : "Archive channel logo"}
            </p>
            <div className="mt-3 flex items-center gap-4">
              <div className="grid size-20 shrink-0 place-items-center overflow-hidden rounded-full border-4 border-emerald-100 bg-slate-100">
                {logo ? (
                  <img
                    src={logo}
                    alt="Archive logo"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <Upload className="text-slate-400" />
                )}
              </div>
              <div className="flex-1">
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-xs font-black">
                  <Upload size={14} />
                  {ar ? "رفع شعار" : "Upload logo"}
                  <input
                    type="file"
                    className="hidden"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={(e) => uploadLogo(e.target.files?.[0])}
                  />
                </label>
                {branding.archive_logo_key && (
                  <button
                    onClick={deleteLogo}
                    className="ms-2 rounded-lg px-3 py-2 text-xs font-black text-rose-600"
                  >
                    {ar ? "إزالة" : "Remove"}
                  </button>
                )}
                <p className="mt-2 text-[11px] text-slate-400">
                  PNG / JPG / WebP · 5MB
                </p>
              </div>
            </div>
          </div>
          <label className="block text-sm font-black">
            {ar ? "اسم قناة الأرشيف" : "Archive channel name"}
            <input
              value={branding.archive_channel_name || ""}
              onChange={(e) =>
                setBranding({
                  ...branding,
                  archive_channel_name: e.target.value,
                })
              }
              className={inputClass}
            />
          </label>
          <label className="block text-sm font-black">
            {ar ? "النص التذييلي" : "Archive footer tagline"}
            <input
              value={branding.archive_tagline || ""}
              onChange={(e) =>
                setBranding({ ...branding, archive_tagline: e.target.value })
              }
              className={inputClass}
            />
          </label>
          <label className="block text-sm font-black">
            {ar ? "الفيديو المقترح الأيسر" : "Left recommended video"}
            <select
              value={branding.default_left_vod_id || ""}
              onChange={(e) =>
                setBranding({
                  ...branding,
                  default_left_vod_id: e.target.value || null,
                })
              }
              className={inputClass}
            >
              <option value="">
                {ar ? "تلقائي: أحدث بثين" : "Auto: Latest 2 archive VODs"}
              </option>
              {completed.map((s) => (
                <option key={s.id} value={s.id}>
                  {handle(s)}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-black">
            {ar ? "الفيديو المقترح الأيمن" : "Right recommended video"}
            <select
              value={branding.default_right_vod_id || ""}
              onChange={(e) =>
                setBranding({
                  ...branding,
                  default_right_vod_id: e.target.value || null,
                })
              }
              className={inputClass}
            >
              <option value="">
                {ar ? "تلقائي: أحدث بثين" : "Auto: Latest 2 archive VODs"}
              </option>
              {completed.map((s) => (
                <option key={s.id} value={s.id}>
                  {handle(s)}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={saveBranding}
            disabled={savingBrand}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3.5 font-black text-white disabled:opacity-50"
          >
            <Check size={17} />
            {savingBrand
              ? ar
                ? "جارٍ الحفظ…"
                : "Saving…"
              : ar
                ? "حفظ إعدادات الهوية"
                : "Save branding settings"}
          </button>
        </aside>
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-black">
              {ar ? "المخطط الحي لشاشة النهاية" : "Live end-screen blueprint"}
            </h2>
            <span className="text-xs text-slate-400">1920 × 1080</span>
          </div>
          <div className="relative aspect-video overflow-hidden rounded-2xl bg-[radial-gradient(circle_at_50%_25%,#174235,#07140f_65%)] p-5 text-white shadow-xl">
            <div className="absolute inset-x-0 top-5 text-center">
              <div className="mx-auto grid size-[14%] min-h-14 min-w-14 place-items-center overflow-hidden rounded-full border-4 border-emerald-400 bg-white/10">
                {logo ? (
                  <img
                    src={logo}
                    alt="Logo preview"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <Sparkles />
                )}
              </div>
              <p className="mt-2 text-sm font-black sm:text-lg">
                {branding.archive_channel_name ||
                  (ar ? "اسم قناة الأرشيف" : "Archive channel")}
              </p>
              <span className="mt-1 inline-block rounded-full bg-red-600 px-4 py-1 text-[9px] font-black sm:text-xs">
                {ar ? "اشترك الآن" : "SUBSCRIBE"}
              </span>
            </div>
            <div className="absolute inset-x-[6%] bottom-[18%] grid grid-cols-2 gap-[8%]">
              <div className="aspect-video rounded-lg border-2 border-dashed border-white/45 bg-white/10 p-2 text-[9px] sm:text-xs">
                {ar ? "الفيديو المقترح الأيسر" : "LEFT RECOMMENDED VIDEO"}
              </div>
              <div className="aspect-video rounded-lg border-2 border-dashed border-white/45 bg-white/10 p-2 text-[9px] sm:text-xs">
                {ar ? "الفيديو المقترح الأيمن" : "RIGHT RECOMMENDED VIDEO"}
              </div>
            </div>
            <div className="absolute inset-x-0 bottom-4 text-center text-[9px] text-emerald-100 sm:text-xs">
              {branding.archive_tagline ||
                (ar ? "لحظات البث، جاهزة للنشر." : "Live moments, clipped.")}
            </div>
          </div>
        </section>
      </div>
    </>
  );

  const startStudioRender = async () => {
    if (!studioVodId) {
      setMessage(
        ar
          ? "اختر بثاً جاهزاً من مكتبة البثوث أولاً."
          : "Select a ready VOD from the vault first.",
      );
      return;
    }
    setStudioBusy(true);
    try {
      const render = await api.createStudioRender(studioVodId, {
        exportQuality: studioExportQuality,
        intro: studioIntro,
        outro: studioOutro,
      });
      setStudioRender(render);
      setMessage(
        ar
          ? "بدأ تجهيز المقطع — يمكنك متابعة التقدم هنا."
          : "Render started — follow its progress here.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : ar
            ? "تعذّر بدء التجهيز."
            : "Could not start the render.",
      );
    } finally {
      setStudioBusy(false);
    }
  };
  const startEditorialRange = async (vod: Vod) => {
    const range = editorRanges[vod.id] || {
      start: "0",
      end: String(Math.min(vod.duration_seconds || 60, 300)),
    };
    const start = Number(range.start),
      end = Number(range.end);
    if (
      !Number.isFinite(start) ||
      !Number.isFinite(end) ||
      start < 0 ||
      end <= start
    ) {
      setMessage(
        ar
          ? "أدخل بداية ونهاية صحيحتين بالثواني."
          : "Enter a valid start and end time in seconds.",
      );
      return;
    }
    setStudioBusy(true);
    try {
      const render = await api.createStudioRender(vod.id, {
        exportQuality: "original",
        startSeconds: start,
        endSeconds: end,
      });
      setStudioRender(render);
      setStudioVodId(vod.id);
      setMessage(
        ar
          ? "بدأ حفظ الجزء المحدد مع المقدمة والخاتمة تلقائياً."
          : "Saving the selected range with the default intro and outro.",
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not start editorial export",
      );
    } finally {
      setStudioBusy(false);
    }
  };
  const updateEditorialTime = (
    vodId: string,
    key: "start" | "end",
    part: "hours" | "minutes" | "seconds",
    raw: string,
  ) => {
    const current = Number(editorRanges[vodId]?.[key] || 0);
    const parts = {
      hours: Math.floor(current / 3600),
      minutes: Math.floor((current % 3600) / 60),
      seconds: Math.floor(current % 60),
    };
    parts[part] = Math.max(
      0,
      Math.min(part === "hours" ? 99 : 59, Number(raw) || 0),
    );
    const total = parts.hours * 3600 + parts.minutes * 60 + parts.seconds;
    setEditorRanges({
      ...editorRanges,
      [vodId]: {
        start: editorRanges[vodId]?.start || "0",
        end: editorRanges[vodId]?.end || "0",
        [key]: String(total),
      },
    });
  };
  const editorialTimeFields = (
    vod: Vod,
    key: "start" | "end",
    label: string,
  ) => {
    const total = Number(editorRanges[vod.id]?.[key] || 0);
    const values = [
      Math.floor(total / 3600),
      Math.floor((total % 3600) / 60),
      Math.floor(total % 60),
    ];
    const parts = ["hours", "minutes", "seconds"] as const;
    const labels = ar
      ? ["ساعة", "دقيقة", "ثانية"]
      : ["Hour", "Minute", "Second"];
    const toEnd = key === "end" && Boolean(editorToEnd[vod.id]);
    return (
      <div
        className={`rounded-xl border p-3 ${toEnd ? "border-emerald-300 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}
      >
        <p className="mb-2 text-xs font-black text-slate-700">{label}</p>
        <div className="grid grid-cols-3 gap-1">
          {parts.map((part, index) => (
            <label
              key={part}
              className="text-center text-[10px] font-bold text-slate-500"
            >
              {labels[index]}
              <input
                type="number"
                min="0"
                max={part === "hours" ? 99 : 59}
                disabled={toEnd}
                value={values[index]}
                onChange={(event) =>
                  updateEditorialTime(vod.id, key, part, event.target.value)
                }
                className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-1 py-2 text-center text-sm font-black disabled:bg-emerald-100 disabled:text-emerald-800"
              />
            </label>
          ))}
        </div>
        {key === "end" && (
          <button
            type="button"
            onClick={() => {
              const active = !editorToEnd[vod.id];
              setEditorToEnd({ ...editorToEnd, [vod.id]: active });
              if (active)
                setEditorRanges({
                  ...editorRanges,
                  [vod.id]: {
                    start: editorRanges[vod.id]?.start || "0",
                    end: String(vod.duration_seconds || 0),
                  },
                });
            }}
            className={`mt-3 w-full rounded-lg px-3 py-2 text-xs font-black transition ${toEnd ? "bg-emerald-600 text-white" : "border border-emerald-300 bg-white text-emerald-700"}`}
          >
            {toEnd
              ? ar
                ? "✓ محدد إلى نهاية البث"
                : "✓ Set to end of broadcast"
              : ar
                ? "إلى نهاية البث"
                : "To end of broadcast"}
          </button>
        )}
      </div>
    );
  };
  const studioView = (
    <>
      <SectionTitle
        icon={Clapperboard}
        eyebrow={ar ? "استوديو الإنتاج" : "PRODUCTION STUDIO"}
        title={ar ? "الاستديو المتكامل" : "Production Studio"}
        description={
          ar
            ? "اختر بثاً محفوظاً، أضف المقدمة والنهاية، ثم جهّز ملف MP4 موحداً وجاهزاً للتنزيل."
            : "Choose a vault VOD, add an intro and outro, then render a normalized downloadable MP4."
        }
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
        <section className="space-y-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <label className="block text-sm font-black">
            {ar
              ? "1. البث أو المقطع من مكتبة البثوث المحفوظة"
              : "1. VOD from the saved broadcast vault"}
            <select
              value={studioVodId}
              onChange={(event) => setStudioVodId(event.target.value)}
              className={inputClass}
            >
              <option value="">
                {ar ? "اختر بثاً جاهزاً" : "Choose a ready VOD"}
              </option>
              {vods
                .filter((vod) => vod.status === "ready")
                .map((vod) => (
                  <option key={vod.id} value={vod.id}>
                    {vod.title || (ar ? "بث غير مسمى" : "Untitled broadcast")} ·{" "}
                    {vodDuration(vod.duration_seconds)}
                  </option>
                ))}
            </select>
          </label>
          {studioVodId &&
            (() => {
              const vod = vods.find((item) => item.id === studioVodId);
              return vod?.download_url ? (
                <video
                  controls
                  className="aspect-video w-full rounded-xl bg-black"
                  src={`${process.env.NEXT_PUBLIC_API_URL || "/api"}${vod.download_url}`}
                />
              ) : null;
            })()}
          <div>
            <p className="mb-3 text-sm font-black">
              {ar ? "2. المقدمة والنهاية" : "2. Intro & Outro"}
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <AssetPicker
                label={ar ? "فيديو المقدمة" : "Intro video"}
                accept="video/mp4,video/quicktime"
                file={studioIntro}
                onChange={setStudioIntro}
                hint="MP4 / MOV · optional"
              />
              <AssetPicker
                label={ar ? "فيديو النهاية" : "Outro video"}
                accept="video/mp4,video/quicktime"
                file={studioOutro}
                onChange={setStudioOutro}
                hint="MP4 / MOV · optional"
              />
            </div>
          </div>
          <div>
            <p className="mb-3 text-sm font-black">
              {ar ? "جودة التصدير" : "Export quality"}
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setStudioExportQuality("original")}
                className={`rounded-xl border p-4 text-start ${studioExportQuality === "original" ? "border-emerald-500 bg-emerald-50 text-emerald-800" : "border-slate-200"}`}
              >
                <b className="block text-sm">
                  {ar ? "الجودة الأصلية" : "Original quality"}
                </b>
                <span className="mt-1 block text-xs opacity-70">
                  1080p · {ar ? "حتى 60fps" : "up to 60fps"}
                </span>
              </button>
              <button
                type="button"
                onClick={() => setStudioExportQuality("4k")}
                className={`rounded-xl border p-4 text-start ${studioExportQuality === "4k" ? "border-emerald-500 bg-emerald-50 text-emerald-800" : "border-slate-200"}`}
              >
                <b className="block text-sm">4K Ultra HD</b>
                <span className="mt-1 block text-xs opacity-70">
                  3840×2160 · 60fps · CRF 16
                </span>
              </button>
            </div>
          </div>
          <button
            onClick={startStudioRender}
            disabled={studioBusy || !studioVodId}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3.5 font-black text-white disabled:opacity-50"
          >
            <Sparkles size={18} />
            {studioBusy
              ? ar
                ? "جارٍ الحفظ…"
                : "Saving…"
              : ar
                ? "3. حفظ وتجهيز"
                : "3. Save & Render"}
          </button>
          <p className="text-xs leading-5 text-slate-500">
            {ar
              ? "توحيد تلقائي: 1920×1080، معدل الإطارات المصدر، وصوت AAC بتردد 48kHz، ثم دمج المقدمة + البث + النهاية."
              : "Automatic normalization: 1920×1080, source FPS and AAC 48kHz; then Intro + VOD + Outro."}
          </p>
        </section>
        <aside className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="font-black">
            {ar ? "حالة التجهيز" : "Render status"}
          </h2>
          {studioRender ? (
            <div className="mt-5">
              <div className="flex justify-between text-sm font-bold">
                <span>
                  {studioRender.status === "ready"
                    ? ar
                      ? "مكتمل"
                      : "Ready"
                    : studioRender.status === "failed"
                      ? ar
                        ? "فشل"
                        : "Failed"
                      : ar
                        ? "قيد المعالجة"
                        : "Processing"}
                </span>
                <span>{Math.round(studioRender.progress)}%</span>
              </div>
              <div className="mt-2 h-3 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full ${studioRender.status === "failed" ? "bg-rose-500" : "bg-emerald-500"}`}
                  style={{ width: `${studioRender.progress}%` }}
                />
              </div>
              {studioRender.error && (
                <p className="mt-4 rounded-xl bg-rose-50 p-3 text-xs text-rose-700">
                  {studioRender.error}
                </p>
              )}
              {studioRender.download_url && (
                <a
                  href={`${process.env.NEXT_PUBLIC_API_URL || "/api"}${studioRender.download_url}`}
                  download
                  className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 font-black text-white"
                >
                  <Download size={17} />
                  {ar ? "تنزيل المقطع النهائي MP4" : "Download final MP4"}
                </a>
              )}
            </div>
          ) : (
            <Empty
              text={
                ar
                  ? "اختر بثاً وارفع المقدمة أو النهاية، ثم اضغط حفظ وتجهيز."
                  : "Choose a VOD, add an intro or outro, then save and render."
              }
            />
          )}
        </aside>
      </div>
    </>
  );

  const reviewSuggestion = async (item: CreatorSuggestion) => {
    try {
      const next = await api.updateCreatorSuggestion(
        item.id,
        item.status === "new" ? "reviewed" : "new",
      );
      setSuggestions((current) =>
        current.map((value) => (value.id === item.id ? next : value)),
      );
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : ar
            ? "تعذّر تحديث الاقتراح"
            : "Could not update suggestion",
      );
    }
  };
  const removeSuggestion = async (id: string) => {
    try {
      await api.deleteCreatorSuggestion(id);
      setSuggestions((current) => current.filter((item) => item.id !== id));
      setMessage(ar ? "تم حذف الاقتراح." : "Suggestion deleted.");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : ar
            ? "تعذّر حذف الاقتراح"
            : "Could not delete suggestion",
      );
    }
  };
  const newSuggestionCount = suggestions.filter(
    (item) => item.status === "new",
  ).length;
  const suggestionsView = (
    <>
      <SectionTitle
        eyebrow={ar ? "صوت المجتمع" : "Community inbox"}
        title={ar ? "اقتراحات المشاهير" : "Creator suggestions"}
        description={
          ar
            ? "كل الأسماء التي يقترحها زوار Klipr تصل إلى هنا. راجع القناة والمنصة ثم حدّث حالة الاقتراح."
            : "Every creator submitted by Klipr visitors arrives here. Review the channel and platform, then update its status."
        }
        icon={MessageSquareText}
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-xs font-black uppercase tracking-[.16em] text-slate-400">
            {ar ? "إجمالي الاقتراحات" : "Total suggestions"}
          </p>
          <p className="mt-2 text-3xl font-black text-slate-900">
            {suggestions.length}
          </p>
        </div>
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <p className="text-xs font-black uppercase tracking-[.16em] text-emerald-600">
            {ar ? "بانتظار المراجعة" : "Awaiting review"}
          </p>
          <p className="mt-2 text-3xl font-black text-emerald-800">
            {newSuggestionCount}
          </p>
        </div>
      </div>
      {suggestionsBusy ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-sm font-bold text-slate-400">
          {ar ? "جارٍ تحميل الاقتراحات..." : "Loading suggestions..."}
        </div>
      ) : suggestions.length === 0 ? (
        <Empty
          text={
            ar
              ? "لا توجد اقتراحات حتى الآن. ستظهر اقتراحات زوار الموقع هنا مباشرة."
              : "No suggestions yet. Visitor submissions will appear here automatically."
          }
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {suggestions.map((item) => (
            <article
              key={item.id}
              className={`rounded-2xl border bg-white p-5 shadow-sm transition ${item.status === "new" ? "border-emerald-200 ring-1 ring-emerald-100" : "border-slate-200"}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-lg font-black text-slate-900">
                      {item.creator_name}
                    </h3>
                    <span
                      className={`rounded-full px-2.5 py-1 text-[10px] font-black uppercase ${item.platform === "twitch" ? "bg-violet-100 text-violet-700" : "bg-emerald-100 text-emerald-700"}`}
                    >
                      {item.platform}
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-slate-400">
                    {new Intl.DateTimeFormat(ar ? "ar-SA" : "en-US", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(item.created_at))}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-black ${item.status === "new" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"}`}
                >
                  {item.status === "new"
                    ? ar
                      ? "جديد"
                      : "New"
                    : ar
                      ? "تمت المراجعة"
                      : "Reviewed"}
                </span>
              </div>
              {item.channel_url ? (
                <a
                  href={item.channel_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-4 flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs font-bold text-slate-600 transition hover:border-emerald-300 hover:text-emerald-700"
                >
                  <span className="truncate" dir="ltr">
                    {item.channel_url}
                  </span>
                  <ExternalLink size={15} className="shrink-0" />
                </a>
              ) : (
                <p className="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-xs text-slate-400">
                  {ar ? "لم يُرفق رابط للقناة." : "No channel URL was provided."}
                </p>
              )}
              <div className="mt-4 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => removeSuggestion(item.id)}
                  className="rounded-lg px-3 py-2 text-xs font-black text-rose-600 transition hover:bg-rose-50"
                >
                  {ar ? "حذف" : "Delete"}
                </button>
                <button
                  type="button"
                  onClick={() => reviewSuggestion(item)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-black transition ${item.status === "new" ? "bg-emerald-600 text-white hover:bg-emerald-700" : "border border-slate-200 text-slate-600 hover:bg-slate-50"}`}
                >
                  <CheckCircle2 size={15} />
                  {item.status === "new"
                    ? ar
                      ? "تحديد كمُراجع"
                      : "Mark reviewed"
                    : ar
                      ? "إعادة إلى جديد"
                      : "Mark as new"}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );

  const vodsView = (
    <>
      <SectionTitle
        eyebrow={ar ? "استيراد محلي" : "Local lossless import"}
        title={ar ? "مكتبة البثوث المحفوظة" : "VOD Vault"}
        description={
          ar
            ? "ألصق رابط بث محفوظ من Twitch أو Kick. يُحمّل بأعلى جودة متاحة ثم يُعاد تغليفه دون إعادة ترميز ليبقى جاهزاً للتقطيع."
            : "Paste a saved Twitch or Kick broadcast URL. It downloads at the best available quality and is remuxed without re-encoding for fast editing."
        }
        icon={FolderDown}
      />
      <form
        onSubmit={importVod}
        className="mb-7 rounded-2xl border border-emerald-200 bg-gradient-to-br from-white to-emerald-50 p-5 shadow-sm"
      >
        <div className="flex flex-col gap-3 lg:flex-row">
          <div className="relative min-w-0 flex-1">
            <input
              value={vodUrl}
              onChange={(event) => setVodUrl(event.target.value)}
              dir="ltr"
              placeholder="https://www.twitch.tv/videos/...  أو  https://kick.com/user/videos/..."
              className={`${inputClass} mt-0 ps-11`}
            />
            <span
              className={`absolute start-3 top-3.5 text-xs font-black ${/twitch/i.test(vodUrl) ? "text-violet-600" : /kick/i.test(vodUrl) ? "text-lime-600" : "text-slate-400"}`}
            >
              {/twitch/i.test(vodUrl)
                ? "TW"
                : /kick/i.test(vodUrl)
                  ? "K"
                  : "URL"}
            </span>
          </div>
          <div className="flex items-center justify-center rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm font-black text-emerald-800">
            {ar ? "أعلى جودة أصلية" : "Best original quality"}
          </div>
          <button
            disabled={vodBusy || !vodUrl.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 font-black text-white transition hover:bg-emerald-700 disabled:opacity-50"
          >
            <FolderDown size={18} />
            {ar ? "جلب وحفظ البث" : "Fetch & save VOD"}
          </button>
        </div>
        <p className="mt-3 text-xs leading-5 text-emerald-800">
          {ar
            ? "يسحب أعلى مصدر متاح بالتنزيل المتوازي ويحفظ دقته ومعدل إطاراته الأصليين دون تكبير وهمي. إن كان المصدر 4K/60 فسيبقى 4K/60، وإن كان 1080p/60 فسيحفظ 1080p/60 الحقيقي بسرعة."
            : "Fetches the best available source in parallel and preserves its native resolution and frame rate without artificial upscaling."}
        </p>
      </form>
      {vods.some((vod) => !["ready", "failed"].includes(vod.status)) && (
        <div className="mb-7 space-y-3">
          {vods
            .filter((vod) => !["ready", "failed"].includes(vod.status))
            .map((vod) => (
              <article
                key={vod.id}
                className="overflow-hidden rounded-2xl border border-emerald-200 bg-white p-4 shadow-sm"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-black">
                      {vod.title ||
                        (ar
                          ? "جارٍ استخراج بيانات البث…"
                          : "Fetching VOD metadata…")}
                    </p>
                    <p className="mt-1 text-xs font-bold text-emerald-700">
                      {vod.status === "fetching_metadata"
                        ? ar
                          ? "استخراج البيانات"
                          : "Fetching metadata"
                        : vod.status === "remuxing"
                          ? ar
                            ? "تجهيز MP4 سريع التقديم"
                            : "Preparing seekable MP4"
                          : ar
                            ? "تحميل البث"
                            : "Downloading VOD"}
                    </p>
                  </div>
                  <span className="text-sm font-black text-emerald-700">
                    {Math.round(vod.progress)}%
                  </span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all"
                    style={{ width: `${Math.max(3, vod.progress)}%` }}
                  />
                </div>
                <div className="mt-3 flex items-center justify-between gap-4 text-xs text-slate-500">
                  <div className="flex gap-4">
                    <span>{vod.download_speed || "—"}</span>
                    <span>
                      {vod.eta_seconds ? `${vod.eta_seconds}s ETA` : ""}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => cancelVod(vod.id)}
                    disabled={vodBusy}
                    className="rounded-lg border border-rose-200 px-3 py-2 font-black text-rose-600 hover:bg-rose-50 disabled:opacity-50"
                  >
                    {ar ? "إلغاء المعالجة فوراً" : "Cancel now"}
                  </button>
                </div>
              </article>
            ))}
        </div>
      )}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-black">
          {ar ? "البثوث الجاهزة" : "Ready broadcasts"}
        </h2>
        <span className="text-xs font-bold text-slate-400">
          {vods.filter((vod) => vod.status === "ready").length}
        </span>
      </div>
      {vods.length === 0 ? (
        <Empty
          text={
            ar
              ? "لم تُحفظ أي بثوث بعد. ألصق رابط VOD للبدء."
              : "No saved broadcasts yet. Paste a VOD URL to begin."
          }
        />
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {vods.map((vod) => (
            <article
              key={vod.id}
              className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
            >
              <div className="relative aspect-video bg-slate-100">
                {vod.thumbnail_url ? (
                  <img
                    src={
                      vod.thumbnail_url.startsWith("/")
                        ? `${process.env.NEXT_PUBLIC_API_URL || "/api"}${vod.thumbnail_url}`
                        : vod.thumbnail_url
                    }
                    alt=""
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="grid h-full place-items-center text-slate-300">
                    <Film size={36} />
                  </div>
                )}
                <span
                  className={`absolute end-3 top-3 rounded-full px-2.5 py-1 text-[10px] font-black uppercase ${platformClass(vod.platform)}`}
                >
                  {vod.platform}
                </span>
                <span className="absolute start-3 top-3 rounded-full bg-slate-950/85 px-2.5 py-1 text-[10px] font-black text-white backdrop-blur">
                  {vodQualityText(vod)}
                </span>
              </div>
              <div className="p-4">
                <h3 className="truncate font-black">
                  {vod.title || (ar ? "بث غير مسمّى" : "Untitled broadcast")}
                </h3>
                <p className="mt-1 truncate text-xs text-slate-500">
                  {vod.streamer_name || "—"}
                </p>
                <div className="mt-3 flex flex-wrap gap-3 text-xs font-bold text-slate-500">
                  <span>{vodDuration(vod.duration_seconds)}</span>
                  <span>{fileSize(vod.file_size)}</span>
                  <span>{bitrateText(vod.bitrate)}</span>
                </div>
                {vod.status === "failed" ? (
                  <p className="mt-3 text-xs font-bold text-rose-600">
                    {vod.error || (ar ? "فشل الاستيراد" : "Import failed")}
                  </p>
                ) : vod.status === "ready" ? (
                  <div className="mt-4 grid grid-cols-2 gap-2">
                    {editorialTimeFields(
                      vod,
                      "start",
                      ar ? "البداية · من" : "Start from",
                    )}
                    {editorialTimeFields(
                      vod,
                      "end",
                      ar ? "النهاية · إلى" : "End at",
                    )}
                    <p className="col-span-2 text-center text-[11px] font-bold text-emerald-700">
                      {ar
                        ? `مدة الجزء: ${vodDuration(Math.max(0, Number(editorRanges[vod.id]?.end || 0) - Number(editorRanges[vod.id]?.start || 0)))}`
                        : `Selected duration: ${vodDuration(Math.max(0, Number(editorRanges[vod.id]?.end || 0) - Number(editorRanges[vod.id]?.start || 0)))}`}
                    </p>
                    <button
                      onClick={() => startEditorialRange(vod)}
                      disabled={studioBusy}
                      className="col-span-2 rounded-lg bg-slate-900 px-3 py-2 text-xs font-black text-white disabled:opacity-50"
                    >
                      {ar
                        ? "اعتماد وحفظ مع المقدمة والخاتمة"
                        : "Save with intro & outro"}
                    </button>
                    <button
                      onClick={() => generateVodClips(vod)}
                      disabled={vodBusy}
                      className="col-span-2 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-black text-white disabled:opacity-50"
                    >
                      {ar ? "إرسال لصناعة الشورتات" : "Send to Shorts"}
                    </button>
                    <button
                      onClick={() => {
                        setMetadataVodId(vod.id);
                        setAiMetadata(null);
                        changeSection("metadata");
                      }}
                      className="rounded-lg border border-emerald-200 px-3 py-2 text-xs font-black text-emerald-700"
                    >
                      {ar ? "عنوان ووصف" : "Title & description"}
                    </button>
                    <a
                      href={`${process.env.NEXT_PUBLIC_API_URL || "/api"}${vod.download_url || ""}`}
                      download
                      className="rounded-lg border border-slate-200 px-3 py-2 text-center text-xs font-black text-slate-700"
                    >
                      {ar ? "تنزيل" : "Download"}
                    </a>
                    <button
                      onClick={() => removeVod(vod.id)}
                      className="col-span-2 rounded-lg px-3 py-2 text-xs font-black text-rose-600 hover:bg-rose-50"
                    >
                      {ar ? "حذف" : "Delete"}
                    </button>
                  </div>
                ) : (
                  <p className="mt-3 text-xs font-bold text-slate-400">
                    {ar ? "قيد المعالجة…" : "Processing…"}
                  </p>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );

  const aiMetadataView = (
    <>
      <SectionTitle
        icon={MessageSquareText}
        eyebrow="AI METADATA"
        title={
          ar
            ? "صناعة العنوان والوصف بالذكاء الاصطناعي"
            : "AI Titles & Description"
        }
        description={
          ar
            ? "يكتب من أحداث البث والكلام الفعلي فقط: عناوين عالية الجذب ووصف SEO وفصول وهاشتاقات قابلة للنسخ."
            : "Creates high-CTR titles, SEO description, chapters and hashtags from actual VOD events and speech."
        }
      />
      <section className="rounded-3xl border border-slate-800 bg-slate-950 p-6 text-white shadow-xl">
        <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
          <select
            value={metadataVodId}
            onChange={(event) => {
              setMetadataVodId(event.target.value);
              setAiMetadata(null);
            }}
            className="rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm font-bold outline-none focus:border-emerald-500"
          >
            <option value="">
              {ar ? "اختر بثاً جاهزاً من المكتبة" : "Choose a ready VOD"}
            </option>
            {vods
              .filter((vod) => vod.status === "ready")
              .map((vod) => (
                <option key={vod.id} value={vod.id}>
                  {vod.title || (ar ? "بث غير مسمى" : "Untitled VOD")}
                </option>
              ))}
          </select>
          <button
            onClick={() => generateMetadata(Boolean(aiMetadata))}
            disabled={!metadataVodId || metadataBusy}
            className="rounded-xl bg-emerald-500 px-5 py-3 text-sm font-black text-slate-950 disabled:opacity-50"
          >
            {metadataBusy
              ? ar
                ? "جارٍ التحليل…"
                : "Analyzing…"
              : aiMetadata
                ? ar
                  ? "توليد صياغة مختلفة"
                  : "Generate another version"
                : ar
                  ? "تحليل البث وتوليد المحتوى"
                  : "Analyze & generate"}
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-400">
          {ar
            ? "يلزم تحليل أحداث البث أولاً؛ لن ينشئ محتوى اعتماداً على عنوان البث وحده."
            : "Event analysis is required first; it never writes from the VOD title alone."}
        </p>
      </section>
      {aiMetadata && (
        <div className="mt-6 grid gap-5 xl:grid-cols-2">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="font-black">
                {ar ? "5 عناوين عالية الجذب" : "5 high-CTR titles"}
              </h2>
              <button
                onClick={() =>
                  copyText(
                    aiMetadata.titles.map((item) => item.text).join("\n"),
                  )
                }
                className="text-xs font-black text-emerald-700"
              >
                {ar ? "نسخ الكل" : "Copy all"}
              </button>
            </div>
            <div className="mt-4 space-y-3">
              {aiMetadata.titles.map((item, index) => (
                <button
                  key={`${item.text}-${index}`}
                  onClick={() => copyText(item.text)}
                  className="flex w-full items-start justify-between gap-3 rounded-xl bg-slate-50 p-3 text-start"
                >
                  <span className="text-sm font-bold">{item.text}</span>
                  <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-1 text-[11px] font-black text-emerald-700">
                    {item.score}%
                  </span>
                </button>
              ))}
            </div>
          </section>
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="font-black">
                {ar ? "وصف SEO احترافي" : "SEO description"}
              </h2>
              <button
                onClick={() => copyText(aiMetadata.description)}
                className="text-xs font-black text-emerald-700"
              >
                {ar ? "نسخ" : "Copy"}
              </button>
            </div>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-600">
              {aiMetadata.description}
            </p>
          </section>
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="font-black">{ar ? "فصول البث" : "Chapters"}</h2>
              <button
                onClick={() =>
                  copyText(
                    aiMetadata.chapters
                      .map((item) => `${item.time} ${item.title}`)
                      .join("\n"),
                  )
                }
                className="text-xs font-black text-emerald-700"
              >
                {ar ? "نسخ" : "Copy"}
              </button>
            </div>
            <div className="mt-4 space-y-2">
              {aiMetadata.chapters.map((item, index) => (
                <div
                  key={`${item.time}-${index}`}
                  className="flex gap-3 rounded-lg bg-slate-50 px-3 py-2 text-sm"
                >
                  <span className="font-black text-emerald-700">
                    {item.time}
                  </span>
                  <span>{item.title}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="font-black">
                {ar ? "الكلمات والهاشتاقات" : "Tags & hashtags"}
              </h2>
              <button
                onClick={() =>
                  copyText(
                    [...aiMetadata.tags, ...aiMetadata.hashtags].join(" "),
                  )
                }
                className="text-xs font-black text-emerald-700"
              >
                {ar ? "نسخ الكل" : "Copy all"}
              </button>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {[...aiMetadata.tags, ...aiMetadata.hashtags].map(
                (item, index) => (
                  <span
                    key={`${item}-${index}`}
                    className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-800"
                  >
                    {item}
                  </span>
                ),
              )}
            </div>
          </section>
        </div>
      )}
    </>
  );

  const sessionView = (
    <>
      <SectionTitle
        eyebrow={ar ? "خزنة مشفّرة" : "Encrypted vault"}
        title={ar ? "الجلسة" : "Session Vault"}
        description={
          ar
            ? "اربط جلسات Kick وTwitch محلياً لتسجيل المصدر بأفضل جودة. لا تظهر الكوكيز أو الرموز بعد حفظها."
            : "Store Kick and Twitch sessions locally for best-source capture. Cookies and tokens are never shown after saving."
        }
        icon={KeyRound}
      />
      <div className="grid gap-5 xl:grid-cols-2">
        {(["kick", "twitch"] as const).map((platform) => {
          const item = credentials[platform];
          const expired = item.status === "expired";
          const active = item.status === "active";
          const date = (value: string | null) =>
            value
              ? new Intl.DateTimeFormat(ar ? "ar-SA" : "en-US", {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(value))
              : "—";
          const save = async () => {
            if (!sessionInput[platform].trim()) return;
            setSessionBusy(platform);
            try {
              const next = await api.saveCredential(
                platform,
                sessionInput[platform],
              );
              setCredentials((current) => ({ ...current, [platform]: next }));
              setSessionInput((current) => ({ ...current, [platform]: "" }));
              setMessage(
                ar ? "تم حفظ وتشفير الجلسة." : "Session encrypted and saved.",
              );
            } catch (error) {
              setMessage(
                error instanceof Error
                  ? error.message
                  : "Unable to save session",
              );
            } finally {
              setSessionBusy(null);
            }
          };
          const removeSession = async () => {
            setSessionBusy(platform);
            try {
              await api.deleteCredential(platform);
              setCredentials((current) => ({
                ...current,
                [platform]: {
                  ...emptyCredentials[platform],
                  updated_at: new Date().toISOString(),
                },
              }));
              setSessionInput((current) => ({ ...current, [platform]: "" }));
            } catch (error) {
              setMessage(
                error instanceof Error
                  ? error.message
                  : "Unable to remove session",
              );
            } finally {
              setSessionBusy(null);
            }
          };
          return (
            <section
              key={platform}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[.16em] text-emerald-600">
                    {platform === "kick"
                      ? "Kick 1080p60 Session"
                      : "Twitch 1080p60 & Ad-Free Session"}
                  </p>
                  <h2 className="mt-1 text-xl font-black">
                    {active
                      ? ar
                        ? "متصل • جودة 1080p60 مفعّلة"
                        : "Connected • 1080p60 enabled"
                      : expired
                        ? ar
                          ? "منتهية الصلاحية — يلزم التجديد"
                          : "Expired — renew required"
                        : ar
                          ? "غير مربوط"
                          : "Not connected"}
                  </h2>
                </div>
                <span
                  className={`mt-1 size-3 rounded-full ${active ? "bg-emerald-500" : expired ? "bg-amber-500" : "bg-slate-300"}`}
                  aria-label={item.status}
                />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-xs">
                <div>
                  <p className="text-slate-400">
                    {ar ? "آخر تحديث" : "Last updated"}
                  </p>
                  <b>{date(item.updated_at)}</b>
                </div>
                <div>
                  <p className="text-slate-400">
                    {ar ? "انتهاء الكوكيز" : "Cookie expiry"}
                  </p>
                  <b>{date(item.expires_at)}</b>
                </div>
              </div>
              <div className="mt-5 rounded-xl border border-emerald-100 bg-emerald-50/50 p-4 text-xs leading-6 text-slate-600">
                <b className="text-emerald-800">
                  {ar ? "دليل سريع (15 ثانية)" : "Quick guide (15 seconds)"}
                </b>
                <ol className="mt-1 list-decimal ps-5">
                  <li>
                    {ar
                      ? "افتح جلسة ثانوية مسجّل الدخول في المتصفح."
                      : "Open a secondary signed-in browser session."}
                  </li>
                  <li>
                    {ar
                      ? "انسخ cookies.txt بصيغة Netscape أو session_token."
                      : "Copy Netscape cookies.txt or a session token."}
                  </li>
                  <li>
                    {ar
                      ? "الصقه هنا ثم احفظه مشفراً."
                      : "Paste it here and save encrypted."}
                  </li>
                </ol>
              </div>
              {platform === "twitch" && (
                <p className="mt-4 rounded-xl bg-violet-50 p-3 text-xs font-bold leading-5 text-violet-800">
                  اربط جلسة حساب Twitch Turbo لضمان تسجيل خام 1080p60 بدون أي
                  إعلانات أو انقطاع أثناء اللقطات القوية.
                </p>
              )}
              <label className="mt-5 block text-xs font-black text-slate-700">
                {ar ? "كوكيز أو رمز الجلسة" : "Cookies or session token"}
                <textarea
                  value={sessionInput[platform]}
                  onChange={(event) =>
                    setSessionInput((current) => ({
                      ...current,
                      [platform]: event.target.value,
                    }))
                  }
                  maxLength={65536}
                  rows={5}
                  className={inputClass}
                  placeholder={
                    platform === "kick"
                      ? "cookies.txt أو kick_session"
                      : "cookies.txt أو Bearer token"
                  }
                />
              </label>
              <label className="mt-3 inline-flex cursor-pointer items-center gap-2 text-xs font-bold text-emerald-700">
                <Upload size={15} />
                {ar ? "تحميل ملف .txt" : "Load .txt file"}
                <input
                  className="hidden"
                  type="file"
                  accept=".txt,text/plain"
                  onChange={async (event) => {
                    const file = event.target.files?.[0];
                    if (file) {
                      const content = await file.text();
                      setSessionInput((current) => ({
                        ...current,
                        [platform]: content.slice(0, 65536),
                      }));
                    }
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  disabled={
                    sessionBusy === platform || !sessionInput[platform].trim()
                  }
                  onClick={save}
                  className="rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-black text-white disabled:opacity-50"
                >
                  {ar ? "حفظ وتشفير الجلسة" : "Save encrypted session"}
                </button>
                <button
                  disabled={sessionBusy === platform || !item.has_session}
                  onClick={removeSession}
                  className="rounded-xl border border-rose-300 px-4 py-2.5 text-xs font-black text-rose-600 disabled:opacity-50"
                >
                  {ar ? "حذف الجلسة" : "Delete session"}
                </button>
              </div>
            </section>
          );
        })}
      </div>
    </>
  );
  const hasExpiredSession = Object.values(credentials).some(
    (item) => item.status === "expired",
  );
  const presetsView = (
    <>
      <SectionTitle
        icon={CheckCircle2}
        eyebrow={ar ? "هوية القناة" : "CHANNEL IDENTITY"}
        title={ar ? "الشعار والبنر" : "Logo & YouTube banner"}
        description={
          ar
            ? "احفظ هوية موحّدة: شعار أسود بإطار أخضر وبنر يوتيوب باسم القناة."
            : "Save a unified black-and-emerald logo card and YouTube channel banner."
        }
      />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="space-y-6 rounded-3xl border border-emerald-100 bg-white p-6 shadow-sm">
          <div>
            <div className="mb-3 flex items-center justify-between">
              <b>{ar ? "صورة القناة · YouTube" : "YouTube channel avatar"}</b>
              <a
                href={drb7hLogo}
                download
                className="text-xs font-black text-emerald-700"
              >
                {ar ? "تنزيل الشعار" : "Download logo"}
              </a>
            </div>
            <div className="relative mx-auto grid aspect-video max-w-3xl place-items-center overflow-hidden rounded-2xl border-[10px] border-emerald-500 bg-black shadow-[0_0_40px_rgba(16,185,129,.25)]">
              <div className="grid size-72 place-items-center rounded-full border-[7px] border-emerald-500 bg-black p-3 shadow-[0_0_28px_rgba(16,185,129,.42)] sm:size-80">
                <div className="flex w-full flex-col items-center">
                  <div className="grid size-52 place-items-center overflow-hidden bg-transparent sm:size-56">
                    <img
                      src={drb7hLogo}
                      alt="Drb7h channel logo"
                      className="h-full w-full object-contain"
                    />
                  </div>
                  <p className="mt-2 max-w-full truncate text-center text-2xl font-black tracking-[-.03em] text-white drop-shadow-lg sm:text-3xl">
                    {branding.overlay_creator_name || "Drb7h"}
                  </p>
                </div>
              </div>
            </div>
          </div>
          <div>
            <div className="mb-3 flex items-center justify-between">
              <b>{ar ? "بنر يوتيوب" : "YouTube banner"}</b>
              <div className="flex items-center gap-3">
                <span className="text-xs text-slate-500">2560 × 1440</span>
                <a
                  href={drb7hBanner}
                  download
                  className="text-xs font-black text-emerald-700"
                >
                  {ar ? "تنزيل البنر" : "Download banner"}
                </a>
              </div>
            </div>
            <div className="relative mx-auto aspect-[16/9] max-w-3xl overflow-hidden rounded-2xl border border-emerald-500 bg-slate-950 shadow-xl">
              <img
                src={drb7hBanner}
                alt="Drb7h YouTube channel banner"
                className="h-full w-full object-contain"
              />
            </div>
          </div>
        </section>
        <aside className="space-y-5 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <label className="block text-sm font-black">
            {ar ? "اسم المشهور / الستريمر" : "Creator / streamer name"}
            <input
              value={branding.overlay_creator_name || ""}
              onChange={(event) =>
                setBranding({
                  ...branding,
                  overlay_creator_name: event.target.value,
                })
              }
              maxLength={120}
              placeholder="@drb7h"
              className={inputClass}
            />
          </label>
          <div>
            <p className="text-sm font-black">{ar ? "الشعار" : "Logo"}</p>
            <div className="mt-3 flex gap-2">
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-slate-300 px-3 py-2.5 text-xs font-black">
                <Upload size={15} />
                {ar ? "رفع / تغيير" : "Upload / change"}
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={(event) =>
                    uploadOverlayLogo(event.target.files?.[0])
                  }
                />
              </label>
              {branding.overlay_logo_key && (
                <button
                  onClick={deleteOverlayLogo}
                  className="rounded-xl px-3 text-xs font-black text-rose-600"
                >
                  {ar ? "إزالة" : "Remove"}
                </button>
              )}
            </div>
            <p className="mt-2 text-[11px] text-slate-400">
              PNG / JPG / WebP · 5MB
            </p>
          </div>
          <label className="block text-sm font-black">
            {ar ? "موقع الختم" : "Overlay position"}
            <select
              value={branding.overlay_position}
              onChange={(event) =>
                setBranding({
                  ...branding,
                  overlay_position: event.target
                    .value as Branding["overlay_position"],
                })
              }
              className={inputClass}
            >
              <option value="top-right">
                {ar ? "أعلى اليمين" : "Top right"}
              </option>
              <option value="top-left">
                {ar ? "أعلى اليسار" : "Top left"}
              </option>
              <option value="bottom-center">
                {ar ? "أسفل المنتصف" : "Bottom center"}
              </option>
            </select>
          </label>
          <button
            onClick={saveBranding}
            disabled={savingBrand}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3.5 font-black text-white disabled:opacity-50"
          >
            <Check size={17} />
            {savingBrand
              ? ar
                ? "جارٍ الحفظ…"
                : "Saving…"
              : ar
                ? "حفظ المحفوظات التعديلية"
                : "Save editing preset"}
          </button>
          <p className="rounded-xl bg-emerald-50 p-3 text-xs leading-5 text-emerald-800">
            {ar
              ? "سيُلتقط هذا الإعداد مع كل بث جديد ويُدمج تلقائياً في التصدير النهائي."
              : "This preset is snapshotted with each new stream and burned into its final export."}
          </p>
        </aside>
      </div>
    </>
  );
  const settingsView = (
    <>
      <SectionTitle
        icon={KeyRound}
        eyebrow={ar ? "الهوية والإعدادات" : "SETTINGS & BRANDING"}
        title={ar ? "الإعدادات والهوية" : "Settings & Branding"}
        description={
          ar
            ? "اعتمد هوية القناة وقوالب البداية والنهاية، ثم أدر جلسات المنصات بأمان."
            : "Set channel identity, intro/outro templates, and platform sessions in one place."
        }
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        <button
          onClick={() =>
            setBranding({
              ...branding,
              auto_merge_branding: !branding.auto_merge_branding,
            })
          }
          className={`rounded-2xl border p-4 text-start ${branding.auto_merge_branding ? "border-emerald-300 bg-emerald-50" : "border-slate-200 bg-white"}`}
        >
          <b className="block text-sm text-emerald-900">
            {ar ? "مقدمة 5 ث + خاتمة 8 ث" : "5s intro + 8s outro"}
          </b>
          <span className="mt-1 block text-xs text-emerald-700">
            {branding.auto_merge_branding
              ? ar
                ? "مفعّل تلقائياً عند السحب"
                : "Enabled for every import"
              : ar
                ? "غير مفعّل"
                : "Disabled"}
          </span>
        </button>
        <button
          onClick={() =>
            setBranding({
              ...branding,
              ai_music_removal: !branding.ai_music_removal,
            })
          }
          className={`rounded-2xl border p-4 text-start ${branding.ai_music_removal ? "border-emerald-300 bg-emerald-50" : "border-slate-200 bg-white"}`}
        >
          <b className="block text-sm text-emerald-900">
            {ar ? "إزالة الموسيقى بالذكاء" : "AI music removal"}
          </b>
          <span className="mt-1 block text-xs text-emerald-700">
            {branding.ai_music_removal
              ? ar
                ? "Demucs + فلترة صوت"
                : "Demucs + vocal cleanup"
              : ar
                ? "اضغط للتفعيل"
                : "Click to enable"}
          </span>
        </button>
        <button
          onClick={() => changeSection("sessions")}
          className="rounded-2xl border border-slate-200 bg-white p-4 text-start shadow-sm transition hover:border-emerald-300"
        >
          <b className="block text-sm">
            {ar ? "جلسات المنصات" : "Platform sessions"}
          </b>
          <span className="mt-1 block text-xs text-slate-500">
            Kick و Twitch
          </span>
        </button>
      </div>
      {presetsView}
    </>
  );
  const content =
    section === "live"
      ? liveView
      : section === "vods"
        ? vodsView
        : section === "shorts"
          ? shortsView
          : section === "metadata"
            ? aiMetadataView
            : section === "settings"
              ? settingsView
              : section === "presets"
                ? presetsView
                : section === "thumbnails"
                  ? thumbnailView
                  : section === "intro-outro"
                    ? brandingView
                    : section === "studio"
                      ? studioView
                      : section === "sessions"
                        ? sessionView
                        : suggestionsView;
  return (
    <Shell
      activeCount={active.length}
      activeSection={section}
      onSectionChange={changeSection}
    >
      <div className="mx-auto max-w-[1500px]">
        {hasExpiredSession && section !== "sessions" && (
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-bold text-amber-900">
            <span>
              {ar
                ? "انتهت صلاحية جلسة البث — جدّدها للاستمرار بجودة 1080p60."
                : "A stream session expired — renew it to continue 1080p60 capture."}
            </span>
            <button
              onClick={() => changeSection("sessions")}
              className="rounded-lg bg-amber-500 px-3 py-2 text-xs font-black text-white"
            >
              {ar ? "تجديد الجلسة الآن" : "Renew session now"}
            </button>
          </div>
        )}
        {message && (
          <div
            className={`mb-5 flex items-center justify-between rounded-xl border px-4 py-3 text-sm font-bold ${/نجاح|تم |started|saved|uploaded/i.test(message) ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-rose-200 bg-rose-50 text-rose-700"}`}
          >
            <span>{message}</span>
            <button onClick={() => setMessage("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {content}
      </div>
      {deleting && (
        <div className="fixed inset-0 z-[60] grid place-items-center bg-slate-950/45 p-5">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h2 className="text-xl font-black">
              {ar
                ? "حذف هذا الأرشيف نهائيًا؟"
                : "Permanently delete this archive?"}
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              {ar
                ? "سيتم حذف البث الكامل والشورتات والصور المصغّرة والترجمات وجميع الملفات المرتبطة. لا يمكن التراجع."
                : "The master VOD, Shorts, thumbnails, captions and related files will be permanently removed."}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setDeleting(null)}
                className="rounded-lg px-4 py-2 font-bold text-slate-600"
              >
                {ar ? "إلغاء" : "Cancel"}
              </button>
              <button
                onClick={remove}
                className="rounded-lg bg-rose-600 px-4 py-2 font-bold text-white"
              >
                {ar ? "حذف نهائي" : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}

export default function Dashboard() {
  return <DashboardWorkspace />;
}

function ClapperboardIcon(props: React.ComponentProps<typeof Film>) {
  return <Film {...props} />;
}

function AssetPicker({
  label,
  accept,
  file,
  onChange,
  hint,
}: {
  label: string;
  accept: string;
  file: File | null;
  onChange: (file: File | null) => void;
  hint: string;
}) {
  return (
    <label className="block rounded-xl border border-dashed border-slate-300 p-4 text-sm font-black transition hover:border-emerald-400 hover:bg-emerald-50">
      <span className="flex items-center gap-2">
        <Upload size={17} className="text-emerald-600" />
        {label}
      </span>
      <span className="mt-3 block truncate rounded-lg bg-slate-50 px-3 py-2 text-xs font-medium text-slate-500">
        {file?.name || hint}
      </span>
      <input
        type="file"
        accept={accept}
        className="hidden"
        onChange={(event) => onChange(event.target.files?.[0] || null)}
      />
    </label>
  );
}
