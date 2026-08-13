import { ref } from 'vue';

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'fi', label: 'Finnish' },
  { code: 'sv', label: 'Swedish' },
  { code: 'fr', label: 'French' },
  { code: 'ar', label: 'Arabic' },
  { code: 'de', label: 'German' },
  { code: 'es', label: 'Spanish' },
  { code: 'ru', label: 'Russian' },
  { code: 'zh-CN', label: 'Chinese' },
  { code: 'so', label: 'Somali' },
  { code: 'fa', label: 'Persian' },
  { code: 'hi', label: 'Hindi' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'it', label: 'Italian' },
  { code: 'pl', label: 'Polish' },
  { code: 'uk', label: 'Ukrainian' },
];

const currentLanguage = ref(localStorage.getItem('app_language') || 'en');

function ensureGoogleTranslateLoaded() {
  return new Promise((resolve) => {
    if (window.google && window.google.translate) {
      resolve();
      return;
    }

    // Add the hidden Google Translate element if not present
    if (!document.getElementById('google_translate_element')) {
      const div = document.createElement('div');
      div.id = 'google_translate_element';
      div.style.display = 'none';
      document.body.appendChild(div);
    }

    // Define the callback
    window.googleTranslateElementInit = () => {
      new window.google.translate.TranslateElement(
        { pageLanguage: 'en', autoDisplay: false },
        'google_translate_element'
      );
      resolve();
    };

    // Load the script
    if (!document.getElementById('google-translate-script')) {
      const script = document.createElement('script');
      script.id = 'google-translate-script';
      script.src = '//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
      document.head.appendChild(script);
    }
  });
}

function triggerGoogleTranslate(langCode) {
  // Google Translate uses a cookie to set language
  // Set the googtrans cookie and reload the translate frame
  const value = langCode === 'en' ? '' : `/en/${langCode}`;

  // Set cookie for both paths
  document.cookie = `googtrans=${value};path=/`;
  document.cookie = `googtrans=${value};path=/;domain=${window.location.hostname}`;

  // Try to use the Google Translate combo box directly
  const frame = document.querySelector('.goog-te-menu-frame');
  if (frame) {
    const innerDoc = frame.contentDocument || frame.contentWindow.document;
    const items = innerDoc.querySelectorAll('.goog-te-menu2-item span.text');
    for (const item of items) {
      const text = item.textContent.toLowerCase();
      const target = LANGUAGES.find(l => l.code === langCode);
      if (target && text === target.label.toLowerCase()) {
        item.click();
        return;
      }
    }
  }

  // Fallback: set the select element value
  const select = document.querySelector('.goog-te-combo');
  if (select) {
    select.value = langCode;
    select.dispatchEvent(new Event('change'));
    return;
  }

  // If widget isn't ready yet, wait and retry
  setTimeout(() => {
    const sel = document.querySelector('.goog-te-combo');
    if (sel) {
      sel.value = langCode;
      sel.dispatchEvent(new Event('change'));
    }
  }, 1000);
}

async function setLanguage(code) {
  currentLanguage.value = code;
  localStorage.setItem('app_language', code);

  await ensureGoogleTranslateLoaded();

  if (code === 'en') {
    // Reset to original language
    const select = document.querySelector('.goog-te-combo');
    if (select) {
      select.value = '';
      select.dispatchEvent(new Event('change'));
    }
    // Clear cookie
    document.cookie = 'googtrans=;path=/;expires=Thu, 01 Jan 1970 00:00:00 GMT';
    document.cookie = `googtrans=;path=/;domain=${window.location.hostname};expires=Thu, 01 Jan 1970 00:00:00 GMT`;
    // Reload to fully reset translation
    window.location.reload();
    return;
  }

  triggerGoogleTranslate(code);
}

function getLanguageLabel() {
  const lang = LANGUAGES.find(l => l.code === currentLanguage.value);
  return lang ? lang.label : 'English';
}

function initOnLoad() {
  const saved = localStorage.getItem('app_language');
  if (saved && saved !== 'en') {
    ensureGoogleTranslateLoaded().then(() => {
      setTimeout(() => triggerGoogleTranslate(saved), 1500);
    });
  }
}

// Auto-init when the page loads
if (typeof window !== 'undefined') {
  if (document.readyState === 'complete') {
    initOnLoad();
  } else {
    window.addEventListener('load', initOnLoad);
  }
}

export const languageService = {
  LANGUAGES,
  currentLanguage,
  setLanguage,
  getLanguageLabel,
};
