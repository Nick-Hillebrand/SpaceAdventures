import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import en from "./locales/en.json";
import de from "./locales/de.json";
import fr from "./locales/fr.json";
import ja from "./locales/ja.json";
import ru from "./locales/ru.json";
import es from "./locales/es.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    load: "languageOnly", // P19: navigator.language returns "en-US", resolves to "en"
    fallbackLng: "en",
    resources: {
      en: { translation: en },
      de: { translation: de },
      fr: { translation: fr },
      ja: { translation: ja },
      ru: { translation: ru },
      es: { translation: es },
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
