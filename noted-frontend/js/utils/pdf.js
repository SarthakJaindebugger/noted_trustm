/**
 * PDF utilities — validated Unicode font loading for jsPDF.
 *
 * Uses a real Google Fonts TTF that covers Korean and Latin, then validates
 * that the browser can load it before registering it with jsPDF.
 */

const FONT_FAMILY = 'NotoSansKRPdf';
const FONT_URL = '/fonts/NotoSansKR-wght.ttf';
const FONT_FILENAME = 'NotoSansKR-wght.ttf';
const FONT_PROBE_TEXT = 'ABC abc 123 ÅÄÖ 가각한글';

let fontBufferPromise = null;
let browserFontReadyPromise = null;

async function fetchFontBuffer(url) {
    if (fontBufferPromise) {
        return fontBufferPromise;
    }

    fontBufferPromise = (async () => {
        const response = await fetch(url, { cache: 'force-cache' });
        if (!response.ok) {
            throw new Error(`Failed to fetch font: ${response.status}`);
        }

        const buffer = await response.arrayBuffer();
        validateTrueTypeFont(buffer);
        return buffer;
    })();

    return fontBufferPromise;
}

function validateTrueTypeFont(buffer) {
    if (!buffer || buffer.byteLength < 12) {
        throw new Error('Font file is empty or truncated.');
    }

    const header = new Uint8Array(buffer, 0, 4);
    const isTrueType =
        (header[0] === 0x00 && header[1] === 0x01 && header[2] === 0x00 && header[3] === 0x00) ||
        (header[0] === 0x74 && header[1] === 0x72 && header[2] === 0x75 && header[3] === 0x65);

    if (!isTrueType) {
        throw new Error('Font file is not a supported TrueType font.');
    }
}

async function ensureBrowserFontReady(buffer) {
    if (browserFontReadyPromise) {
        return browserFontReadyPromise;
    }

    browserFontReadyPromise = (async () => {
        if (typeof FontFace !== 'function' || !document?.fonts) {
            throw new Error('Browser FontFace API not available.');
        }

        const face = new FontFace(FONT_FAMILY, buffer);
        const loadedFace = await face.load();
        document.fonts.add(loadedFace);

        const probes = [
            `16px "${FONT_FAMILY}"`,
            `700 16px "${FONT_FAMILY}"`,
        ];

        for (const probe of probes) {
            const loaded = await document.fonts.load(probe, FONT_PROBE_TEXT);
            if (!loaded || loaded.length === 0) {
                throw new Error(`Browser could not load PDF font for probe: ${probe}`);
            }
        }
    })();

    return browserFontReadyPromise;
}

function arrayBufferToBase64(buffer) {
    return new Promise((resolve, reject) => {
        const blob = new Blob([buffer], { type: 'font/ttf' });
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

/**
 * Register the validated Unicode font with a jsPDF doc instance.
 * @param {jsPDF} doc
 */
export async function registerCJKFont(doc) {
    const buffer = await fetchFontBuffer(FONT_URL);
    await ensureBrowserFontReady(buffer);
    const base64 = await arrayBufferToBase64(buffer);

    doc.addFileToVFS(FONT_FILENAME, base64);
    doc.addFont(FONT_FILENAME, 'NotoSansCJK', 'normal');
    doc.addFont(FONT_FILENAME, 'NotoSansCJK', 'bold');

    const fontList = doc.getFontList?.() || {};
    const registeredFamilies = Object.keys(fontList);
    if (!registeredFamilies.includes('NotoSansCJK')) {
        throw new Error('PDF font registration failed.');
    }

    doc.setFont('NotoSansCJK', 'normal');
}
