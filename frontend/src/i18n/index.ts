/**
 * Lightweight i18n scaffold (EN live; ZH/AR keys reserved per docs/LANGUAGES.md).
 * Full RTL Arabic mirroring is a separate project — do not flip layout here yet.
 */

export type AppLocale = 'en' | 'zh' | 'ar';

const STRINGS: Record<AppLocale, Record<string, string>> = {
  en: {
    'app.name': 'FundReady AI',
    'investor.verify.title': 'Investor verification',
    'investor.verify.cta': 'Verify identity',
    'founder.programmes.title': 'Programmes',
    'alerts.empty': 'Alerts will appear here when they arrive.',
  },
  zh: {
    'app.name': 'FundReady AI',
    'investor.verify.title': '投资者认证',
    'investor.verify.cta': '验证身份',
    'founder.programmes.title': '课程与活动',
    'alerts.empty': '有新消息时将显示在此处。',
  },
  ar: {
    'app.name': 'FundReady AI',
    'investor.verify.title': 'التحقق من المستثمر',
    'investor.verify.cta': 'تحقق من الهوية',
    'founder.programmes.title': 'البرامج',
    'alerts.empty': 'ستظهر التنبيهات هنا عند وصولها.',
  },
};

let current: AppLocale = 'en';

export function setLocale(locale: AppLocale): void {
  current = locale;
}

export function getLocale(): AppLocale {
  return current;
}

export function t(key: string): string {
  return STRINGS[current][key] ?? STRINGS.en[key] ?? key;
}
