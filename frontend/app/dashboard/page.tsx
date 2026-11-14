"use client";
import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  Check,
  CheckCircle2,
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
  WandSparkles,
  X,
} from "lucide-react";
import {
  api,
  ArchiveShort,
  Branding,
  CreatorSuggestion,
  SavedThumbnail,
  Stream,
  StreamPreview,
} from "@/lib/api";
import { DashboardSection, Shell } from "@/components/shell";
import { StatusBadge } from "@/components/status";
import { useLanguage } from "@/components/language";

const emptyBranding: Branding = {
  enable_end_screen: true,
  remove_music: false,
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
};
const validSections: DashboardSection[] = [
  "live",
  "archive",
  "shorts",
  "thumbnail",
  "branding",
  "suggestions",
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

export default function Dashboard() {
  const { language } = useLanguage();
  const ar = language === "ar";
  const [section, setSection] = useState<DashboardSection>("live"),
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
  useEffect(() => {
    const query = new URLSearchParams(window.location.search).get(
      "section",
    ) as DashboardSection | null;
    if (query && validSections.includes(query)) setSection(query);
    load();
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
  }, [section]);
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
    window.history.replaceState(null, "", `/dashboard?section=${next}`);
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
      canvas.width = thumbFormat === "short" ? 1080 : 1280;
      canvas.height = thumbFormat === "short" ? 1920 : 720;
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
                <button
                  type="button"
                  onClick={() => changeSection("thumbnail")}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-black"
                >
                  {ar ? "فتح صانع الثامبنيل" : "Open Thumbnail Studio"}
                </button>
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
                <button
                  type="button"
                  onClick={() => changeSection("branding")}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-black"
                >
                  {ar ? "فتح صانع الهوية" : "Open Branding Studio"}
                </button>
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
                  <div className="mt-5 grid grid-cols-2 gap-2">
                    {stream.master_url && (
                      <a
                        href={stream.master_url}
                        download
                        className="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold"
                      >
                        <Download size={14} />
                        {ar ? "تحميل البث" : "Master VOD"}
                      </a>
                    )}
                    {stream.thumbnail_url && (
                      <a
                        href={stream.thumbnail_url}
                        download
                        className="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold"
                      >
                        <Download size={14} />
                        {ar ? "الثامبنايل" : "Thumbnail"}
                      </a>
                    )}
                    <button
                      onClick={() => {
                        setSelected(stream.id);
                        changeSection("shorts");
                      }}
                      className="inline-flex items-center justify-center gap-1 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-bold text-white"
                    >
                      <WandSparkles size={14} />
                      {ar ? "صانع الشورتات" : "Shorts studio"}
                    </button>
                    <button
                      onClick={() => {
                        setSelected(stream.id);
                        setThumbPlatform(stream.platform);
                        changeSection("thumbnail");
                      }}
                      className="inline-flex items-center justify-center gap-1 rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white"
                    >
                      <ImageIcon size={14} />
                      {ar ? "صانع الغلاف" : "Thumbnail studio"}
                    </button>
                    <label className="inline-flex cursor-pointer items-center justify-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold">
                      <Upload size={14} />
                      {ar ? "رفع غلاف" : "Upload cover"}
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        className="hidden"
                        onChange={(e) =>
                          uploadRecordingThumbnail(
                            stream.id,
                            e.target.files?.[0],
                          )
                        }
                      />
                    </label>
                  </div>
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
                <button
                  onClick={() => {
                    setThumbFormat("short");
                    changeSection("thumbnail");
                  }}
                  className="mt-2 text-xs font-black text-emerald-700"
                >
                  {ar
                    ? "فتح صانع الثامبنيل الطولي ←"
                    : "Open vertical Thumbnail Studio →"}
                </button>
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
                  {ar ? "مقطع عادي · 1280×720" : "Regular VOD · 1280×720"}
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
              {thumbFormat === "short" ? "1080 × 1920" : "1280 × 720"}
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
                  {ar
                    ? "لم يُرفق رابط للقناة."
                    : "No channel URL was provided."}
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

  const content =
    section === "live"
      ? liveView
      : section === "archive"
        ? archiveView
        : section === "shorts"
          ? shortsView
          : section === "thumbnail"
            ? thumbnailView
            : section === "branding"
              ? brandingView
              : suggestionsView;
  return (
    <Shell
      activeCount={active.length}
      activeSection={section}
      onSectionChange={changeSection}
    >
      <div className="mx-auto max-w-[1500px]">
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

function ClapperboardIcon(props: React.ComponentProps<typeof Film>) {
  return <Film {...props} />;
}
