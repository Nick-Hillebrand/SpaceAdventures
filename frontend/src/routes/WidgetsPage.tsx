import { useState } from "react";
import { useTranslation } from "react-i18next";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "de", label: "Deutsch" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "ja", label: "日本語" },
  { code: "ru", label: "Русский" },
] as const;

type LangCode = (typeof LANGUAGES)[number]["code"];

function buildEmbedUrl(
  provider: string,
  lang: LangCode,
): string {
  const base = `${window.location.origin}/embed/next-launch`;
  const params = new URLSearchParams();
  if (provider) params.set("provider", provider);
  if (lang !== "en") params.set("lang", lang);
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

function buildSnippet(embedUrl: string): string {
  return `<iframe\n  src="${embedUrl}"\n  width="320"\n  height="180"\n  frameborder="0"\n  loading="lazy"\n  title="Next rocket launch"\n></iframe>`;
}

export default function WidgetsPage() {
  const { t } = useTranslation();
  const [provider, setProvider] = useState("");
  const [lang, setLang] = useState<LangCode>("en");
  const [copied, setCopied] = useState(false);

  const embedUrl = buildEmbedUrl(provider, lang);
  const snippet = buildSnippet(embedUrl);

  const handleCopy = () => {
    navigator.clipboard.writeText(snippet).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="widgets-page" data-testid="widgets-page">
      <h1>{t("widgets.title")}</h1>

      <section className="widgets-section" data-testid="next-launch-widget-section">
        <h2>{t("widgets.nextLaunchTitle")}</h2>
        <p>{t("widgets.description")}</p>

        <div className="widgets-controls">
          <label htmlFor="provider-input">{t("widgets.providerLabel")}</label>
          <input
            id="provider-input"
            data-testid="provider-input"
            type="text"
            value={provider}
            placeholder={t("widgets.providerPlaceholder")}
            onChange={(e) => setProvider(e.target.value)}
          />

          <label htmlFor="lang-select">{t("widgets.languageLabel")}</label>
          <select
            id="lang-select"
            data-testid="lang-select"
            value={lang}
            onChange={(e) => setLang(e.target.value as LangCode)}
          >
            {LANGUAGES.map(({ code, label }) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <h3>{t("widgets.previewTitle")}</h3>
        <iframe
          data-testid="embed-preview"
          src={embedUrl}
          width="320"
          height="180"
          title={t("widgets.iframeTitle")}
        />

        <h3>{t("widgets.snippetTitle")}</h3>
        <pre data-testid="embed-snippet" style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
          {snippet}
        </pre>
        <button
          type="button"
          data-testid="copy-button"
          onClick={handleCopy}
        >
          {copied ? t("widgets.copied") : t("widgets.copyButton")}
        </button>
      </section>
    </div>
  );
}
