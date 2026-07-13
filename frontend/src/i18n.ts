import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en from "./locales/en.json";

// English ships in the initial bundle (it's the fallback and the common
// case). The other five locales are lazy-loaded per language through this
// dynamic-import backend so they never inflate the initial chunk
// (26-performance.md: "six locales must not all ship in the initial bundle").
const lazyLocaleBackend = {
  type: "backend" as const,
  read(
    language: string,
    _namespace: string,
    callback: (err: Error | null, data: unknown) => void,
  ) {
    import(`./locales/${language}.json`)
      .then((mod) => callback(null, mod.default))
      .catch((err) => callback(err as Error, null));
  },
};

i18n
  .use(LanguageDetector)
  .use(lazyLocaleBackend)
  .use(initReactI18next)
  .init({
    load: "languageOnly", // P19: navigator.language returns "en-US", resolves to "en"
    fallbackLng: "en",
    partialBundledLanguages: true,
    resources: {
      en: { translation: en },
    },
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "space-adventures-lang",
      caches: ["localStorage"],
    },
  });

export default i18n;
